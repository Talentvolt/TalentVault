import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import Client
from apps.candidates.models import CandidateProfile
from scripts.setup_recruiter_accounts import setup_accounts, RECRUITERS_DATA, ADMIN_DATA

User = get_user_model()

@pytest.mark.django_db
class TestRecruiterAuthAndRoleSeparation:
    def setup_method(self):
        self.credentials = setup_accounts()

    def test_all_9_company_admin_accounts_exist_and_can_login_at_admin_portal(self):
        client = Client()
        recruiter_creds = [c for c in self.credentials if c['type'] == 'Recruiter']
        assert len(recruiter_creds) == 9

        for cred in recruiter_creds:
            user = User.objects.get(email=cred['email'])
            assert user.is_active is True
            assert user.is_staff is True
            assert user.is_superuser is True
            assert user.role == User.Role.SUPER_ADMIN
            assert user.recruiter_status == User.RecruiterStatus.ACTIVE

            # Company Administrator login via /accounts/login/admin/
            admin_login_url = reverse('admin_login')
            response = client.post(admin_login_url, {'email': cred['email'], 'password': cred['password']})
            assert response.status_code == 302
            assert response.url == reverse('frontend:recruiter_dashboard')

            # Verify Dashboard greeting contains admin's first name
            dash_response = client.get(reverse('frontend:recruiter_dashboard'))
            assert dash_response.status_code == 200
            content = dash_response.content.decode('utf-8')
            assert f"Welcome, {user.first_name}" in content
            assert "growfluencestudio@gmail.com" not in content

            # Logout
            client.post(reverse('account_logout'))
            assert '_auth_user_id' not in client.session

    def test_administrator_login_and_admin_permissions(self):
        client = Client()
        admin_email = ADMIN_DATA['email']
        admin_pwd = "TalentVaultAdmin2026!"

        admin_login_url = reverse('admin_login')
        response = client.post(admin_login_url, {'email': admin_email, 'password': admin_pwd})
        assert response.status_code == 302
        assert response.url == reverse('frontend:recruiter_dashboard')

        # Admin user must be able to access Admin Recruiter Approvals page
        approvals_url = reverse('frontend:admin_recruiter_approvals')
        app_res = client.get(approvals_url)
        assert app_res.status_code == 200
        assert "Recruiter Approvals" in app_res.content.decode('utf-8')

    def test_company_admin_login_at_admin_portal(self):
        client = Client()
        snehal_email = "snehal.2020technologies@gmail.com"
        snehal_pwd = "TV_Snehal#2026!"

        # Company user posts credentials to Admin Login page /accounts/login/admin/ -> SUCCESS
        admin_login_url = reverse('admin_login')
        response = client.post(admin_login_url, {'email': snehal_email, 'password': snehal_pwd})
        assert response.status_code == 302
        assert response.url == reverse('frontend:recruiter_dashboard')
        assert client.session.get('_auth_user_id') is not None

    def test_wrong_password_rejection(self):
        client = Client()
        email = "snehal.2020technologies@gmail.com"
        response = client.post(reverse('recruiter_login'), {'email': email, 'password': 'WrongPassword999!'})
        assert response.status_code == 200
        assert "Invalid email or password." in response.content.decode('utf-8')
        assert '_auth_user_id' not in client.session

    def test_cross_user_password_rejection(self):
        client = Client()
        snehal_email = "snehal.2020technologies@gmail.com"
        chhaya_email = "chhayajoshi.2020technologies.in@gmail.com"
        snehal_pwd = "TV_Snehal#2026!"
        chhaya_pwd = "TV_Chhaya#2026!"

        # Snehal email + Chhaya password -> MUST FAIL
        res1 = client.post(reverse('recruiter_login'), {'email': snehal_email, 'password': chhaya_pwd})
        assert res1.status_code == 200
        assert "Invalid email or password." in res1.content.decode('utf-8')
        assert '_auth_user_id' not in client.session

        # Chhaya email + Snehal password -> MUST FAIL
        res2 = client.post(reverse('recruiter_login'), {'email': chhaya_email, 'password': snehal_pwd})
        assert res2.status_code == 200
        assert "Invalid email or password." in res2.content.decode('utf-8')
        assert '_auth_user_id' not in client.session

    def test_inactive_recruiter_account_rejected(self):
        client = Client()
        snehal = User.objects.get(email="snehal.2020technologies@gmail.com")
        snehal.is_active = False
        snehal.save()

        response = client.post(reverse('recruiter_login'), {'email': snehal.email, 'password': "TV_Snehal#2026!"})
        assert response.status_code == 200
        assert "suspended" in response.content.decode('utf-8').lower() or "disabled" in response.content.decode('utf-8').lower()
        assert '_auth_user_id' not in client.session

        # Re-enable
        snehal.is_active = True
        snehal.save()

    def test_resume_upload_records_uploader_ownership(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(fitz.Point(50, 50), "Name: Alex Smith\nEmail: alex.smith@example.com\nPython Django Engineer")
        pdf_bytes = doc.tobytes()
        doc.close()

        snehal = User.objects.get(email="snehal.2020technologies@gmail.com")
        resume_file = SimpleUploadedFile("alex_smith_resume.pdf", pdf_bytes, content_type="application/pdf")

        from apps.candidates.utils import handle_resume_upload
        results = handle_resume_upload(resume_file, overwrite=True, user=snehal)
        assert len(results['created']) == 1
        cand = results['created'][0]

        assert cand.uploaded_by == snehal
        assert cand.uploader_name == "Snehal Patil"

    def test_public_candidate_share_link_works_without_auth(self):
        cand_user = User.objects.create_user(email="public_candidate@example.com", role=User.Role.CANDIDATE)
        profile = CandidateProfile.objects.create(
            user=cand_user,
            full_name="Public Candidate",
            location="Remote",
            uploaded_by=None
        )

        client = Client()
        share_url = reverse('frontend:public_candidate_profile', kwargs={'pk': profile.pk})
        response = client.get(share_url)
        assert response.status_code == 200
        assert "Public Candidate" in response.content.decode('utf-8')
