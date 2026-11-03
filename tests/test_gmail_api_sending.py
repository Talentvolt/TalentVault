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
