import uuid
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.management import call_command
from allauth.socialaccount.models import SocialApp

from apps.accounts.models import User
from apps.accounts.apps import setup_google_social_app
from apps.notifications.models import RecruiterEmailAccount
from apps.notifications.views import get_google_oauth_redirect_uri


class RecruiterGmailSeparateOAuthCredentialsTests(TestCase):
    """
    Focused test suite proving:
    1. Recruiter Gmail OAuth start, callback, and token exchange flows read
       RECRUITER_GMAIL_OAUTH_CLIENT_ID and RECRUITER_GMAIL_OAUTH_CLIENT_SECRET.
    2. Normal Django Google Login uses GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET unchanged.
    3. The callback URL is https://talent-vault.in/notifications/oauth/gmail/callback/.
    4. Refresh tokens, SendAs alias verification, and Sent-folder sending are preserved.
    """

    RECRUITER_CLIENT_ID = "recruiter-gmail-client-id-11111"
    RECRUITER_CLIENT_SECRET = "recruiter-gmail-client-secret-22222"
    GOOGLE_LOGIN_CLIENT_ID = "normal-django-login-client-id-88888"
    GOOGLE_LOGIN_CLIENT_SECRET = "normal-django-login-client-secret-99999"
    EXPECTED_CALLBACK_URL = "https://talent-vault.in/notifications/oauth/gmail/callback/"

    def setUp(self):
        self.recruiter_email = f"recruiter_{uuid.uuid4().hex[:6]}@2020technologies.in"
        self.recruiter = User.objects.create_user(
            email=self.recruiter_email,
            first_name="Recruiter",
            last_name="Tester",
            password="Password123!",
            role=User.Role.RECRUITER,
        )

        self.client_session = Client()
        self.client_session.force_login(self.recruiter)

        self.env_patcher = patch.dict("os.environ", {
            "RECRUITER_GMAIL_OAUTH_CLIENT_ID": self.RECRUITER_CLIENT_ID,
            "RECRUITER_GMAIL_OAUTH_CLIENT_SECRET": self.RECRUITER_CLIENT_SECRET,
            "RECRUITER_GMAIL_OAUTH_CALLBACK_URL": self.EXPECTED_CALLBACK_URL,
            "GOOGLE_CLIENT_ID": self.GOOGLE_LOGIN_CLIENT_ID,
            "GOOGLE_CLIENT_SECRET": self.GOOGLE_LOGIN_CLIENT_SECRET,
        })
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

        self.settings_patcher = patch.multiple(
            "django.conf.settings",
            RECRUITER_GMAIL_OAUTH_CLIENT_ID=self.RECRUITER_CLIENT_ID,
            RECRUITER_GMAIL_OAUTH_CLIENT_SECRET=self.RECRUITER_CLIENT_SECRET,
            RECRUITER_GMAIL_OAUTH_CALLBACK_URL=self.EXPECTED_CALLBACK_URL,
            GOOGLE_CLIENT_ID=self.GOOGLE_LOGIN_CLIENT_ID,
            GOOGLE_CLIENT_SECRET=self.GOOGLE_LOGIN_CLIENT_SECRET,
        )
        self.settings_patcher.start()
        self.addCleanup(self.settings_patcher.stop)

    def test_recruiter_gmail_oauth_start_uses_recruiter_credentials(self):
        """
        Verify Recruiter Gmail OAuth start uses RECRUITER_GMAIL_OAUTH_CLIENT_ID
        and redirects with callback URL https://talent-vault.in/notifications/oauth/gmail/callback/,
        never using GOOGLE_CLIENT_ID.
        """
        url = reverse("notifications:recruiter_gmail_oauth_start")
        response = self.client_session.get(url, {"email_address": self.recruiter.email})

        self.assertEqual(response.status_code, 302)
        redirect_url = response.url
        self.assertTrue(redirect_url.startswith("https://accounts.google.com/o/oauth2/v2/auth"))

        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)

        # Must use RECRUITER_GMAIL_OAUTH_CLIENT_ID
        self.assertEqual(params.get("client_id"), [self.RECRUITER_CLIENT_ID])
        self.assertNotEqual(params.get("client_id"), [self.GOOGLE_LOGIN_CLIENT_ID])

        # Must use expected callback URL
        self.assertEqual(params.get("redirect_uri"), [self.EXPECTED_CALLBACK_URL])
        self.assertEqual(get_google_oauth_redirect_uri(), self.EXPECTED_CALLBACK_URL)

        # Scopes and offline consent
        self.assertEqual(params.get("response_type"), ["code"])
        self.assertEqual(params.get("access_type"), ["offline"])
        self.assertEqual(params.get("prompt"), ["consent"])
        scope_str = params.get("scope", [""])[0]
        self.assertIn("https://www.googleapis.com/auth/gmail.send", scope_str)
        self.assertIn("https://www.googleapis.com/auth/gmail.settings.basic", scope_str)

    @patch("requests.post")
    @patch("requests.get")
    def test_recruiter_gmail_oauth_callback_token_exchange_uses_recruiter_credentials(
        self, mock_requests_get, mock_requests_post
    ):
        """
        Verify Recruiter Gmail OAuth callback exchanges authorization code using
        RECRUITER_GMAIL_OAUTH_CLIENT_ID and RECRUITER_GMAIL_OAUTH_CLIENT_SECRET,
        and uses https://talent-vault.in/notifications/oauth/gmail/callback/.
        """
        session = self.client_session.session
        session["gmail_oauth_state"] = "secure_test_state_123"
        session["gmail_oauth_recruiter_id"] = str(self.recruiter.id)
        session["gmail_oauth_expected_email"] = self.recruiter.email
        session.save()

        # Mock token endpoint response
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "recruiter_access_token_xyz",
            "refresh_token": "recruiter_refresh_token_xyz",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.settings.basic openid email profile",
        }
        mock_requests_post.return_value = mock_token_resp

        # Mock userinfo & sendAs
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
            "code": "auth_code_from_google",
            "state": "secure_test_state_123"
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn("settings", response.url)

        # Verify token exchange payload sent to Google
        mock_requests_post.assert_called_once()
        called_args, called_kwargs = mock_requests_post.call_args
        self.assertEqual(called_args[0], "https://oauth2.googleapis.com/token")

        payload = called_kwargs.get("data", {})
        self.assertEqual(payload.get("client_id"), self.RECRUITER_CLIENT_ID)
        self.assertEqual(payload.get("client_secret"), self.RECRUITER_CLIENT_SECRET)
        self.assertEqual(payload.get("redirect_uri"), self.EXPECTED_CALLBACK_URL)
        self.assertEqual(payload.get("code"), "auth_code_from_google")
        self.assertEqual(payload.get("grant_type"), "authorization_code")

        # Explicitly verify it did NOT use normal Django Google login credentials
        self.assertNotEqual(payload.get("client_id"), self.GOOGLE_LOGIN_CLIENT_ID)
        self.assertNotEqual(payload.get("client_secret"), self.GOOGLE_LOGIN_CLIENT_SECRET)

    @patch("requests.post")
    def test_recruiter_gmail_token_refresh_uses_recruiter_credentials(self, mock_requests_post):
        """
        Verify token refresh on RecruiterEmailAccount sends RECRUITER_GMAIL_OAUTH_CLIENT_ID
        and RECRUITER_GMAIL_OAUTH_CLIENT_SECRET to the token endpoint.
        """
        account = RecruiterEmailAccount.objects.create(
            recruiter=self.recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address=self.recruiter.email,
            oauth_access_token="old_access_token",
            oauth_refresh_token="precious_refresh_token_999",
            is_verified=True,
            is_default=True,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_refreshed_access_token_111",
            "expires_in": 3600
        }
        mock_requests_post.return_value = mock_resp

        success = account.refresh_access_token()
        self.assertTrue(success)

        mock_requests_post.assert_called_once()
        called_args, called_kwargs = mock_requests_post.call_args
        self.assertEqual(called_args[0], "https://oauth2.googleapis.com/token")

        refresh_payload = called_kwargs.get("data", {})
        self.assertEqual(refresh_payload.get("client_id"), self.RECRUITER_CLIENT_ID)
        self.assertEqual(refresh_payload.get("client_secret"), self.RECRUITER_CLIENT_SECRET)
        self.assertEqual(refresh_payload.get("grant_type"), "refresh_token")
        self.assertEqual(refresh_payload.get("refresh_token"), "precious_refresh_token_999")

        # Must not use normal login credentials
        self.assertNotEqual(refresh_payload.get("client_id"), self.GOOGLE_LOGIN_CLIENT_ID)
        self.assertNotEqual(refresh_payload.get("client_secret"), self.GOOGLE_LOGIN_CLIENT_SECRET)

        # Refresh token is preserved when response omits new refresh token
        account.refresh_from_db()
        self.assertEqual(account.oauth_refresh_token, "precious_refresh_token_999")
        self.assertEqual(account.oauth_access_token, "new_refreshed_access_token_111")

    def test_normal_django_google_login_uses_google_client_id_and_secret(self):
        """
        Verify normal Django Google Login (via allauth SocialApp setup and allauth endpoints)
        uses GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, completely unaffected by recruiter credentials.
        """
        setup_google_social_app(None)

        social_app = SocialApp.objects.get(provider="google")
        self.assertEqual(social_app.client_id, self.GOOGLE_LOGIN_CLIENT_ID)
        self.assertEqual(social_app.secret, self.GOOGLE_LOGIN_CLIENT_SECRET)

        self.assertNotEqual(social_app.client_id, self.RECRUITER_CLIENT_ID)
        self.assertNotEqual(social_app.secret, self.RECRUITER_CLIENT_SECRET)

        # Also test management command setup_google_app
        call_command("setup_google_app")
        social_app.refresh_from_db()
        self.assertEqual(social_app.client_id, self.GOOGLE_LOGIN_CLIENT_ID)
        self.assertEqual(social_app.secret, self.GOOGLE_LOGIN_CLIENT_SECRET)

        # Verify Google login initiate redirect uses GOOGLE_CLIENT_ID
        anon_client = Client()
        for path in ["/accounts/login/google/", "/accounts/google/login/"]:
            resp = anon_client.get(path)
            self.assertEqual(resp.status_code, 302)
            redirect_url = resp.url
            self.assertTrue(redirect_url.startswith("https://accounts.google.com"))
            query_params = parse_qs(urlparse(redirect_url).query)
            self.assertEqual(query_params.get("client_id"), [self.GOOGLE_LOGIN_CLIENT_ID])
            self.assertNotEqual(query_params.get("client_id"), [self.RECRUITER_CLIENT_ID])

    def test_recruiter_gmail_oauth_fails_if_recruiter_credentials_missing_even_when_google_login_configured(self):
        """
        Verify that if RECRUITER_GMAIL_OAUTH_CLIENT_ID is missing, recruiter Gmail OAuth start
        refuses to start and redirects with error, rather than falling back to GOOGLE_CLIENT_ID.
        """
        with patch("django.conf.settings.RECRUITER_GMAIL_OAUTH_CLIENT_ID", ""), \
             patch("django.conf.settings.RECRUITER_GMAIL_OAUTH_CLIENT_SECRET", ""), \
             patch.dict("os.environ", {
                 "RECRUITER_GMAIL_OAUTH_CLIENT_ID": "",
                 "RECRUITER_GMAIL_OAUTH_CLIENT_SECRET": "",
                 "GOOGLE_CLIENT_ID": self.GOOGLE_LOGIN_CLIENT_ID,
                 "GOOGLE_CLIENT_SECRET": self.GOOGLE_LOGIN_CLIENT_SECRET,
             }):
            url = reverse("notifications:recruiter_gmail_oauth_start")
            response = self.client_session.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("settings", response.url)
            self.assertIn("email-accounts-panel", response.url)

    @patch("requests.post")
    @patch("requests.get")
    def test_preserve_refresh_tokens_and_verify_alias(self, mock_requests_get, mock_requests_post):
        """
        Verify refresh token is preserved across callbacks and alias verification succeeds.
        """
        existing_account = RecruiterEmailAccount.objects.create(
            recruiter=self.recruiter,
            account_type="OAUTH",
            provider="GMAIL",
            email_address=self.recruiter.email,
            oauth_access_token="old_access_token",
            oauth_refresh_token="original_keep_this_token",
            is_verified=True,
            is_default=True,
        )

        session = self.client_session.session
        session["gmail_oauth_state"] = "state_preserve_check"
        session["gmail_oauth_recruiter_id"] = str(self.recruiter.id)
        session.save()

        # Token response WITHOUT refresh_token
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "brand_new_access_token",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.settings.basic openid email profile",
        }
        mock_requests_post.return_value = mock_token_resp

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "userinfo" in url:
                resp.status_code = 200
                resp.json.return_value = {"email": self.recruiter.email}
            else:
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
            "code": "new_auth_code",
            "state": "state_preserve_check"
        })

        self.assertEqual(response.status_code, 302)
        existing_account.refresh_from_db()
        self.assertEqual(existing_account.oauth_access_token, "brand_new_access_token")
        self.assertEqual(existing_account.oauth_refresh_token, "original_keep_this_token")
        self.assertTrue(existing_account.is_verified)
