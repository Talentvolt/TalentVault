import uuid
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.messages import get_messages

from apps.accounts.models import User
from apps.notifications.models import RecruiterEmailAccount
from apps.notifications.views import (
    verify_recruiter_gmail_scopes,
    parse_oauth_scopes,
    RECRUITER_GMAIL_REQUIRED_SCOPES,
)


class RecruiterGmailScopeAndVerificationTests(TestCase):
    """
    Focused test suite verifying:
    1. Authorization URL explicitly requests:
       - https://www.googleapis.com/auth/gmail.send
       - https://www.googleapis.com/auth/gmail.settings.basic
       along with access_type=offline, prompt=consent, and include_granted_scopes=true.
    2. Uses RECRUITER_GMAIL_OAUTH_CLIENT_ID and SECRET only.
    3. Verifies actual granted scopes before marking account or alias verified.
    4. Missing-scope handling (e.g. gmail.settings.basic missing, or gmail.send missing):
       - Account is NOT marked verified (is_verified=False).
       - Alias is NOT verified.
       - User receives clear error message.
    5. Existing refresh token is preserved if Google omits refresh_token in response.
    6. verify_sendas_alias 403 response marks account is_verified=False.
    """

    RECRUITER_CLIENT_ID = "recruiter-gmail-id-xyz.apps.googleusercontent.com"
    RECRUITER_CLIENT_SECRET = "recruiter-gmail-secret-secret"
    NORMAL_LOGIN_CLIENT_ID = "normal-login-id.apps.googleusercontent.com"
    NORMAL_LOGIN_CLIENT_SECRET = "normal-login-secret"
    EXPECTED_CALLBACK_URL = "https://talent-vault.in/notifications/oauth/gmail/callback/"

    def setUp(self):
        self.recruiter_email = f"recruiter_{uuid.uuid4().hex[:6]}@2020technologies.in"
        self.recruiter = User.objects.create_user(
            email=self.recruiter_email,
            first_name="Garima",
            last_name="Recruiter",
            password="SecurePassword123!",
            role=User.Role.RECRUITER,
        )

        self.client_session = Client()
        self.client_session.force_login(self.recruiter)

        self.env_patcher = patch.dict("os.environ", {
            "RECRUITER_GMAIL_OAUTH_CLIENT_ID": self.RECRUITER_CLIENT_ID,
            "RECRUITER_GMAIL_OAUTH_CLIENT_SECRET": self.RECRUITER_CLIENT_SECRET,
            "RECRUITER_GMAIL_OAUTH_CALLBACK_URL": self.EXPECTED_CALLBACK_URL,
            "GOOGLE_CLIENT_ID": self.NORMAL_LOGIN_CLIENT_ID,
            "GOOGLE_CLIENT_SECRET": self.NORMAL_LOGIN_CLIENT_SECRET,
        })
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

        self.settings_patcher = patch.multiple(
            "django.conf.settings",
            RECRUITER_GMAIL_OAUTH_CLIENT_ID=self.RECRUITER_CLIENT_ID,
            RECRUITER_GMAIL_OAUTH_CLIENT_SECRET=self.RECRUITER_CLIENT_SECRET,
            RECRUITER_GMAIL_OAUTH_CALLBACK_URL=self.EXPECTED_CALLBACK_URL,
            GOOGLE_CLIENT_ID=self.NORMAL_LOGIN_CLIENT_ID,
            GOOGLE_CLIENT_SECRET=self.NORMAL_LOGIN_CLIENT_SECRET,
        )
        self.settings_patcher.start()
        self.addCleanup(self.settings_patcher.stop)

    def test_oauth_start_requests_explicit_gmail_scopes_and_consent_params(self):
        """
        Verify that hitting recruiter Gmail OAuth start:
        1. Requests both https://www.googleapis.com/auth/gmail.send and
           https://www.googleapis.com/auth/gmail.settings.basic.
        2. Includes access_type=offline, prompt=consent, and include_granted_scopes=true.
        3. Uses RECRUITER_GMAIL_OAUTH_CLIENT_ID exclusively.
        """
        url = reverse("notifications:recruiter_gmail_oauth_start")
        response = self.client_session.get(url, {"email_address": self.recruiter.email})

        self.assertEqual(response.status_code, 302)
        parsed = urlparse(response.url)
        params = parse_qs(parsed.query)

        # Credentials: recruiter-only
        self.assertEqual(params.get("client_id"), [self.RECRUITER_CLIENT_ID])
        self.assertNotEqual(params.get("client_id"), [self.NORMAL_LOGIN_CLIENT_ID])

        # Required OAuth parameters
        self.assertEqual(params.get("response_type"), ["code"])
        self.assertEqual(params.get("access_type"), ["offline"])
        self.assertEqual(params.get("prompt"), ["consent"])
        self.assertEqual(params.get("include_granted_scopes"), ["true"])
        self.assertEqual(params.get("redirect_uri"), [self.EXPECTED_CALLBACK_URL])

        # Scopes: must explicitly include both gmail.send and gmail.settings.basic
        scope_str = params.get("scope", [""])[0]
        scopes = scope_str.split(" ")
        self.assertIn("https://www.googleapis.com/auth/gmail.send", scopes)
        self.assertIn("https://www.googleapis.com/auth/gmail.settings.basic", scopes)

    @patch("requests.post")
    @patch("requests.get")
    def test_callback_success_when_all_required_scopes_granted(
        self, mock_requests_get, mock_requests_post
    ):
        """
        When token endpoint returns both gmail.send and gmail.settings.basic:
        1. Account is marked is_verified=True.
        2. Alias verification is executed.
        3. Success message is added.
        """
        session = self.client_session.session
        session["gmail_oauth_state"] = "state_all_scopes_valid"
        session["gmail_oauth_recruiter_id"] = str(self.recruiter.id)
        session["gmail_oauth_expected_email"] = self.recruiter.email
        session.save()

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "valid_token_all_scopes",
            "refresh_token": "valid_refresh_token_all_scopes",
            "expires_in": 3600,
            "scope": (
                "https://www.googleapis.com/auth/gmail.send "
                "https://www.googleapis.com/auth/gmail.settings.basic "
                "openid email profile"
            ),
        }
        mock_requests_post.return_value = mock_token_resp

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "userinfo" in url:
                resp.status_code = 200
                resp.json.return_value = {"email": self.recruiter.email}
            elif "sendAs" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "sendAs": [{
                        "sendAsEmail": "profiles@2020technologies.in",
                        "verificationStatus": "accepted"
                    }]
                }
            return resp

        mock_requests_get.side_effect = get_side_effect

        callback_url = reverse("notifications:recruiter_gmail_oauth_callback")
        response = self.client_session.get(callback_url, {
            "code": "test_auth_code_ok",
            "state": "state_all_scopes_valid",
        })

        self.assertEqual(response.status_code, 302)
        account = RecruiterEmailAccount.objects.get(
            recruiter=self.recruiter, email_address=self.recruiter.email
        )
        self.assertTrue(account.is_verified)
        self.assertEqual(account.oauth_access_token, "valid_token_all_scopes")
        self.assertEqual(account.oauth_refresh_token, "valid_refresh_token_all_scopes")

        # Success message
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Successfully connected" in str(m) for m in msgs))

    @patch("requests.post")
    @patch("requests.get")
    def test_callback_fails_verification_when_settings_basic_scope_missing(
        self, mock_requests_get, mock_requests_post
    ):
        """
        Live error scenario reproduction:
        Google connects successfully and grants gmail.send, but gmail.settings.basic
        is NOT granted.
        1. Account MUST NOT be marked verified (is_verified=False).
        2. Alias verification must NOT mark alias verified.
        3. Clear error message specifying missing gmail.settings.basic is delivered.
        """
        session = self.client_session.session
        session["gmail_oauth_state"] = "state_missing_settings"
        session["gmail_oauth_recruiter_id"] = str(self.recruiter.id)
        session["gmail_oauth_expected_email"] = self.recruiter.email
        session.save()

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        # Notice: only gmail.send, gmail.settings.basic is omitted
        mock_token_resp.json.return_value = {
            "access_token": "token_lacking_settings_basic",
            "refresh_token": "refresh_token_abc",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.send openid email profile",
        }
        mock_requests_post.return_value = mock_token_resp

        mock_userinfo = MagicMock()
        mock_userinfo.status_code = 200
        mock_userinfo.json.return_value = {"email": self.recruiter.email}
        mock_requests_get.return_value = mock_userinfo

        callback_url = reverse("notifications:recruiter_gmail_oauth_callback")
        response = self.client_session.get(callback_url, {
            "code": "test_auth_code_partial",
            "state": "state_missing_settings",
        })

        self.assertEqual(response.status_code, 302)
        account = RecruiterEmailAccount.objects.get(
            recruiter=self.recruiter, email_address=self.recruiter.email
        )
        # MUST NOT BE VERIFIED
        self.assertFalse(account.is_verified)

        # Error message delivered to user
        msgs = list(get_messages(response.wsgi_request))
        error_msgs = [str(m) for m in msgs if m.level_tag == "error"]
        self.assertTrue(len(error_msgs) > 0)
        self.assertIn("gmail.settings.basic", error_msgs[0])

    @patch("requests.post")
    @patch("requests.get")
    def test_callback_fails_verification_when_gmail_send_scope_missing(
        self, mock_requests_get, mock_requests_post
    ):
        """
        When gmail.send is missing from granted scopes:
        1. Account MUST NOT be marked verified (is_verified=False).
        2. Error message delivered specifying missing gmail.send.
        """
        session = self.client_session.session
        session["gmail_oauth_state"] = "state_missing_send"
        session["gmail_oauth_recruiter_id"] = str(self.recruiter.id)
        session.save()

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "token_lacking_send",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.settings.basic openid email profile",
        }
        mock_requests_post.return_value = mock_token_resp

        mock_userinfo = MagicMock()
        mock_userinfo.status_code = 200
        mock_userinfo.json.return_value = {"email": self.recruiter.email}
        mock_requests_get.return_value = mock_userinfo

        callback_url = reverse("notifications:recruiter_gmail_oauth_callback")
        response = self.client_session.get(callback_url, {
            "code": "test_auth_code_no_send",
            "state": "state_missing_send",
        })

        self.assertEqual(response.status_code, 302)
        account = RecruiterEmailAccount.objects.get(
            recruiter=self.recruiter, email_address=self.recruiter.email
        )
        self.assertFalse(account.is_verified)

        msgs = list(get_messages(response.wsgi_request))
        error_msgs = [str(m) for m in msgs if m.level_tag == "error"]
        self.assertTrue(len(error_msgs) > 0)
        self.assertIn("gmail.send", error_msgs[0])

    @patch("requests.post")
    @patch("requests.get")
    def test_callback_fails_when_all_gmail_scopes_missing(
        self, mock_requests_get, mock_requests_post
    ):
        """
        When only profile/email is granted (no Gmail scopes at all):
        Account is saved as unverified with error message listing both missing scopes.
        """
        session = self.client_session.session
        session["gmail_oauth_state"] = "state_no_gmail_scopes"
        session["gmail_oauth_recruiter_id"] = str(self.recruiter.id)
        session.save()

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "token_no_gmail",
            "expires_in": 3600,
            "scope": "openid email profile",
        }
        mock_requests_post.return_value = mock_token_resp

        mock_userinfo = MagicMock()
        mock_userinfo.status_code = 200
        mock_userinfo.json.return_value = {"email": self.recruiter.email}
        mock_requests_get.return_value = mock_userinfo

        callback_url = reverse("notifications:recruiter_gmail_oauth_callback")
        response = self.client_session.get(callback_url, {
            "code": "test_code_no_gmail",
            "state": "state_no_gmail_scopes",
        })

        self.assertEqual(response.status_code, 302)
        account = RecruiterEmailAccount.objects.get(
            recruiter=self.recruiter, email_address=self.recruiter.email
        )
        self.assertFalse(account.is_verified)

        msgs = list(get_messages(response.wsgi_request))
        error_msgs = [str(m) for m in msgs if m.level_tag == "error"]
        self.assertTrue(len(error_msgs) > 0)
        self.assertIn("gmail.send", error_msgs[0])
        self.assertIn("gmail.settings.basic", error_msgs[0])

    @patch("requests.post")
    @patch("requests.get")
    def test_callback_preserves_existing_refresh_token_when_google_omits_new_token(
        self, mock_requests_get, mock_requests_post
    ):
        """
        Verify existing refresh token is preserved across callbacks when Google
        omits refresh_token on re-authorization.
        """
        account = RecruiterEmailAccount.objects.create(
            recruiter=self.recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address=self.recruiter.email,
            oauth_access_token="old_access_token",
            oauth_refresh_token="precious_existing_refresh_token_123",
            is_verified=True,
            is_default=True,
        )

        session = self.client_session.session
        session["gmail_oauth_state"] = "state_preserve_refresh_token"
        session["gmail_oauth_recruiter_id"] = str(self.recruiter.id)
        session.save()

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "new_access_token_only",
            "expires_in": 3600,
            "scope": (
                "https://www.googleapis.com/auth/gmail.send "
                "https://www.googleapis.com/auth/gmail.settings.basic openid"
            ),
        }
        mock_requests_post.return_value = mock_token_resp

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "userinfo" in url:
                resp.status_code = 200
                resp.json.return_value = {"email": self.recruiter.email}
            elif "sendAs" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "sendAs": [{
                        "sendAsEmail": "profiles@2020technologies.in",
                        "verificationStatus": "accepted"
                    }]
                }
            return resp

        mock_requests_get.side_effect = get_side_effect

        callback_url = reverse("notifications:recruiter_gmail_oauth_callback")
        response = self.client_session.get(callback_url, {
            "code": "new_code_no_refresh",
            "state": "state_preserve_refresh_token",
        })

        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertEqual(account.oauth_access_token, "new_access_token_only")
        self.assertEqual(account.oauth_refresh_token, "precious_existing_refresh_token_123")
        self.assertTrue(account.is_verified)

    @patch("requests.post")
    @patch("requests.get")
    def test_callback_preserves_refresh_token_even_when_scopes_missing(
        self, mock_requests_get, mock_requests_post
    ):
        """
        If a reconnect is attempted with missing scopes, the existing refresh_token
        is still preserved in the account record (marked is_verified=False).
        """
        account = RecruiterEmailAccount.objects.create(
            recruiter=self.recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address=self.recruiter.email,
            oauth_access_token="old_access_token",
            oauth_refresh_token="keep_this_token_always",
            is_verified=True,
            is_default=True,
        )

        session = self.client_session.session
        session["gmail_oauth_state"] = "state_partial_scope_preserve"
        session["gmail_oauth_recruiter_id"] = str(self.recruiter.id)
        session.save()

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "new_token_missing_scope",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.send openid",
        }
        mock_requests_post.return_value = mock_token_resp

        mock_userinfo = MagicMock()
        mock_userinfo.status_code = 200
        mock_userinfo.json.return_value = {"email": self.recruiter.email}
        mock_requests_get.return_value = mock_userinfo

        callback_url = reverse("notifications:recruiter_gmail_oauth_callback")
        response = self.client_session.get(callback_url, {
            "code": "new_code_missing_scope",
            "state": "state_partial_scope_preserve",
        })

        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertEqual(account.oauth_refresh_token, "keep_this_token_always")
        self.assertFalse(account.is_verified)

    @patch("requests.get")
    def test_verify_sendas_alias_403_unverifies_account(self, mock_requests_get):
        """
        When verify_sendas_alias encounters HTTP 403 Forbidden (missing gmail.settings.basic):
        1. Returns (False, error_msg)
        2. Sets account.is_verified = False in database.
        """
        account = RecruiterEmailAccount.objects.create(
            recruiter=self.recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address=self.recruiter.email,
            oauth_access_token="access_token_403_test",
            oauth_refresh_token="refresh_token_test",
            is_verified=True,
            is_default=True,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden - Insufficient Permission"
        mock_requests_get.return_value = mock_resp

        is_verified, err_msg = account.verify_sendas_alias("profiles@2020technologies.in")

        self.assertFalse(is_verified)
        self.assertIn("gmail.settings.basic", err_msg)
        account.refresh_from_db()
        self.assertFalse(account.is_verified)

    @patch("requests.post")
    def test_refresh_access_token_uses_recruiter_credentials_only(self, mock_requests_post):
        """
        Verify token refresh uses RECRUITER_GMAIL_OAUTH_CLIENT_ID and SECRET only.
        If recruiter credentials are removed, refresh refuses to fall back to normal
        Google Login credentials and returns False.
        """
        account = RecruiterEmailAccount.objects.create(
            recruiter=self.recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address=self.recruiter.email,
            oauth_access_token="old_access_token",
            oauth_refresh_token="my_refresh_token",
            is_verified=True,
            is_default=True,
        )

        with patch("django.conf.settings.RECRUITER_GMAIL_OAUTH_CLIENT_ID", ""), \
             patch("django.conf.settings.RECRUITER_GMAIL_OAUTH_CLIENT_SECRET", ""), \
             patch.dict("os.environ", {
                 "RECRUITER_GMAIL_OAUTH_CLIENT_ID": "",
                 "RECRUITER_GMAIL_OAUTH_CLIENT_SECRET": "",
                 "GOOGLE_CLIENT_ID": self.NORMAL_LOGIN_CLIENT_ID,
                 "GOOGLE_CLIENT_SECRET": self.NORMAL_LOGIN_CLIENT_SECRET,
             }):
            success = account.refresh_access_token()
            self.assertFalse(success)
            mock_requests_post.assert_not_called()

    def test_scope_parser_and_verifier_helpers(self):
        """
        Unit test the scope parsing and verification helper functions for various inputs.
        """
        # Full Google mail scope satisfies both send and settings
        valid_full, missing = verify_recruiter_gmail_scopes("https://mail.google.com/ email")
        self.assertTrue(valid_full)
        self.assertEqual(missing, [])

        # Both exact scopes
        valid_both, missing = verify_recruiter_gmail_scopes(
            "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.settings.basic"
        )
        self.assertTrue(valid_both)
        self.assertEqual(missing, [])

        # Comma delimited
        valid_comma, missing = verify_recruiter_gmail_scopes(
            "https://www.googleapis.com/auth/gmail.send, https://www.googleapis.com/auth/gmail.settings.basic"
        )
        self.assertTrue(valid_comma)
        self.assertEqual(missing, [])

        # Missing settings
        valid_no_settings, missing = verify_recruiter_gmail_scopes("https://www.googleapis.com/auth/gmail.send")
        self.assertFalse(valid_no_settings)
        self.assertEqual(missing, ["https://www.googleapis.com/auth/gmail.settings.basic"])

        # Missing send
        valid_no_send, missing = verify_recruiter_gmail_scopes("https://www.googleapis.com/auth/gmail.settings.basic")
        self.assertFalse(valid_no_send)
        self.assertEqual(missing, ["https://www.googleapis.com/auth/gmail.send"])

        # Empty
        valid_empty, missing = verify_recruiter_gmail_scopes("")
        self.assertFalse(valid_empty)
        self.assertEqual(len(missing), 2)
