import pytest
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.accounts.models import OTPVerification
from apps.candidates.models import CandidateProfile

User = get_user_model()


@pytest.mark.django_db
class TestCandidateLoginAuthentication:
    """
    Comprehensive test suite for Candidate registration, password hashing,
    email normalization, verification states, and login authentication.
    """

    @patch('apps.accounts.services.email_service.send_email_otp')
    def test_candidate_registration_creates_hashed_password(self, mock_send, client):
        """
        Verify that candidate registration securely hashes the password using
        Django's password hasher (pbkdf2_sha256) and NEVER stores raw plaintext.
        """
        mock_send.return_value = (True, "OTP sent")
        raw_password = "SecurePassword2026!"
        email = "hashed_pw_candidate@example.com"

        # 1. Register candidate
        signup_data = {
            'first_name': 'Hashed',
            'last_name': 'Candidate',
            'email': email,
            'role': User.Role.CANDIDATE,
            'password': raw_password,
            'confirm_password': raw_password,
            'phone_number': '+919811223344',
            'location': 'Bangalore, India',
            'experience': 'experienced',
        }
        response = client.post(reverse('candidate_signup'), signup_data)
        assert response.status_code == 302
        assert response.url == reverse('candidate_verify_otp')

        # 2. Verify OTP
        otp_record = OTPVerification.objects.filter(email=email).first()
        assert otp_record is not None
        otp_record.set_otp("123456")
        otp_record.save()

        verify_resp = client.post(reverse('candidate_verify_otp'), {'otp': '123456'})
        assert verify_resp.status_code == 302

        # 3. Inspect user in database
        user = User.objects.filter(email=email).first()
        assert user is not None
        assert user.password != raw_password
        assert user.password.startswith('pbkdf2_sha256$') or '$' in user.password
        assert user.check_password(raw_password) is True
        assert user.check_password("WrongPassword123!") is False

    @patch('apps.accounts.services.email_service.send_email_otp')
    def test_complete_register_logout_login_flow(self, mock_send, client):
        """
        Full round-trip test:
        REGISTER → LOGOUT → LOGIN
        Confirm the exact same credentials work, session is established,
        and user is redirected to Candidate Dashboard.
        """
        mock_send.return_value = (True, "OTP sent")
        email = "roundtrip.candidate@example.com"
        password = "RoundTripPass123!"

        # REGISTER
        signup_data = {
            'first_name': 'Round',
            'last_name': 'Trip',
            'email': email,
            'role': User.Role.CANDIDATE,
            'password': password,
            'confirm_password': password,
            'phone_number': '+919877001122',
            'location': 'Pune, Maharashtra, India',
            'experience': 'experienced',
        }
        resp = client.post(reverse('candidate_signup'), signup_data)
        assert resp.status_code == 302

        otp_rec = OTPVerification.objects.filter(email=email).first()
        otp_rec.set_otp("654321")
        otp_rec.save()

        verify_resp = client.post(reverse('candidate_verify_otp'), {'otp': '654321'})
        assert verify_resp.status_code == 302

        user = User.objects.filter(email=email).first()
        assert user is not None
        assert user.candidate_profile is not None
        user_count_before = User.objects.count()

        # LOGOUT
        client.logout()

        # LOGIN with exact same credentials
        login_resp = client.post(reverse('candidate_login'), {
            'email': email,
            'password': password
        })
        assert login_resp.status_code == 302
        assert login_resp.url == reverse('frontend:candidate_dashboard')

        # Confirm no duplicate User or CandidateProfile created
        assert User.objects.count() == user_count_before
        assert CandidateProfile.objects.filter(user=user).count() == 1

    def test_candidate_login_fails_with_incorrect_credentials(self, client):
        """
        Candidate login fails with invalid password or non-existent email
        and renders 'Invalid email or password.'
        """
        # Create candidate user
        user = User.objects.create_user(
            email='valid.candidate@example.com',
            password='CorrectPassword123!',
            first_name='Valid',
            last_name='User',
            role=User.Role.CANDIDATE,
            is_active=True,
            is_verified=True
        )
        CandidateProfile.objects.get_or_create(user=user, full_name='Valid User')

        # Test 1: Wrong password
        resp1 = client.post(reverse('candidate_login'), {
            'email': 'valid.candidate@example.com',
            'password': 'WrongPassword999!'
        })
        assert resp1.status_code == 200
        assert b"Invalid email or password." in resp1.content

        # Test 2: Non-existent email
        resp2 = client.post(reverse('candidate_login'), {
            'email': 'nonexistent.user@example.com',
            'password': 'AnyPassword123!'
        })
        assert resp2.status_code == 200
        assert b"Invalid email or password." in resp2.content

    def test_candidate_email_normalization(self, client):
        """
        Test that email normalization handles case-insensitivity and whitespace:
        'Test.Candidate@Example.COM' and 'test.candidate@example.com' and '  test.candidate@example.com  '
        resolve to the same account and authenticate properly.
        """
        user = User.objects.create_user(
            email='Test.Candidate@Example.COM',
            password='NormalizationPass123!',
            first_name='Normalized',
            last_name='Candidate',
            role=User.Role.CANDIDATE,
            is_active=True,
            is_verified=True
        )
        CandidateProfile.objects.get_or_create(user=user, full_name='Normalized Candidate')

        # 1. Login with all lowercase
        client.logout()
        resp1 = client.post(reverse('candidate_login'), {
            'email': 'test.candidate@example.com',
            'password': 'NormalizationPass123!'
        })
        assert resp1.status_code == 302
        assert resp1.url == reverse('frontend:candidate_dashboard')

        # 2. Login with uppercase and surrounding whitespace
        client.logout()
        resp2 = client.post(reverse('candidate_login'), {
            'email': '  TEST.CANDIDATE@EXAMPLE.COM  ',
            'password': 'NormalizationPass123!'
        })
        assert resp2.status_code == 302
        assert resp2.url == reverse('frontend:candidate_dashboard')

    def test_duplicate_candidate_prevention(self, client):
        """
        Signup form prevents duplicate registrations regardless of email casing.
        """
        User.objects.create_user(
            email='existing.candidate@example.com',
            password='Password123!',
            first_name='Existing',
            last_name='User',
            role=User.Role.CANDIDATE,
            is_active=True,
            is_verified=True
        )

        signup_data = {
            'first_name': 'Duplicate',
            'last_name': 'Candidate',
            'email': 'EXISTING.CANDIDATE@EXAMPLE.COM',
            'role': User.Role.CANDIDATE,
            'password': 'Password123!',
            'confirm_password': 'Password123!',
            'phone_number': '+919876543299',
            'location': 'Delhi, India',
            'experience': 'fresher',
        }
        response = client.post(reverse('candidate_signup'), signup_data)
        assert response.status_code == 200
        assert b"An account with this email already exists." in response.content

    def test_unverified_candidate_shows_verification_message(self, client):
        """
        When candidate account exists but email is not verified (is_verified=False),
        login must display 'Please verify your email before logging in.'
        and NOT incorrectly show 'Invalid email or password.'
        """
        user = User.objects.create_user(
            email='unverified.candidate@example.com',
            password='ValidPassword123!',
            first_name='Unverified',
            last_name='User',
            role=User.Role.CANDIDATE,
            is_active=True
        )
        user.is_verified = False
        user.save()

        response = client.post(reverse('candidate_login'), {
            'email': 'unverified.candidate@example.com',
            'password': 'ValidPassword123!'
        })
        assert response.status_code == 200
        assert b"Please verify your email before logging in." in response.content
        assert b"Invalid email or password." not in response.content

    def test_recruiter_status_pending_does_not_block_candidate_login(self, client):
        """
        In Django Admin, candidate users default to recruiter_status='PENDING' ('Pending Verification').
        This status must NOT prevent candidate authentication if is_active=True and is_verified=True.
        """
        user = User.objects.create_user(
            email='admin_pending_cand@example.com',
            password='ValidPassword123!',
            first_name='AdminCandidate',
            last_name='Test',
            role=User.Role.CANDIDATE,
            recruiter_status=User.RecruiterStatus.PENDING,
            is_active=True
        )
        user.is_verified = True
        user.save()
        CandidateProfile.objects.get_or_create(user=user, full_name='AdminCandidate Test')

        response = client.post(reverse('candidate_login'), {
            'email': 'admin_pending_cand@example.com',
            'password': 'ValidPassword123!'
        })
        assert response.status_code == 302
        assert response.url == reverse('frontend:candidate_dashboard')

    def test_disabled_candidate_shows_disabled_message(self, client):
        """
        Disabled candidate account (is_active=False) displays 'This account is disabled.'
        """
        user = User.objects.create_user(
            email='disabled.cand@example.com',
            password='ValidPassword123!',
            first_name='Disabled',
            last_name='Cand',
            role=User.Role.CANDIDATE,
            is_active=False
        )
        user.is_verified = True
        user.save()

        response = client.post(reverse('candidate_login'), {
            'email': 'disabled.cand@example.com',
            'password': 'ValidPassword123!'
        })
        assert response.status_code == 200
        assert b"This account is disabled." in response.content

    def test_existing_candidate_login_preserved(self, client):
        """
        Verify that existing candidate accounts with valid Django hashed passwords
        continue to authenticate successfully.
        """
        user = User.objects.create_user(
            email='legacy.candidate@example.com',
            password='LegacyPassword123!',
            first_name='Legacy',
            last_name='Candidate',
            role=User.Role.CANDIDATE,
            is_active=True
        )
        user.is_verified = True
        user.save()
        CandidateProfile.objects.get_or_create(user=user, full_name='Legacy Candidate')

        response = client.post(reverse('candidate_login'), {
            'email': 'legacy.candidate@example.com',
            'password': 'LegacyPassword123!'
        })
        assert response.status_code == 302
        assert response.url == reverse('frontend:candidate_dashboard')
