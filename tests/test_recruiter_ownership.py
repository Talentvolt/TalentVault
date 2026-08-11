import pytest
import fitz
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import Client
from apps.candidates.models import CandidateProfile
from apps.accounts.apps import create_default_recruiter

User = get_user_model()

def create_valid_pdf_bytes(name, email, text="Senior Software Engineer Python Django AWS"):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 50), f"Name: {name}\nEmail: {email}\n{text}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

@pytest.mark.django_db
class TestRecruiterOwnershipAndAuth:
    def setup_method(self):
        create_default_recruiter(sender=None)

    def test_company_recruiter_accounts_created_with_names(self):
        recruiter_emails = [
            ("snehal.2020technologies@gmail.com", "Snehal Patil"),
            ("chhayajoshi.2020technologies.in@gmail.com", "Chhaya Joshi"),
            ("rahul.2020technologies@gmail.com", "Rahul Nishad"),
            ("anamikashkla.2020technologies@gmail.com", "Anamika"),
            ("deepak.kumar@2020technologies.in", "Deepak Kumar"),
            ("nikhil@2020technologies.in", "Nikhil Mittal"),
            ("harshita.2020technologies@gmail.com", "Harshita"),
            ("deepanshu.verma@2020technologies.in", "Deepanshu Verma"),
            ("rajeevkumar9801456p@gmail.com", "Rajeev Kumar"),
        ]

        for email, expected_name in recruiter_emails:
            user = User.objects.filter(email=email).first()
            assert user is not None, f"Recruiter user {email} was not created"
            assert user.is_active is True
            assert user.recruiter_status == User.RecruiterStatus.ACTIVE
            full_name = user.get_full_name().strip()
            assert full_name == expected_name, f"Expected '{expected_name}' for {email}, got '{full_name}'"

    def test_recruiter_login_and_wrong_password_rejection(self):
        client = Client()
        email = "snehal.2020technologies@gmail.com"

        # Wrong password test
        login_url = reverse('employer_login')
        response_wrong = client.post(login_url, {'email': email, 'password': 'WrongPassword123'})
        assert response_wrong.status_code == 200
        assert '_auth_user_id' not in client.session

        # Correct password test
        response_correct = client.post(login_url, {'email': email, 'password': 'TalentVault2026!'})
        assert response_correct.status_code == 302
        assert client.session.get('_auth_user_id') is not None

        # Logout test
        logout_url = reverse('account_logout')
        response_logout = client.post(logout_url)
        assert response_logout.status_code in (200, 302)

    def test_dashboard_identity_displays_logged_in_recruiter(self):
        client = Client()
        snehal = User.objects.get(email="snehal.2020technologies@gmail.com")
        client.force_login(snehal)

        dashboard_url = reverse('frontend:recruiter_dashboard')
        res = client.get(dashboard_url)
        assert res.status_code == 200
        content = res.content.decode('utf-8')
        assert "Welcome, Snehal 👋" in content or "Snehal Patil" in content
        assert "growfluencestudio@gmail.com" not in content

    def test_multi_recruiter_upload_ownership_isolation(self):
        client = Client()

        snehal = User.objects.get(email="snehal.2020technologies@gmail.com")
        deepak = User.objects.get(email="deepak.kumar@2020technologies.in")

        # 1. Recruiter Snehal uploads Candidate A
        client.force_login(snehal)
        pdf_bytes_a = create_valid_pdf_bytes("John Doe", "john.doe.a@example.com")
        resume_a = SimpleUploadedFile("resume_candidate_a.pdf", pdf_bytes_a, content_type="application/pdf")

        from apps.candidates.utils import handle_resume_upload
        results_a = handle_resume_upload(resume_a, overwrite=True, user=snehal)
        assert len(results_a['created']) == 1
        cand_a = results_a['created'][0]

        assert cand_a.uploaded_by == snehal
        assert cand_a.created_by == snehal
        assert cand_a.uploader_name == "Snehal Patil"

        # 2. Recruiter Deepak uploads Candidate B
        client.force_login(deepak)
        pdf_bytes_b = create_valid_pdf_bytes("Jane Smith", "jane.smith.b@example.com")
        resume_b = SimpleUploadedFile("resume_candidate_b.pdf", pdf_bytes_b, content_type="application/pdf")
        results_b = handle_resume_upload(resume_b, overwrite=True, user=deepak)
        assert len(results_b['created']) == 1
        cand_b = results_b['created'][0]

        assert cand_b.uploaded_by == deepak
        assert cand_b.created_by == deepak
        assert cand_b.uploader_name == "Deepak Kumar"

        # Verify Candidate A's uploader remains Snehal Patil
        cand_a.refresh_from_db()
        assert cand_a.uploaded_by == snehal
        assert cand_a.uploader_name == "Snehal Patil"

    def test_existing_candidate_data_preservation_with_null_uploader(self):
        cand_user = User.objects.create_user(email="historical_candidate@example.com", role=User.Role.CANDIDATE)
        resume_file = SimpleUploadedFile("historical.pdf", b"%PDF-1.4 historical resume", content_type="application/pdf")
        profile = CandidateProfile.objects.create(
            user=cand_user,
            full_name="Historical Candidate",
            resume=resume_file,
            original_filename="historical.pdf",
            uploaded_by=None,
            created_by=None
        )

        assert profile.uploaded_by is None
        assert profile.uploader_name is None

        # Share link must continue working publicly without login
        client = Client()
        share_url = reverse('frontend:public_candidate_profile', kwargs={'pk': profile.pk})
        res_share = client.get(share_url)
        assert res_share.status_code == 200
        share_html = res_share.content.decode('utf-8')
        assert "Historical Candidate" in share_html

        # Resume preview and download views
        preview_url = reverse('frontend:share_resume_preview', kwargs={'pk': profile.pk})
        res_prev = client.get(preview_url)
        assert res_prev.status_code in (200, 302)

        download_url = reverse('frontend:share_resume_download', kwargs={'pk': profile.pk})
        res_dl = client.get(download_url)
        assert res_dl.status_code in (200, 302)
