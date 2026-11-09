import pytest
import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import User
from apps.companies.models import Company
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile
from apps.applications.models import Application
from apps.notifications.models import RecruiterEmailAccount, EmailLog
from apps.notifications.services import send_ats_email


class GmailAPIOAuthSendingTests(TestCase):
    def setUp(self):
        unique_email = f'nikhil_{uuid.uuid4().hex[:6]}@2020technologies.in'
        self.recruiter = User.objects.create_user(
            email=unique_email,
            first_name='Nikhil',
            last_name='Mittal',
            password='Password123!',
            role=User.Role.RECRUITER
        )
        self.email_account = RecruiterEmailAccount.objects.create(
            recruiter=self.recruiter,
            account_type='OAUTH',
            provider='GMAIL',
            email_address=unique_email,
            oauth_access_token='mock_google_oauth_token_xyz123',
            is_verified=True,
            is_default=True
        )
        self.company = Company.objects.create(name='2020Tech', slug='2020tech')
        self.job = Job.objects.create(
            title='Senior Backend Engineer',
            company=self.company,
            created_by=self.recruiter,
            status='ACTIVE'
        )
        self.candidate_user = User.objects.create_user(
            email=f'candidate_{uuid.uuid4().hex[:6]}@example.com',
            role=User.Role.CANDIDATE
        )
        self.profile = CandidateProfile.objects.create(
            user=self.candidate_user,
            full_name='Deepak Kumar',
            location='Delhi',
            resume=SimpleUploadedFile("resume.pdf", b"PDF content", content_type="application/pdf")
        )
        self.application = Application.objects.create(
            job=self.job,
            candidate=self.profile,
            created_by=self.recruiter
        )
        self.client_session = Client()
        self.client_session.force_login(self.recruiter)

        # Configure recruiter Gmail OAuth credentials for tests
        self.patcher_recruiter_oauth = patch.dict('os.environ', {
            'RECRUITER_GMAIL_OAUTH_CLIENT_ID': 'test-recruiter-client-id-xyz',
            'RECRUITER_GMAIL_OAUTH_CLIENT_SECRET': 'test-recruiter-client-secret-xyz',
            'RECRUITER_GMAIL_OAUTH_CALLBACK_URL': 'https://talent-vault.in/notifications/oauth/gmail/callback/'
        })
        self.patcher_recruiter_oauth.start()
        self.addCleanup(self.patcher_recruiter_oauth.stop)

        # Mock Gmail sendAs alias verification to return accepted profiles@2020technologies.in by default
        self.mock_get_patcher = patch('requests.get')
        self.mock_requests_get = self.mock_get_patcher.start()
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "sendAs": [
                {
                    "sendAsEmail": "profiles@2020technologies.in",
                    "displayName": "TalentVault Profiles",
                    "verificationStatus": "accepted"
                }
            ]
        }
        self.mock_requests_get.return_value = mock_get_resp
        self.addCleanup(self.mock_get_patcher.stop)

    @patch('requests.post')
    def test_gmail_api_oauth_messages_send(self, mock_requests_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "msg_gmail_12345",
            "threadId": "thread_gmail_12345",
            "labelIds": ["SENT"]
        }
        mock_requests_post.return_value = mock_response

        email_log, success, message = send_ats_email(
            sender=self.recruiter,
            recipient_email='client@company.com',
            subject='Candidate Shortlist for Senior Backend Engineer',
            body='Please find Nikhil Mittal shortlisted candidates attached.',
            attachments=[self.profile.resume],
            email_account=self.email_account
        )

        self.assertTrue(success)
        self.assertEqual(email_log.status, 'SENT')
        self.assertTrue(mock_requests_post.called)

        called_args, called_kwargs = mock_requests_post.call_args
        self.assertEqual(called_args[0], "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")
        self.assertIn("Authorization", called_kwargs['headers'])
        self.assertEqual(called_kwargs['headers']['Authorization'], "Bearer mock_google_oauth_token_xyz123")
        self.assertIn("raw", called_kwargs['json'])

        # Verify From and Reply-To headers
        import base64
        from email import message_from_bytes
        raw_mime = base64.urlsafe_b64decode(called_kwargs['json']['raw'])
        parsed = message_from_bytes(raw_mime)
        self.assertEqual(parsed['From'], "Nikhil Mittal <profiles@2020technologies.in>")
        self.assertEqual(parsed['Reply-To'], self.email_account.email_address)

    @patch('requests.post')
    def test_job_candidates_email_to_client_with_gmail_api(self, mock_requests_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "msg_999", "labelIds": ["SENT"]}
        mock_requests_post.return_value = mock_response

        url = reverse('frontend:job_candidates_email_to_client', kwargs={'job_id': self.job.id})
        response = self.client_session.post(url, {
            'candidate_ids[]': [str(self.profile.id)],
            'to_email': 'hiring.manager@clientcorp.com',
            'email_account_id': str(self.email_account.id),
            'subject': 'Shortlist from Nikhil Mittal',
            'body': 'Here are the candidate profiles.',
            'attach_resumes': 'true'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(mock_requests_post.called)

    @patch('requests.post')
    def test_oauth_token_refresh_before_sending(self, mock_requests_post):
        self.email_account.oauth_refresh_token = 'valid_refresh_token_abc'
        self.email_account.token_expires_at = timezone.now() - timezone.timedelta(hours=1)
        self.email_account.save()

        def post_side_effect(url, **kwargs):
            res = MagicMock()
            if 'oauth2.googleapis.com/token' in url:
                res.status_code = 200
                res.json.return_value = {"access_token": "refreshed_access_token_xyz", "expires_in": 3600}
            else:
                res.status_code = 200
                res.json.return_value = {"id": "msg_refreshed_123"}
            return res

        mock_requests_post.side_effect = post_side_effect

        email_log, success, message = send_ats_email(
            sender=self.recruiter,
            recipient_email='client@company.com',
            subject='Token Refresh Test',
            body='Testing token refresh.',
            email_account=self.email_account
        )

        self.assertTrue(success)
        self.assertEqual(email_log.status, 'SENT')
        self.email_account.refresh_from_db()
        self.assertEqual(self.email_account.oauth_access_token, "refreshed_access_token_xyz")

    @patch('requests.post')
    def test_oauth_revoked_credentials_401(self, mock_requests_post):
        self.email_account.oauth_refresh_token = 'revoked_refresh_token_xyz'
        self.email_account.save()

        def post_side_effect(url, **kwargs):
            res = MagicMock()
            if 'oauth2.googleapis.com/token' in url:
                res.status_code = 401
                res.text = "Invalid Grant"
            else:
                res.status_code = 401
                res.text = "Unauthorized"
            return res

        mock_requests_post.side_effect = post_side_effect

        email_log, success, message = send_ats_email(
            sender=self.recruiter,
            recipient_email='client@company.com',
            subject='Revoked Credentials Test',
            body='Testing revoked credentials.',
            email_account=self.email_account
        )

        self.assertFalse(success)
        self.assertEqual(email_log.status, 'FAILED')
        self.email_account.refresh_from_db()
        self.assertFalse(self.email_account.is_verified)

    def test_preserve_existing_refresh_token(self):
        self.email_account.oauth_refresh_token = 'original_refresh_token_123'
        self.email_account.save()

        url = reverse('notifications:recruiter_email_accounts_api')
        response = self.client_session.post(url, {
            'action': 'connect_oauth',
            'provider': 'GMAIL',
            'email_address': self.recruiter.email,
            'oauth_access_token': 'new_access_token_456',
            # no refresh_token provided in request
        })
        self.assertEqual(response.status_code, 200)
        self.email_account.refresh_from_db()
        self.assertEqual(self.email_account.oauth_refresh_token, 'original_refresh_token_123')
        self.assertEqual(self.email_account.oauth_access_token, 'new_access_token_456')

    def test_alias_verification_accepted(self):
        """
        Verify that verify_sendas_alias checks users.settings.sendAs.list
        and returns True when profiles@2020technologies.in is accepted.
        """
        is_verified, error_msg = self.email_account.verify_sendas_alias("profiles@2020technologies.in")
        self.assertTrue(is_verified)
        self.assertIsNone(error_msg)
        self.assertTrue(self.mock_requests_get.called)
        called_args, called_kwargs = self.mock_requests_get.call_args
        self.assertEqual(called_args[0], "https://gmail.googleapis.com/gmail/v1/users/me/settings/sendAs")
        self.assertEqual(called_kwargs['headers']['Authorization'], f"Bearer {self.email_account.oauth_access_token}")

    @patch('requests.post')
    def test_alias_missing_blocks_sending(self, mock_requests_post):
        """
        If profiles@2020technologies.in is missing from Gmail sendAs list,
        sending must be blocked, email_log marked FAILED, and messages.send never called.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sendAs": [
                {
                    "sendAsEmail": "other@company.com",
                    "verificationStatus": "accepted"
                }
            ]
        }
        self.mock_requests_get.return_value = mock_resp

        email_log, success, message = send_ats_email(
            sender=self.recruiter,
            recipient_email='client@company.com',
            subject='Shortlist',
            body='Body content',
            email_account=self.email_account
        )

        self.assertFalse(success)
        self.assertEqual(email_log.status, 'FAILED')
        self.assertIn("profiles@2020technologies.in", message)
        self.assertIn("not configured", message)
        self.assertFalse(mock_requests_post.called)

    @patch('requests.post')
    def test_alias_unverified_status_pending_blocks_sending(self, mock_requests_post):
        """
        If profiles@2020technologies.in is present but verificationStatus is not 'accepted'
        (e.g., 'pending'), sending must be blocked and messages.send never called.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sendAs": [
                {
                    "sendAsEmail": "profiles@2020technologies.in",
                    "verificationStatus": "pending"
                }
            ]
        }
        self.mock_requests_get.return_value = mock_resp

        email_log, success, message = send_ats_email(
            sender=self.recruiter,
            recipient_email='client@company.com',
            subject='Shortlist',
            body='Body content',
            email_account=self.email_account
        )

        self.assertFalse(success)
        self.assertEqual(email_log.status, 'FAILED')
        self.assertIn("unverified", message)
        self.assertIn("pending", message)
        self.assertFalse(mock_requests_post.called)

    @patch('requests.post')
    def test_alias_verification_scope_insufficient_403(self, mock_requests_post):
        """
        If Gmail API returns 403 Forbidden due to missing gmail.settings.basic scope,
        sending must be blocked and a clear error requesting reconnection displayed.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = '{"error": {"status": "PERMISSION_DENIED"}}'
        self.mock_requests_get.return_value = mock_resp

        email_log, success, message = send_ats_email(
            sender=self.recruiter,
            recipient_email='client@company.com',
            subject='Shortlist',
            body='Body content',
            email_account=self.email_account
        )

        self.assertFalse(success)
        self.assertEqual(email_log.status, 'FAILED')
        self.assertIn("gmail.settings.basic", message)
        self.assertIn("reconnect", message.lower())
        self.assertFalse(mock_requests_post.called)

    @patch('requests.post')
    def test_from_and_reply_to_and_sent_folder_behaviour(self, mock_requests_post):
        """
        Tests exact From name/email, Reply-To header, and Gmail API users.messages.send
        sent folder placement for recruiter-to-client emails.
        """
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "id": "msg_sent_in_folder_456",
            "threadId": "thread_456",
            "labelIds": ["SENT"]
        }
        mock_requests_post.return_value = mock_post_resp

        email_log, success, message = send_ats_email(
            sender=self.recruiter,
            recipient_email='client@acme.com',
            subject='Candidate Submission',
            body='Please see candidate details.',
            email_account=self.email_account
        )

        self.assertTrue(success)
        self.assertEqual(email_log.status, 'SENT')
        self.assertTrue(mock_requests_post.called)

        called_args, called_kwargs = mock_requests_post.call_args
        self.assertEqual(called_args[0], "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")

        import base64
        from email import message_from_bytes
        raw_mime = base64.urlsafe_b64decode(called_kwargs['json']['raw'])
        parsed = message_from_bytes(raw_mime)
        # From Name: Logged-in recruiter name (Nikhil Mittal)
        # From Email: profiles@2020technologies.in
        self.assertEqual(parsed['From'], "Nikhil Mittal <profiles@2020technologies.in>")
        # Reply-To: Recruiter's work email
        self.assertEqual(parsed['Reply-To'], self.email_account.email_address)
        self.assertEqual(parsed['To'], "client@acme.com")

    @patch('django.core.mail.send_mail')
    def test_no_fallback_to_shared_gmail(self, mock_send_mail):
        """
        When recruiter has no verified Gmail/Google Workspace OAuth account,
        sending must fail with clear error and NEVER use TalentVault's shared Gmail fallback.
        """
        unverified_account = RecruiterEmailAccount.objects.create(
            recruiter=self.recruiter,
            account_type='SMTP',
            provider='SMTP',
            email_address='smtp@example.com',
            is_verified=False
        )

        with self.assertRaises(ValueError) as ctx:
            send_ats_email(
                sender=self.recruiter,
                recipient_email='client@acme.com',
                subject='Test',
                body='Test',
                email_account=unverified_account
            )

        self.assertFalse(mock_send_mail.called)
        self.assertIn("unverified", str(ctx.exception).lower())

    def test_api_verify_alias_endpoint(self):
        """
        Tests the recruiter email account verify_alias API action.
        """
        url = reverse('notifications:recruiter_email_accounts_api')
        response = self.client_session.post(url, {
            'action': 'verify_alias',
            'account_id': str(self.email_account.id)
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn("verified successfully", data['message'])

    def test_gmail_oauth_start_real_http_redirect(self):
        """
        Ensure clicking Connect & Verify / hitting recruiter_gmail_oauth_start issues a real
        HTTP 302 redirect to Google's consent screen with required scopes, prompt=consent, access_type=offline.
        """
        url = reverse('notifications:recruiter_gmail_oauth_start')
        response = self.client_session.get(url, {'email_address': self.recruiter.email})
        self.assertEqual(response.status_code, 302)
        redirect_url = response.url
        self.assertTrue(redirect_url.startswith("https://accounts.google.com/o/oauth2/v2/auth"))

        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)

        self.assertIn('client_id', params)
        self.assertEqual(params.get('client_id'), ['test-recruiter-client-id-xyz'])
        self.assertIn('redirect_uri', params)
        self.assertEqual(params.get('redirect_uri'), ['https://talent-vault.in/notifications/oauth/gmail/callback/'])
        self.assertEqual(params.get('response_type'), ['code'])
        self.assertEqual(params.get('access_type'), ['offline'])
        self.assertEqual(params.get('prompt'), ['consent'])

        scope_str = params.get('scope', [''])[0]
        self.assertIn('https://www.googleapis.com/auth/gmail.send', scope_str)
        self.assertIn('https://www.googleapis.com/auth/gmail.settings.basic', scope_str)

        # State stored in session matches state in redirect query
        state = params.get('state', [None])[0]
        self.assertIsNotNone(state)
        self.assertEqual(self.client_session.session.get('gmail_oauth_state'), state)
        self.assertEqual(self.client_session.session.get('gmail_oauth_recruiter_id'), str(self.recruiter.id))

    def test_gmail_oauth_start_missing_credentials(self):
        """
        Displays clear error if RECRUITER_GMAIL_OAUTH_CLIENT_ID or RECRUITER_GMAIL_OAUTH_CLIENT_SECRET is missing.
        """
        with patch('django.conf.settings.RECRUITER_GMAIL_OAUTH_CLIENT_ID', ''), \
             patch('django.conf.settings.RECRUITER_GMAIL_OAUTH_CLIENT_SECRET', ''), \
             patch.dict('os.environ', {'RECRUITER_GMAIL_OAUTH_CLIENT_ID': '', 'RECRUITER_GMAIL_OAUTH_CLIENT_SECRET': ''}):
            url = reverse('notifications:recruiter_gmail_oauth_start')
            response = self.client_session.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('settings', response.url)

    @patch('requests.post')
    def test_gmail_oauth_callback_success(self, mock_requests_post):
        """
        Tests complete OAuth callback flow: state validation, code exchange,
        userinfo fetch, account creation with is_verified=True, and alias check.
        """
        # Set session state
        session = self.client_session.session
        session['gmail_oauth_state'] = 'test_secure_state_789'
        session['gmail_oauth_recruiter_id'] = str(self.recruiter.id)
        session['gmail_oauth_expected_email'] = self.recruiter.email
        session.save()

        # Mock token exchange
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            'access_token': 'new_google_access_token_999',
            'refresh_token': 'new_google_refresh_token_999',
            'expires_in': 3600,
            'scope': 'https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.settings.basic openid email profile',
        }
        mock_requests_post.return_value = mock_token_resp

        # Mock userinfo and sendAs in requests.get
        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if 'userinfo' in url:
                resp.status_code = 200
                resp.json.return_value = {'email': self.recruiter.email}
            elif 'sendAs' in url:
                resp.status_code = 200
                resp.json.return_value = {
                    'sendAs': [{
                        'sendAsEmail': 'profiles@2020technologies.in',
                        'verificationStatus': 'accepted'
                    }]
                }
            return resp

        self.mock_requests_get.side_effect = get_side_effect

        callback_url = reverse('notifications:recruiter_gmail_oauth_callback')
        response = self.client_session.get(callback_url, {
            'code': 'valid_auth_code_123',
            'state': 'test_secure_state_789'
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn('settings', response.url)
        self.assertIn('email-accounts-panel', response.url)

        # Check account was updated/created and marked verified
        account = RecruiterEmailAccount.objects.get(recruiter=self.recruiter, email_address=self.recruiter.email)
        self.assertTrue(account.is_verified)
        self.assertEqual(account.oauth_access_token, 'new_google_access_token_999')
        self.assertEqual(account.oauth_refresh_token, 'new_google_refresh_token_999')

    @patch('requests.post')
    def test_gmail_oauth_callback_preserves_existing_refresh_token(self, mock_requests_post):
        """
        When Google re-authorizes without issuing a new refresh token, the existing
        refresh token must be preserved.
        """
        self.email_account.oauth_refresh_token = 'existing_precious_refresh_token'
        self.email_account.save()

        session = self.client_session.session
        session['gmail_oauth_state'] = 'state_preserve_token'
        session['gmail_oauth_recruiter_id'] = str(self.recruiter.id)
        session.save()

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        # No refresh_token returned by Google
        mock_token_resp.json.return_value = {
            'access_token': 'latest_access_token_only',
            'expires_in': 3600,
            'scope': 'https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.settings.basic openid email profile',
        }
        mock_requests_post.return_value = mock_token_resp

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if 'userinfo' in url:
                resp.status_code = 200
                resp.json.return_value = {'email': self.recruiter.email}
            else:
                resp.status_code = 200
                resp.json.return_value = {
                    'sendAs': [{
                        'sendAsEmail': 'profiles@2020technologies.in',
                        'verificationStatus': 'accepted'
                    }]
                }
            return resp

        self.mock_requests_get.side_effect = get_side_effect

        callback_url = reverse('notifications:recruiter_gmail_oauth_callback')
        response = self.client_session.get(callback_url, {
            'code': 'valid_code',
            'state': 'state_preserve_token'
        })

        self.assertEqual(response.status_code, 302)
        self.email_account.refresh_from_db()
        self.assertEqual(self.email_account.oauth_access_token, 'latest_access_token_only')
        self.assertEqual(self.email_account.oauth_refresh_token, 'existing_precious_refresh_token')

    def test_gmail_oauth_callback_state_mismatch_rejected(self):
        """
        OAuth state mismatch must reject the callback, show an error, and not mark account verified.
        """
        session = self.client_session.session
        session['gmail_oauth_state'] = 'correct_state'
        session.save()

        callback_url = reverse('notifications:recruiter_gmail_oauth_callback')
        response = self.client_session.get(callback_url, {
            'code': 'auth_code',
            'state': 'wrong_tampered_state'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('settings', response.url)

    def test_gmail_oauth_callback_denied_by_user(self):
        """
        User cancelling OAuth consent redirects to settings with error.
        """
        callback_url = reverse('notifications:recruiter_gmail_oauth_callback')
        response = self.client_session.get(callback_url, {
            'error': 'access_denied',
            'error_description': 'User denied access'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('settings', response.url)

    def test_settings_html_contains_oauth_redirect_form(self):
        """
        Verify settings.html renders the form with method=GET and action pointing to
        recruiter_gmail_oauth_start, ensuring a real HTTP browser navigation.
        """
        url = reverse('frontend:settings')
        response = self.client_session.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('action="/notifications/oauth/gmail/start/"', html)
        self.assertIn('id="oauthAccountForm"', html)
        self.assertIn('Connect & Verify', html)
