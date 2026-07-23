from unittest.mock import patch
from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.accounts.models import OTPVerification
from apps.accounts.services.email_service import generate_otp, send_email_otp, mask_email

User = get_user_model()


class EmailOTPTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.signup_url = reverse('candidate_signup')
        self.verify_url = reverse('candidate_verify_otp')
        self.resend_url = reverse('resend_email_otp_web')
        self.verify_ajax_url = reverse('verify_email_otp_web')
        self.forgot_url = reverse('candidate_forgot_password')
        self.reset_url = reverse('candidate_reset_password')
        self.candidate_login_url = reverse('candidate_login')
        self.google_login_url = reverse('google_login')

        self.valid_payload = {
            'first_name': 'EmailTest',
            'last_name': 'Candidate',
            'email': 'email.test@example.com',
            'phone_number': '+919876543210',
            'location': 'Bangalore, India',
            'experience': 'experienced',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
            'role': 'CANDIDATE',
        }

    def test_generate_and_mask_email(self):
        """Test OTP generation and email masking helper."""
        otp = generate_otp()
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

        masked = mask_email("candidate@example.com")
        self.assertIn("@example.com", masked)
        self.assertTrue(masked.startswith("c"))

    @patch('apps.accounts.services.email_service.send_email_otp')
    def test_signup_email_otp_dispatch_and_successful_verification(self, mock_send):
        """
        Candidate Signup -> Email OTP -> Verification -> Success
        User account must NOT be created before OTP verification.
        User account IS created after successful OTP verification.
        Verify user.is_verified = True, user.email_verified = True,
        candidate.is_verified = True, candidate.email_verified = True.
        """
        mock_send.return_value = (True, "Verification code sent to your email successfully.")

        # Submit signup form
        response = self.client.post(self.signup_url, self.valid_payload)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.verify_url)

        # Assert user NOT created before OTP verification
        self.assertFalse(User.objects.filter(email='email.test@example.com').exists())

        # Verify OTP record created
        otp_record = OTPVerification.objects.filter(email='email.test@example.com').first()
        self.assertIsNotNone(otp_record)

        # Set known OTP
        raw_otp = "654321"
        otp_record.set_otp(raw_otp)
        otp_record.save()

        # Submit correct OTP
        verify_response = self.client.post(self.verify_url, {'otp': raw_otp})
        self.assertEqual(verify_response.status_code, 302)
        self.assertRedirects(verify_response, reverse('frontend:candidate_dashboard'))

        # Verify user & candidate profile created after verification
        user = User.objects.filter(email='email.test@example.com').first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_verified)
        self.assertTrue(user.email_verified)
        self.assertTrue(user.is_active)
        self.assertEqual(user.role, User.Role.CANDIDATE)
        self.assertEqual(user.candidate_profile.full_name, 'EmailTest Candidate')

        # Check candidate profile verification flags
        candidate_profile = user.candidate_profile
        self.assertTrue(candidate_profile.is_verified)
        self.assertTrue(candidate_profile.email_verified)

        # Log out and test explicit login on CandidateLoginView
        self.client.logout()
        login_resp = self.client.post(self.candidate_login_url, {
            'email': 'email.test@example.com',
            'password': 'StrongPassword123!'
        })
        self.assertEqual(login_resp.status_code, 302)
        self.assertRedirects(login_resp, reverse('frontend:candidate_dashboard'))

    @patch('apps.accounts.services.email_service.send_email_otp')
    def test_wrong_email_otp_validation_error(self, mock_send):
        """
        Wrong Email OTP -> Validation error
        """
        mock_send.return_value = (True, "Success")
        self.client.post(self.signup_url, self.valid_payload)

        otp_record = OTPVerification.objects.filter(email='email.test@example.com').first()
        otp_record.set_otp("123456")
        otp_record.save()

        # Submit wrong OTP
        response = self.client.post(self.verify_url, {'otp': '999999'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid verification code")

        # Verify user NOT created
        self.assertFalse(User.objects.filter(email='email.test@example.com').exists())

    @patch('apps.accounts.services.email_service.send_email_otp')
    def test_expired_email_otp_and_resend(self, mock_send):
        """
        Expired Email OTP -> Resend -> Successful verification
        """
        mock_send.return_value = (True, "Success")
        self.client.post(self.signup_url, self.valid_payload)

        otp_record = OTPVerification.objects.filter(email='email.test@example.com').first()
        otp_record.expires_at = timezone.now() - timedelta(minutes=1)
        otp_record.set_otp("123456")
        otp_record.save()

        # Attempt verification with expired OTP
        verify_resp = self.client.post(self.verify_url, {'otp': '123456'})
        self.assertEqual(verify_resp.status_code, 200)
        self.assertContains(verify_resp, "expired")

        # Resend OTP
        resend_resp = self.client.post(self.resend_url, {}, content_type='application/json')
        self.assertEqual(resend_resp.status_code, 200)
        self.assertTrue(resend_resp.json()['success'])

        otp_record = OTPVerification.objects.filter(email='email.test@example.com').first()
        self.assertFalse(otp_record.is_expired())

        # Verify new OTP succeeds
        otp_record.set_otp("789012")
        otp_record.save()

        final_resp = self.client.post(self.verify_url, {'otp': '789012'})
        self.assertEqual(final_resp.status_code, 302)
        self.assertTrue(User.objects.filter(email='email.test@example.com').exists())

    @patch('apps.accounts.services.email_service.send_email_otp')
    def test_forgot_password_email_otp_flow(self, mock_send):
        """
        Forgot Password -> Email OTP -> Password Reset -> Login
        """
        mock_send.return_value = (True, "Success")

        # 1. Create existing candidate user
        existing_user = User.objects.create_user(
            email='forgot.candidate@example.com',
            password='OldPassword123!',
            first_name='Existing',
            last_name='User',
            phone_number='+919876500000',
            role=User.Role.CANDIDATE,
            is_active=True,
            is_verified=True
        )

        # 2. Submit Forgot Password form with registered email
        forgot_resp = self.client.post(self.forgot_url, {'email': 'forgot.candidate@example.com'})
        self.assertEqual(forgot_resp.status_code, 302)
        self.assertRedirects(forgot_resp, self.verify_url)

        # 3. Verify OTP record created for password reset
        otp_record = OTPVerification.objects.filter(email='forgot.candidate@example.com').first()
        self.assertIsNotNone(otp_record)
        otp_record.set_otp("654321")
        otp_record.save()

        # 4. Verify OTP on OTP Verification screen
        verify_resp = self.client.post(self.verify_url, {'otp': '654321'})
        self.assertEqual(verify_resp.status_code, 302)
        self.assertRedirects(verify_resp, self.reset_url)

        # 5. Reset password on Reset Password screen
        new_password_payload = {
            'password': 'NewSecurePassword123!',
            'confirm_password': 'NewSecurePassword123!'
        }
        reset_resp = self.client.post(self.reset_url, new_password_payload)
        self.assertEqual(reset_resp.status_code, 200)

        # 6. Verify user password updated in DB
        existing_user.refresh_from_db()
        self.assertTrue(existing_user.check_password('NewSecurePassword123!'))

    def test_google_login_route_preserved(self):
        """
        Verify Google Sign-In endpoint remains intact.
        """
        response = self.client.get(self.google_login_url)
        self.assertEqual(response.status_code, 302)
