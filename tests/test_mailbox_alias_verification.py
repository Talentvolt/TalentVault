import base64
import email
from email import policy
import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.messages import get_messages

from apps.accounts.models import User
from apps.companies.models import Company
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile
from apps.applications.models import Application
from apps.notifications.models import RecruiterEmailAccount, EmailLog
from apps.notifications.services import send_ats_email


class RecruiterMailboxAliasVerificationTests(TestCase):
    """
    Dedicated test suite validating:
    Requirement 1 — Growfluence Gmail testing:
      - Mailbox: growfluencestudio@gmail.com
      - Verify using its own primary Gmail address.
      - Do NOT require profiles@2020technologies.in as an alias.
      - From: Growfluence Studio <growfluencestudio@gmail.com>
      - Reply-To: growfluencestudio@gmail.com
      - Sent via Gmail API (lands in Growfluence Sent folder).
    
    Requirement 2 — Nikhil's company mailbox:
      - Mailbox: nikhil@2020technologies.in
      - Require the verified Send As alias profiles@2020technologies.in.
      - From: Nikhil Mittal <profiles@2020technologies.in>
      - Reply-To: nikhil@2020technologies.in
      - Sent via Gmail API (lands in Nikhil's Sent folder).

    Technical requirements:
      - Alias verification depends on authenticated mailbox, not one global setting.
      - Never require Nikhil alias for unrelated recruiter accounts.
      - Strict credential isolation & no shared email fallback.
    """

    RECRUITER_CLIENT_ID = "recruiter-oauth-client-id-12345"
    RECRUITER_CLIENT_SECRET = "recruiter-oauth-client-secret-67890"

    def setUp(self):
        self.env_patcher = patch.dict("os.environ", {
            "RECRUITER_GMAIL_OAUTH_CLIENT_ID": self.RECRUITER_CLIENT_ID,
            "RECRUITER_GMAIL_OAUTH_CLIENT_SECRET": self.RECRUITER_CLIENT_SECRET,
            "RECRUITER_GMAIL_OAUTH_CALLBACK_URL": "https://talent-vault.in/notifications/oauth/gmail/callback/",
        })
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

        self.settings_patcher = patch.multiple(
            "django.conf.settings",
            RECRUITER_GMAIL_OAUTH_CLIENT_ID=self.RECRUITER_CLIENT_ID,
            RECRUITER_GMAIL_OAUTH_CLIENT_SECRET=self.RECRUITER_CLIENT_SECRET,
            RECRUITER_GMAIL_OAUTH_CALLBACK_URL="https://talent-vault.in/notifications/oauth/gmail/callback/",
            RECRUITER_CLIENT_ALIAS_EMAIL="profiles@2020technologies.in",
            RECRUITER_MAILBOX_ALIASES={
                "nikhil@2020technologies.in": "profiles@2020technologies.in",
            }
        )
        self.settings_patcher.start()
        self.addCleanup(self.settings_patcher.stop)

        self.company = Company.objects.create(name="TechCorp", slug="techcorp")

    # -------------------------------------------------------------------------
    # REQUIREMENT 1: GROWFLUENCE GMAIL TESTING
    # -------------------------------------------------------------------------

    @patch("requests.get")
    def test_growfluence_mailbox_verifies_using_own_primary_address(self, mock_requests_get):
        """
        Growfluence mailbox (growfluencestudio@gmail.com):
        - Must verify using its own primary address.
        - Must NOT require profiles@2020technologies.in.
        """
        recruiter, _ = User.objects.get_or_create(
            email="growfluencestudio@gmail.com",
            defaults={
                "first_name": "Growfluence",
                "last_name": "Studio",
                "role": User.Role.RECRUITER
            }
        )
        if not recruiter.first_name:
            recruiter.first_name = "Growfluence"
            recruiter.last_name = "Studio"
            recruiter.save()
        account = RecruiterEmailAccount.objects.create(
            recruiter=recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address="growfluencestudio@gmail.com",
            oauth_access_token="growfluence_token_abc",
            is_verified=True,
            is_default=True
        )

        # Confirm get_required_alias() returns None for Growfluence
        self.assertIsNone(account.get_required_alias())
        self.assertEqual(account.get_sending_email_address(), "growfluencestudio@gmail.com")

        # Mock sendAs list returning only growfluencestudio@gmail.com (NO profiles@2020technologies.in)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sendAs": [
                {
                    "sendAsEmail": "growfluencestudio@gmail.com",
                    "displayName": "Growfluence Studio",
                    "isPrimary": True,
                    "verificationStatus": "accepted"
                }
            ]
        }
        mock_requests_get.return_value = mock_resp

        is_verified, err_msg = account.verify_sendas_alias()
        self.assertTrue(is_verified)
        self.assertIsNone(err_msg)

    @patch("requests.get")
    def test_growfluence_mailbox_verifies_with_pending_verification_status(self, mock_requests_get):
        """
        Regression test:
        Growfluence mailbox (growfluencestudio@gmail.com) with primary address returning
        verificationStatus: "pending" from Gmail API must be accepted successfully (is_verified=True).
        """
        recruiter, _ = User.objects.get_or_create(
            email="growfluencestudio@gmail.com",
            defaults={
                "first_name": "Growfluence",
                "last_name": "Studio",
                "role": User.Role.RECRUITER
            }
        )
        account = RecruiterEmailAccount.objects.create(
            recruiter=recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address="growfluencestudio@gmail.com",
            oauth_access_token="growfluence_token_abc",
            is_verified=True,
            is_default=True
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sendAs": [
                {
                    "sendAsEmail": "growfluencestudio@gmail.com",
                    "displayName": "Growfluence Studio",
                    "isPrimary": True,
                    "verificationStatus": "pending"
                }
            ]
        }
        mock_requests_get.return_value = mock_resp

        is_verified, err_msg = account.verify_sendas_alias()
        self.assertTrue(is_verified, f"Expected verification to succeed even with pending status, got error: {err_msg}")
        self.assertIsNone(err_msg)
        account.refresh_from_db()
        self.assertTrue(account.is_verified)

    @patch("requests.post")
    @patch("requests.get")
    def test_growfluence_send_ats_email_headers_and_sent_folder(
        self, mock_requests_get, mock_requests_post
    ):
        """
        Growfluence mailbox sending:
        - From: Growfluence Studio <growfluencestudio@gmail.com>
        - Reply-To: growfluencestudio@gmail.com
        - Gmail API users.messages.send called with Growfluence token.
        - profiles@2020technologies.in is NOT in From or Reply-To.
        """
        recruiter, _ = User.objects.get_or_create(
            email="growfluencestudio@gmail.com",
            defaults={
                "first_name": "Growfluence",
                "last_name": "Studio",
                "role": User.Role.RECRUITER
            }
        )
        if not recruiter.first_name:
            recruiter.first_name = "Growfluence"
            recruiter.last_name = "Studio"
            recruiter.save()
        account = RecruiterEmailAccount.objects.create(
            recruiter=recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address="growfluencestudio@gmail.com",
            oauth_access_token="growfluence_access_token_111",
            is_verified=True,
            is_default=True
        )

        # Mock sendAs returning primary address only
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "sendAs": [{
                "sendAsEmail": "growfluencestudio@gmail.com",
                "isPrimary": True,
                "verificationStatus": "accepted"
            }]
        }
        mock_requests_get.return_value = mock_get_resp

        # Mock messages.send
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "id": "msg_growfluence_sent_123",
            "threadId": "thread_growfluence_123",
            "labelIds": ["SENT"]
        }
        mock_requests_post.return_value = mock_post_resp

        email_log, success, msg = send_ats_email(
            sender=recruiter,
            recipient_email="client@clientcorp.com",
            subject="Growfluence Talent Presentation",
            body="Hi Client,\nHere is the top profile.",
            email_account=account
        )

        self.assertTrue(success)
        self.assertEqual(email_log.status, "SENT")

        # Inspect Gmail API call
        mock_requests_post.assert_called_once()
        called_url, called_kwargs = mock_requests_post.call_args
        self.assertEqual(called_url[0], "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")
        self.assertEqual(
            called_kwargs["headers"]["Authorization"],
            "Bearer growfluence_access_token_111"
        )

        # Decode raw MIME message to inspect exact headers
        raw_b64 = called_kwargs["json"]["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
        parsed_email = email.message_from_bytes(raw_bytes, policy=policy.default)

        # Verify From and Reply-To headers
        self.assertEqual(parsed_email["From"], "Growfluence Studio <growfluencestudio@gmail.com>")
        self.assertEqual(parsed_email["Reply-To"], "growfluencestudio@gmail.com")
        self.assertEqual(parsed_email["To"], "client@clientcorp.com")
        self.assertNotIn("profiles@2020technologies.in", parsed_email["From"])

    # -------------------------------------------------------------------------
    # REQUIREMENT 2: NIKHIL'S COMPANY MAILBOX
    # -------------------------------------------------------------------------

    @patch("requests.get")
    def test_nikhil_mailbox_requires_profiles_alias(self, mock_requests_get):
        """
        Nikhil's company mailbox (nikhil@2020technologies.in):
        - Must require profiles@2020technologies.in as Send-As alias.
        - Fails verification if profiles@2020technologies.in is missing.
        - Succeeds when profiles@2020technologies.in is accepted.
        """
        recruiter, _ = User.objects.get_or_create(
            email="nikhil@2020technologies.in",
            defaults={
                "first_name": "Nikhil",
                "last_name": "Mittal",
                "role": User.Role.RECRUITER
            }
        )
        if not recruiter.first_name:
            recruiter.first_name = "Nikhil"
            recruiter.last_name = "Mittal"
            recruiter.save()
        account = RecruiterEmailAccount.objects.create(
            recruiter=recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address="nikhil@2020technologies.in",
            oauth_access_token="nikhil_token_999",
            is_verified=True,
            is_default=True
        )

        # Confirm get_required_alias() returns profiles@2020technologies.in
        self.assertEqual(account.get_required_alias(), "profiles@2020technologies.in")
        self.assertEqual(account.get_sending_email_address(), "profiles@2020technologies.in")

        # Scenario A: profiles@2020technologies.in is MISSING
        mock_resp_missing = MagicMock()
        mock_resp_missing.status_code = 200
        mock_resp_missing.json.return_value = {
            "sendAs": [
                {
                    "sendAsEmail": "nikhil@2020technologies.in",
                    "isPrimary": True,
                    "verificationStatus": "accepted"
                }
            ]
        }
        mock_requests_get.return_value = mock_resp_missing

        is_verified, err_msg = account.verify_sendas_alias()
        self.assertFalse(is_verified)
        self.assertIn("profiles@2020technologies.in", err_msg)

        # Scenario B: profiles@2020technologies.in is PRESENT and accepted
        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {
            "sendAs": [
                {
                    "sendAsEmail": "nikhil@2020technologies.in",
                    "isPrimary": True,
                    "verificationStatus": "accepted"
                },
                {
                    "sendAsEmail": "profiles@2020technologies.in",
                    "verificationStatus": "accepted"
                }
            ]
        }
        mock_requests_get.return_value = mock_resp_ok

        is_verified, err_msg = account.verify_sendas_alias()
        self.assertTrue(is_verified)
        self.assertIsNone(err_msg)

    @patch("requests.post")
    @patch("requests.get")
    def test_nikhil_send_ats_email_headers_and_sent_folder(
        self, mock_requests_get, mock_requests_post
    ):
        """
        Nikhil's company mailbox sending:
        - From: Nikhil Mittal <profiles@2020technologies.in>
        - Reply-To: nikhil@2020technologies.in
        - Gmail API users.messages.send called with Nikhil's token.
        """
        recruiter, _ = User.objects.get_or_create(
            email="nikhil@2020technologies.in",
            defaults={
                "first_name": "Nikhil",
                "last_name": "Mittal",
                "role": User.Role.RECRUITER
            }
        )
        if not recruiter.first_name:
            recruiter.first_name = "Nikhil"
            recruiter.last_name = "Mittal"
            recruiter.save()
        account = RecruiterEmailAccount.objects.create(
            recruiter=recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address="nikhil@2020technologies.in",
            oauth_access_token="nikhil_access_token_token",
            is_verified=True,
            is_default=True
        )

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "sendAs": [
                {
                    "sendAsEmail": "nikhil@2020technologies.in",
                    "isPrimary": True,
                    "verificationStatus": "accepted"
                },
                {
                    "sendAsEmail": "profiles@2020technologies.in",
                    "verificationStatus": "accepted"
                }
            ]
        }
        mock_requests_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "id": "msg_nikhil_sent_999",
            "labelIds": ["SENT"]
        }
        mock_requests_post.return_value = mock_post_resp

        email_log, success, msg = send_ats_email(
            sender=recruiter,
            recipient_email="client@acme.com",
            subject="Candidate Profile Submission",
            body="Hi Acme,\nPlease find attached candidate profile.",
            email_account=account
        )

        self.assertTrue(success)
        self.assertEqual(email_log.status, "SENT")

        # Inspect Gmail API call
        mock_requests_post.assert_called_once()
        called_url, called_kwargs = mock_requests_post.call_args
        self.assertEqual(called_url[0], "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")
        self.assertEqual(
            called_kwargs["headers"]["Authorization"],
            "Bearer nikhil_access_token_token"
        )

        # Decode raw MIME message to inspect exact headers
        raw_b64 = called_kwargs["json"]["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
        parsed_email = email.message_from_bytes(raw_bytes, policy=policy.default)

        # From: Nikhil Mittal <profiles@2020technologies.in>
        # Reply-To: nikhil@2020technologies.in
        self.assertEqual(parsed_email["From"], "Nikhil Mittal <profiles@2020technologies.in>")
        self.assertEqual(parsed_email["Reply-To"], "nikhil@2020technologies.in")
        self.assertEqual(parsed_email["To"], "client@acme.com")

    # -------------------------------------------------------------------------
    # UNRELATED RECRUITER ACCOUNTS (TECHNICAL REQUIREMENT 2)
    # -------------------------------------------------------------------------

    @patch("requests.post")
    @patch("requests.get")
    def test_unrelated_recruiter_account_never_requires_nikhil_alias(
        self, mock_requests_get, mock_requests_post
    ):
        """
        Unrelated recruiter account (e.g. sarah@talentagency.com):
        - Never requires profiles@2020technologies.in.
        - From: Sarah Jenkins <sarah@talentagency.com>
        - Reply-To: sarah@talentagency.com
        """
        recruiter = User.objects.create_user(
            email="sarah@talentagency.com",
            first_name="Sarah",
            last_name="Jenkins",
            password="Password123!",
            role=User.Role.RECRUITER
        )
        account = RecruiterEmailAccount.objects.create(
            recruiter=recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address="sarah@talentagency.com",
            oauth_access_token="sarah_token_xyz",
            is_verified=True,
            is_default=True
        )

        # Confirm no alias required
        self.assertIsNone(account.get_required_alias())
        self.assertEqual(account.get_sending_email_address(), "sarah@talentagency.com")

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "sendAs": [{
                "sendAsEmail": "sarah@talentagency.com",
                "isPrimary": True,
                "verificationStatus": "accepted"
            }]
        }
        mock_requests_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"id": "sarah_msg_id"}
        mock_requests_post.return_value = mock_post_resp

        email_log, success, msg = send_ats_email(
            sender=recruiter,
            recipient_email="hiring@startup.io",
            subject="Great Candidate for you",
            body="Take a look at this candidate.",
            email_account=account
        )

        self.assertTrue(success)

        raw_b64 = mock_requests_post.call_args[1]["json"]["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
        parsed_email = email.message_from_bytes(raw_bytes, policy=policy.default)

        self.assertEqual(parsed_email["From"], "Sarah Jenkins <sarah@talentagency.com>")
        self.assertEqual(parsed_email["Reply-To"], "sarah@talentagency.com")
        self.assertNotIn("profiles@2020technologies.in", parsed_email["From"])

    # -------------------------------------------------------------------------
    # OAUTH CALLBACK PER-MAILBOX MESSAGES
    # -------------------------------------------------------------------------

    @patch("requests.post")
    @patch("requests.get")
    def test_oauth_callback_growfluence_succeeds_without_alias_warning(
        self, mock_requests_get, mock_requests_post
    ):
        """
        When Growfluence completes OAuth callback:
        - Scopes gmail.send and gmail.settings.basic verified.
        - Primary address verified in sendAs.
        - Success message does NOT mention profiles@2020technologies.in.
        """
        recruiter, _ = User.objects.get_or_create(
            email="growfluencestudio@gmail.com",
            defaults={
                "first_name": "Growfluence",
                "last_name": "Studio",
                "role": User.Role.RECRUITER
            }
        )
        if not recruiter.first_name:
            recruiter.first_name = "Growfluence"
            recruiter.last_name = "Studio"
            recruiter.save()
        client = Client()
        client.force_login(recruiter)

        session = client.session
        session["gmail_oauth_state"] = "growfluence_state_123"
        session["gmail_oauth_recruiter_id"] = str(recruiter.id)
        session["gmail_oauth_expected_email"] = "growfluencestudio@gmail.com"
        session.save()

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "growfluence_oauth_token",
            "refresh_token": "growfluence_refresh_token",
            "expires_in": 3600,
            "scope": (
                "https://www.googleapis.com/auth/gmail.send "
                "https://www.googleapis.com/auth/gmail.settings.basic openid"
            )
        }
        mock_requests_post.return_value = mock_token_resp

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "userinfo" in url:
                resp.status_code = 200
                resp.json.return_value = {"email": "growfluencestudio@gmail.com"}
            elif "sendAs" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "sendAs": [{
                        "sendAsEmail": "growfluencestudio@gmail.com",
                        "isPrimary": True,
                        "verificationStatus": "accepted"
                    }]
                }
            return resp

        mock_requests_get.side_effect = get_side_effect

        callback_url = reverse("notifications:recruiter_gmail_oauth_callback")
        response = client.get(callback_url, {
            "code": "growfluence_auth_code",
            "state": "growfluence_state_123"
        })

        self.assertEqual(response.status_code, 302)
        account = RecruiterEmailAccount.objects.get(
            recruiter=recruiter, email_address="growfluencestudio@gmail.com"
        )
        self.assertTrue(account.is_verified)

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Successfully connected" in str(m) for m in msgs))
        self.assertFalse(any("profiles@2020technologies.in" in str(m) for m in msgs))
