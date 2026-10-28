import io
from decimal import Decimal
from unittest.mock import patch
import pytest
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile, CandidateSkill, Experience
from apps.candidates.utils import process_resume_file, handle_resume_upload
from apps.accounts.services.email_service import send_candidate_profile_invitation_email
from apps.notifications.models import EmailLog


@pytest.mark.django_db
class TestCandidateProfileInvitationEmailFlow(TestCase):
    def setUp(self):
        # Create a recruiter user
        self.recruiter = User.objects.create_user(
            email='recruiter.jane@talentvault.in',
            password='RecruiterPassword123!',
            role=User.Role.RECRUITER,
            is_active=True,
            first_name='Jane',
            last_name='Recruiter'
        )
        self.client = Client()
        self.client.force_login(self.recruiter)
        mail.outbox.clear()

    def _create_sample_file(self, content_str="Sample resume text"):
        file_obj = io.BytesIO(content_str.encode('utf-8'))
        file_obj.name = "candidate_resume.txt"
        return file_obj

    @patch('apps.candidates.utils.extract_profile_photo', return_value=(None, None))
    @patch('apps.candidates.utils.parse_resume_via_parseora')
    @patch('services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline')
    def test_successful_cv_upload_triggers_automatic_invitation_email(self, mock_ocr, mock_parseora, mock_photo):
        """
        Flow Test:
        Recruiter uploads CV -> CV parses successfully -> Candidate is created ->
        Candidate email is extracted -> Automatic invitation email is sent ->
        Email contains the correct unique TalentVault candidate profile link and CTA button.
        """
        candidate_email = "sara.connor@cyberdyne.org"
        candidate_name = "Sara Connor"
        mock_ocr.return_value = {
            "text": f"{candidate_name}\nEmail: {candidate_email}\nPhone: 9876543210\nSenior DevOps Engineer",
            "engine": "pdfplumber",
            "confidence": 98.0,
            "resume_type": "DIGITAL",
            "largest_bold_name": candidate_name
        }
        mock_parseora.return_value = {
            "personal_info": {
                "name": candidate_name,
                "email": candidate_email,
                "phone": "9876543210",
                "location": "Los Angeles",
                "current_company": "Cyberdyne Systems",
                "current_designation": "Senior DevOps Engineer",
                "total_experience": 6.5
            },
            "summary": "Experienced DevOps and infrastructure specialist.",
            "skills": ["Kubernetes", "Docker", "Terraform", "AWS", "Python"],
            "experience": [
                {
                    "company": "Cyberdyne Systems",
                    "designation": "Senior DevOps Engineer",
                    "description": "Led Kubernetes infrastructure automation.",
                    "start_date": "2021-01-01",
                    "is_current": True
                }
            ],
            "education": []
        }

        fake_file = self._create_sample_file("Sara Connor Resume")
        profile, status = process_resume_file(
            fake_file,
            "sara_connor_cv.txt",
            overwrite=True,
            uploaded_by=self.recruiter
        )

        # 1. Candidate profile creation verification
        self.assertEqual(status, "SUCCESS")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.full_name, candidate_name)
        self.assertEqual(profile.contact_email, candidate_email)

        # 2. Database tracking verification
        profile.refresh_from_db()
        self.assertTrue(profile.profile_invitation_sent)
        self.assertIsNotNone(profile.profile_invitation_sent_at)

        # 3. Automatic email sending verification & From address check
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, [candidate_email])
        self.assertIn("Complete Your TalentVault Profile", sent_email.subject)
        self.assertIn("noreply@talent-vault.in", sent_email.from_email)
        self.assertIn("TalentVault", sent_email.from_email)
        self.assertEqual(sent_email.reply_to, ["support@talent-vault.in"])
        self.assertTrue(sent_email.extra_headers.get('Message-ID', '').endswith('@talent-vault.in>'))

        # 4. Check dynamic HTTPS production profile link in email body (no localhost/IPs)
        expected_profile_link = f"https://talent-vault.in/candidates/{profile.id}/"
        self.assertIn(expected_profile_link, sent_email.body)
        self.assertTrue(expected_profile_link.startswith("https://talent-vault.in/"))
        self.assertNotIn("localhost", sent_email.body)
        self.assertNotIn("127.0.0.1", sent_email.body)

        # 5. Check exact required template copy in email plain text
        self.assertIn(f"Hi {candidate_name},", sent_email.body)
        self.assertIn("Your CV has been successfully processed and your profile has been created on TalentVault.", sent_email.body)
        self.assertIn("To complete your profile and make it available for relevant job opportunities, please review your information and complete your TalentVault profile.", sent_email.body)
        self.assertIn("Your CV / Profile:", sent_email.body)
        self.assertIn("Please click the link above to view your CV details and complete your profile.", sent_email.body)
        self.assertIn("Once your profile is completed, recruiters can consider your profile for suitable job opportunities.", sent_email.body)
        self.assertIn("Regards,", sent_email.body)
        self.assertIn("TalentVault Team", sent_email.body)
        self.assertIn("TalentVault Technologies", sent_email.body)

        # 6. Check HTML alternative and CTA button
        self.assertEqual(len(sent_email.alternatives), 1)
        html_body, mime = sent_email.alternatives[0]
        self.assertEqual(mime, "text/html")
        self.assertIn("Complete Your TalentVault Profile", html_body)
        self.assertIn(expected_profile_link, html_body)
        self.assertIn("https://talent-vault.in/static/images/logo/talentvault-logo.png", html_body)
        self.assertNotIn("localhost", html_body)
        self.assertNotIn("127.0.0.1", html_body)

        # 7. Check EmailLog record
        email_log = EmailLog.objects.filter(recipient_email=candidate_email).first()
        self.assertIsNotNone(email_log)
        self.assertEqual(email_log.status, 'SENT')

    @patch('apps.candidates.utils.extract_profile_photo', return_value=(None, None))
    @patch('apps.candidates.utils.parse_resume_via_parseora')
    @patch('services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline')
    def test_duplicate_cv_upload_does_not_send_duplicate_invitation(self, mock_ocr, mock_parseora, mock_photo):
        """
        Verify idempotency: re-parsing or uploading duplicate CV does NOT send a second invitation email.
        """
        candidate_email = "alex.murphy@omnicorp.org"
        candidate_name = "Alex Murphy"
        mock_ocr.return_value = {
            "text": f"{candidate_name}\nEmail: {candidate_email}\nRobotics Engineer",
            "engine": "pdfplumber",
            "confidence": 95.0,
            "resume_type": "DIGITAL",
            "largest_bold_name": candidate_name
        }
        mock_parseora.return_value = {
            "personal_info": {"name": candidate_name, "email": candidate_email, "phone": "9876543211"},
            "summary": "Robotics specialist",
            "skills": ["Robotics", "C++", "ROS"],
            "experience": [{"company": "OmniCorp", "designation": "Robotics Engineer"}],
            "education": []
        }

        # First parse -> sends 1 email
        fake_file_1 = self._create_sample_file("Alex Murphy Resume 1")
        profile, status = process_resume_file(fake_file_1, "alex_murphy_1.txt", overwrite=True, uploaded_by=self.recruiter)
        self.assertEqual(status, "SUCCESS")
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(profile.profile_invitation_sent)

        # Clear outbox
        mail.outbox.clear()

        # Second parse (same candidate) with overwrite=True
        fake_file_2 = self._create_sample_file("Alex Murphy Resume 2")
        profile2, status2 = process_resume_file(fake_file_2, "alex_murphy_2.txt", overwrite=True, uploaded_by=self.recruiter)
        self.assertEqual(status2, "SUCCESS")

        # Must NOT send duplicate email
        self.assertEqual(len(mail.outbox), 0, "Duplicate invitation email must not be sent on re-parsing!")

    @patch('apps.candidates.utils.extract_profile_photo', return_value=(None, None))
    @patch('apps.candidates.utils.parse_resume_via_parseora')
    @patch('services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline')
    def test_no_valid_email_does_not_send_invitation(self, mock_ocr, mock_parseora, mock_photo):
        """
        Do not send email if no valid candidate email is found in CV.
        """
        mock_ocr.return_value = {
            "text": "John Anonymous\nNo email listed\nPhone: 9876543212\nSystems Analyst",
            "engine": "pdfplumber",
            "confidence": 92.0,
            "resume_type": "DIGITAL",
            "largest_bold_name": "John Anonymous"
        }
        mock_parseora.return_value = {
            "personal_info": {"name": "John Anonymous", "email": "", "phone": "9876543212"},
            "summary": "Analyst without email",
            "skills": ["SQL", "Data Analysis"],
            "experience": [{"company": "Data Corp", "designation": "Systems Analyst"}],
            "education": []
        }

        fake_file = self._create_sample_file("John Anonymous Resume")
        profile, status = process_resume_file(fake_file, "john_anonymous.txt", overwrite=True, uploaded_by=self.recruiter)

        self.assertEqual(status, "SUCCESS")
        profile.refresh_from_db()

        # No email must be sent
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(profile.profile_invitation_sent)
        self.assertIsNone(profile.profile_invitation_sent_at)

    @patch('apps.candidates.utils.extract_profile_photo', return_value=(None, None))
    @patch('apps.candidates.utils.parse_resume_via_parseora')
    @patch('services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline')
    @patch('django.core.mail.EmailMultiAlternatives.send')
    def test_email_sending_failure_does_not_break_cv_parsing_or_profile_creation(
        self, mock_send, mock_ocr, mock_parseora, mock_photo
    ):
        """
        If email sending fails:
        - CV parsing must remain successful
        - Candidate profile must remain created
        - Error is logged
        - Invitation email can be retried later
        """
        mock_send.side_effect = Exception("SMTP connection timed out to smtp.gmail.com")

        candidate_email = "bruce.wayne@waynecorp.org"
        mock_ocr.return_value = {
            "text": f"Bruce Wayne\nEmail: {candidate_email}\nChief Technology Officer",
            "engine": "pdfplumber",
            "confidence": 97.0,
            "resume_type": "DIGITAL",
            "largest_bold_name": "Bruce Wayne"
        }
        mock_parseora.return_value = {
            "personal_info": {"name": "Bruce Wayne", "email": candidate_email, "phone": "9876543213"},
            "summary": "Executive technology leader",
            "skills": ["Leadership", "AI", "Security"],
            "experience": [{"company": "Wayne Enterprises", "designation": "CTO"}],
            "education": []
        }

        fake_file = self._create_sample_file("Bruce Wayne Resume")
        # process_resume_file must succeed without raising an exception
        profile, status = process_resume_file(fake_file, "bruce_wayne.txt", overwrite=True, uploaded_by=self.recruiter)

        self.assertEqual(status, "SUCCESS")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.full_name, "Bruce Wayne")

        profile.refresh_from_db()
        # Invitation sent must be False because email delivery failed
        self.assertFalse(profile.profile_invitation_sent)
        self.assertIsNone(profile.profile_invitation_sent_at)

        failed_log = EmailLog.objects.filter(recipient_email=candidate_email).first()
        self.assertIsNotNone(failed_log)
        self.assertEqual(failed_log.status, 'FAILED')
        self.assertIn('SMTP connection timed out', failed_log.body)

    def test_retry_invitation_endpoint(self):
        """
        Recruiter can retry or manually send the invitation email from the candidate detail view.
        """
        cand_user = User.objects.create(
            email='clark.kent@dailyplanet.org',
            phone_number='9876543214',
            role=User.Role.CANDIDATE
        )
        cand_profile = CandidateProfile.objects.create(
            user=cand_user,
            full_name='Clark Kent',
            location='Metropolis',
            profile_invitation_sent=False
        )

        url = reverse('frontend:candidate_send_invitation', kwargs={'pk': cand_profile.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        cand_profile.refresh_from_db()
        self.assertTrue(cand_profile.profile_invitation_sent)
        self.assertIsNotNone(cand_profile.profile_invitation_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        sent_retry = mail.outbox[0]
        self.assertEqual(sent_retry.to, ['clark.kent@dailyplanet.org'])
        self.assertIn("noreply@talent-vault.in", sent_retry.from_email)
        self.assertIn("TalentVault", sent_retry.from_email)
        self.assertEqual(sent_retry.reply_to, ["support@talent-vault.in"])
        self.assertTrue(sent_retry.extra_headers.get('Message-ID', '').endswith('@talent-vault.in>'))

    def test_unauthenticated_candidate_link_redirects_to_candidate_login(self):
        """
        When candidate clicks the invitation link while logged out,
        they are redirected to candidate_login with ?next=/candidates/<uuid>/.
        """
        cand_user = User.objects.create(
            email='peter.parker@dailybugle.org',
            role=User.Role.CANDIDATE
        )
        cand_profile = CandidateProfile.objects.create(
            user=cand_user,
            full_name='Peter Parker',
            location='Queens, NY'
        )

        unauth_client = Client()
        url = reverse('frontend:candidate_detail', kwargs={'pk': cand_profile.id})
        response = unauth_client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('candidate_login'), response.url)
        self.assertIn(f"next={url}", response.url)

    def test_candidate_accessing_their_profile_url_redirects_to_profile_page(self):
        """
        When a logged-in candidate accesses their unique profile link /candidates/<uuid>/,
        they are routed to their profile completion page /profile/.
        """
        cand_user = User.objects.create_user(
            email='diana.prince@themyscira.gov',
            password='AmazonianPassword123!',
            role=User.Role.CANDIDATE,
            is_active=True
        )
        cand_profile = CandidateProfile.objects.create(
            user=cand_user,
            full_name='Diana Prince',
            location='Themyscira'
        )

        cand_client = Client()
        cand_client.force_login(cand_user)

        url = reverse('frontend:candidate_detail', kwargs={'pk': cand_profile.id})
        response = cand_client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('frontend:candidate_profile'), response.url)

    def test_recruiter_ui_shows_invitation_badges(self):
        """
        Test UI badges on recruiter candidate detail page:
        - "Profile Invitation Sent" when profile_invitation_sent is True
        - "Candidate Email Not Available" when candidate email is missing/placeholder
        """
        now = timezone.now()
        user_sent = User.objects.create(email='tony.stark@stark.org', role=User.Role.CANDIDATE)
        cand_sent = CandidateProfile.objects.create(
            user=user_sent,
            full_name='Tony Stark',
            location='New York',
            profile_invitation_sent=True,
            profile_invitation_sent_at=now
        )

        # 1. View candidate with invitation sent
        url_sent = reverse('frontend:candidate_detail', kwargs={'pk': cand_sent.id})
        response_sent = self.client.get(url_sent)
        self.assertEqual(response_sent.status_code, 200)
        self.assertContains(response_sent, "Profile Invitation Sent")

        # 2. View candidate with no valid email (placeholder email)
        from apps.candidates.utils import make_internal_login_email
        placeholder_email = make_internal_login_email("no_email_hash_1234")
        user_no_email = User.objects.create(email=placeholder_email, role=User.Role.CANDIDATE)
        cand_no_email = CandidateProfile.objects.create(
            user=user_no_email,
            full_name='Natasha Romanoff',
            location='Budapest',
            profile_invitation_sent=False
        )

        url_no_email = reverse('frontend:candidate_detail', kwargs={'pk': cand_no_email.id})
        response_no_email = self.client.get(url_no_email)
        self.assertEqual(response_no_email.status_code, 200)
        self.assertContains(response_no_email, "Candidate Email Not Available")
