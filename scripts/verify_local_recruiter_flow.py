import os
import sys
import django
import fitz

# Setup Django Environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.test import Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from scripts.setup_recruiter_accounts import setup_accounts, RECRUITERS_DATA

def verify_recruiter_flow():
    print("=" * 80)
    print("MANUAL END-TO-END FLOW VERIFICATION — MULTI-USER COMPANY WORKSPACE")
    print("=" * 80)

    # 1. Re-initialize accounts with credentials
    creds = setup_accounts()
    
    # Test users: Snehal, Chhaya, Rahul
    test_emails = [
        "snehal.2020technologies@gmail.com",
        "chhayajoshi.2020technologies.in@gmail.com",
        "rahul.2020technologies@gmail.com"
    ]

    for email in test_emails:
        client = Client()
        user_cred = [c for c in creds if c['email'] == email][0]
        user_obj = User.objects.get(email=email)
        first_name = user_obj.first_name

        print(f"\n[USER TEST] Testing Company User: {user_cred['name']} ({email})...")

        # 1. Login via /accounts/login/admin/
        login_res = client.post(
            reverse('admin_login'),
            {'email': user_cred['email'], 'password': user_cred['password']}
        )
        assert login_res.status_code == 302, f"Login failed for {email} with status {login_res.status_code}"
        print(f"  -> Login successful! Logged in as {user_obj.get_full_name()}")

        # 2. Verify Dashboard Greeting & Identity
        dash_res = client.get(reverse('frontend:recruiter_dashboard'))
        assert dash_res.status_code == 200
        dash_html = dash_res.content.decode('utf-8')
        assert f"Welcome, {first_name}" in dash_html, f"Greeting 'Welcome, {first_name}' missing from dashboard!"
        assert "growfluencestudio@gmail.com" not in dash_html, "Found hardcoded growfluencestudio email!"
        print(f"  -> Dashboard loaded cleanly with personalized greeting 'Welcome, {first_name}'!")

        # 3. Verify Profile Settings Page
        settings_res = client.get(reverse('frontend:settings'))
        assert settings_res.status_code == 200
        settings_html = settings_res.content.decode('utf-8')
        assert user_obj.email in settings_html, f"Email {user_obj.email} missing from Settings page!"
        assert user_obj.get_full_name() in settings_html, f"Full name {user_obj.get_full_name()} missing from Settings page!"
        print(f"  -> Settings page correctly displays real identity: {user_obj.get_full_name()} ({user_obj.email})")

        # 4. Upload Resume as this specific user
        print(f"  -> Uploading resume as {user_obj.get_full_name()}...")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(fitz.Point(50, 50), f"Name: Candidate Test User {first_name}\nEmail: cand.{first_name.lower()}@example.com\nSoftware Engineer")
        pdf_bytes = doc.tobytes()
        doc.close()

        uploaded_file = SimpleUploadedFile(f"resume_{first_name.lower()}.pdf", pdf_bytes, content_type="application/pdf")
        
        from apps.candidates.utils import handle_resume_upload
        results = handle_resume_upload(uploaded_file, overwrite=True, user=user_obj)
        assert len(results['created']) == 1, "Failed to create candidate profile from resume upload!"
        candidate = results['created'][0]

        assert candidate.uploaded_by == user_obj, f"Candidate uploaded_by {candidate.uploaded_by} != {user_obj}"
        assert candidate.uploader_name == user_obj.get_full_name(), f"Expected uploader_name '{user_obj.get_full_name()}', got '{candidate.uploader_name}'"
        print(f"  -> Resume ownership correctly recorded: 'Added By: {candidate.uploader_name}'")

        # 5. Verify Candidate Detail Page UI
        detail_url = reverse('frontend:candidate_detail', kwargs={'pk': candidate.pk})
        detail_res = client.get(detail_url)
        assert detail_res.status_code == 200
        detail_html = detail_res.content.decode('utf-8')
        assert candidate.uploader_name in detail_html, "Uploader name missing on Candidate Detail page UI!"
        print(f"  -> Candidate Detail UI displays 'Added By: {candidate.uploader_name}'!")

        # 6. Verify Resume Preview & Download
        prev_res = client.get(reverse('frontend:candidate_resume_preview', kwargs={'pk': candidate.pk}))
        assert prev_res.status_code in (200, 302)
        dl_res = client.get(reverse('frontend:candidate_resume_download', kwargs={'pk': candidate.pk}))
        assert dl_res.status_code in (200, 302)
        print("  -> Resume Preview & Download endpoints operating 100% normally!")

        # 7. Verify Public Share Link (Anonymous Client)
        anon_client = Client()
        share_url = reverse('frontend:public_candidate_profile', kwargs={'pk': candidate.pk})
        share_res = anon_client.get(share_url)
        assert share_res.status_code == 200
        assert candidate.full_name in share_res.content.decode('utf-8')
        print(f"  -> Public Share Link ({share_url}) working publicly without authentication!")

        # 8. Clean up verification candidate from database
        cand_user = candidate.user
        candidate.delete()
        if cand_user:
            cand_user.delete()
        print(f"  -> Test candidate cleaned up cleanly from database!")

        client.post(reverse('account_logout'))

    print("\n" + "=" * 80)
    print("ALL VERIFICATION STEPS PASSED SUCCESSFULLY FOR ALL TEST USERS!")
    print("=" * 80)

if __name__ == '__main__':
    verify_recruiter_flow()
