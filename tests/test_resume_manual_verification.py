import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import Client
from apps.candidates.models import CandidateProfile

User = get_user_model()

@pytest.mark.django_db
def test_manual_resume_actions_preview_download_replace_delete():
    # Setup candidate user & profile with initial resume
    user = User.objects.create_user(
        email='candidate_manual_test@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE
    )
    initial_resume = SimpleUploadedFile("initial_resume.pdf", b"%PDF-1.4 initial pdf content", content_type="application/pdf")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name="Manual Test Candidate",
        resume=initial_resume,
        original_filename="initial_resume.pdf"
    )

    client = Client()
    client.force_login(user)

    # 1. VERIFY RESUME PREVIEW (HTTP 200)
    preview_url = reverse('frontend:candidate_resume_preview', kwargs={'pk': profile.pk})
    preview_res = client.get(preview_url)
    assert preview_res.status_code == 200, f"Preview failed with status {preview_res.status_code}"
    print("\n[VERIFIED] 1. Resume Preview returned HTTP 200")

    # 2. VERIFY RESUME DOWNLOAD (HTTP 200)
    download_url = reverse('frontend:candidate_resume_download', kwargs={'pk': profile.pk})
    download_res = client.get(download_url)
    assert download_res.status_code == 200, f"Download failed with status {download_res.status_code}"
    assert download_res.headers.get('Content-Disposition', '').startswith('attachment')
    print("[VERIFIED] 2. Resume Download returned HTTP 200 with Attachment Disposition")

    # 3. VERIFY RESUME REPLACE (HTTP 200 & Database update)
    new_resume = SimpleUploadedFile("replaced_resume.pdf", b"%PDF-1.4 replaced content", content_type="application/pdf")
    replace_url = reverse('frontend:candidate_resume_upload_ajax')
    replace_res = client.post(replace_url, {'resume': new_resume})
    assert replace_res.status_code == 200, f"Replace failed with status {replace_res.status_code}"
    replace_json = replace_res.json()
    assert replace_json.get('success') is True

    profile.refresh_from_db()
    assert profile.has_resume is True
    assert "replaced_resume" in profile.resume.name
    print("[VERIFIED] 3. Resume Replace returned HTTP 200 & updated Database record")

    # 4. VERIFY RESUME DELETE (HTTP 200 & Database deletion)
    delete_url = reverse('frontend:candidate_resume_delete_ajax')
    delete_res = client.post(delete_url)
    assert delete_res.status_code == 200, f"Delete failed with status {delete_res.status_code}"
    delete_json = delete_res.json()
    assert delete_json.get('success') is True

    profile.refresh_from_db()
    assert profile.has_resume is False
    assert not profile.resume
    print("[VERIFIED] 4. Resume Delete returned HTTP 200 & cleared Database record")
