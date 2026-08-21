import os
import io
import pytest
from unittest.mock import MagicMock, patch
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core.files.storage import InMemoryStorage
from django.http import HttpResponse

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from services.resume_storage_service import save_candidate_resume_atomic
from utils.s3 import get_presigned_url, get_content_type, MIME_MAP
from utils.preview import generate_resume_preview_response


class MockS3Storage(InMemoryStorage):
    """In-memory storage simulating S3Storage."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bucket_name = "talentvault-files-india"

    def url(self, name):
        return f"https://{self.bucket_name}.s3.ap-south-1.amazonaws.com/{name}"


@pytest.mark.django_db
class S3ResumeAccessAndPresignedUrlTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.mock_storage = MockS3Storage()

        # Recruiter
        self.recruiter = User.objects.create_user(
            email="recruiter@example.com",
            password="Password123!",
            role=User.Role.RECRUITER,
            recruiter_status=User.RecruiterStatus.ACTIVE,
            first_name="Jane",
            last_name="Recruiter"
        )

        # Admin
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="Password123!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
            first_name="Super",
            last_name="Admin"
        )

        # Candidate 1 (owner)
        self.candidate_user_1 = User.objects.create_user(
            email="candidate1@example.com",
            password="Password123!",
            role=User.Role.CANDIDATE,
            first_name="Alice",
            last_name="Candidate"
        )
        self.profile_1 = CandidateProfile.objects.create(
            user=self.candidate_user_1,
            full_name="Alice Candidate",
            location="Bangalore"
        )

        # Candidate 2 (other candidate)
        self.candidate_user_2 = User.objects.create_user(
            email="candidate2@example.com",
            password="Password123!",
            role=User.Role.CANDIDATE,
            first_name="Bob",
            last_name="Other"
        )
        self.profile_2 = CandidateProfile.objects.create(
            user=self.candidate_user_2,
            full_name="Bob Other",
            location="Delhi"
        )

        # Attach sample PDF resume to Profile 1
        with patch.object(CandidateProfile._meta.get_field('resume'), 'storage', self.mock_storage), \
             patch("django.core.files.storage.default_storage", self.mock_storage), \
             patch("services.resume_storage_service.get_active_resume_storage", return_value=self.mock_storage):
            self.pdf_key = save_candidate_resume_atomic(
                self.profile_1,
                b"%PDF-1.4 sample pdf bytes for test",
                "alice_resume.pdf"
            )

    # 1. Presigned URL Generation Tests
    def test_presigned_url_generation_for_pdf_doc_docx(self):
        """Test presigned URL generator with correct Content-Type and expiration (900s)."""
        mock_boto_client = MagicMock()
        mock_boto_client.generate_presigned_url.return_value = "https://talentvault-files-india.s3.ap-south-1.amazonaws.com/resumes/signed-url-test"

        with patch("utils.s3.get_s3_client", return_value=mock_boto_client):
            # Test PDF (inline)
            url_pdf = get_presigned_url("resumes/test.pdf", expires_in=900, as_attachment=False)
            self.assertTrue(url_pdf.startswith("https://"))
            call_params_pdf = mock_boto_client.generate_presigned_url.call_args[1]
            self.assertEqual(call_params_pdf['ExpiresIn'], 900)
            self.assertEqual(call_params_pdf['Params']['ResponseContentType'], 'application/pdf')
            self.assertIn('inline', call_params_pdf['Params']['ResponseContentDisposition'])

            # Test DOC (attachment)
            url_doc = get_presigned_url("resumes/test.doc", expires_in=900, as_attachment=True, filename="my_resume.doc")
            call_params_doc = mock_boto_client.generate_presigned_url.call_args[1]
            self.assertEqual(call_params_doc['ExpiresIn'], 900)
            self.assertEqual(call_params_doc['Params']['ResponseContentType'], 'application/msword')
            self.assertIn('attachment', call_params_doc['Params']['ResponseContentDisposition'])
            self.assertIn('filename="my_resume.doc"', call_params_doc['Params']['ResponseContentDisposition'])

            # Test DOCX (attachment)
            url_docx = get_presigned_url("resumes/test.docx", expires_in=600, as_attachment=True)
            call_params_docx = mock_boto_client.generate_presigned_url.call_args[1]
            self.assertEqual(call_params_docx['ExpiresIn'], 600)
            self.assertEqual(call_params_docx['Params']['ResponseContentType'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')

    def test_content_type_resolution_mapping(self):
        """Test MIME content type resolution for resume formats."""
        self.assertEqual(get_content_type("resume.pdf"), "application/pdf")
        self.assertEqual(get_content_type("resume.doc"), "application/msword")
        self.assertEqual(get_content_type("resume.docx"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertEqual(get_content_type("resume.rtf"), "application/rtf")
        self.assertEqual(get_content_type("resume.txt"), "text/plain")
        self.assertEqual(get_content_type("photo.png"), "image/png")
        self.assertEqual(get_content_type("photo.jpg"), "image/jpeg")

    # 2. Authenticated Resume Access Tests
    def test_authenticated_recruiter_can_download_resume(self):
        """Test recruiter can download candidate resume and gets redirected to presigned S3 URL."""
        self.client.force_login(self.recruiter)
        download_url = reverse('frontend:candidate_resume_download', kwargs={'pk': self.profile_1.pk})

        with patch("utils.s3.get_presigned_url", return_value="https://s3.amazonaws.com/presigned-recruiter-test"):
            resp = self.client.get(download_url)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, "https://s3.amazonaws.com/presigned-recruiter-test")

    def test_authenticated_admin_can_download_resume(self):
        """Test super admin can download candidate resume."""
        self.client.force_login(self.admin)
        download_url = reverse('frontend:candidate_resume_download', kwargs={'pk': self.profile_1.pk})

        with patch("utils.s3.get_presigned_url", return_value="https://s3.amazonaws.com/presigned-admin-test"):
            resp = self.client.get(download_url)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, "https://s3.amazonaws.com/presigned-admin-test")

    def test_candidate_owner_can_download_own_resume(self):
        """Test candidate can download their own resume."""
        self.client.force_login(self.candidate_user_1)
        download_url = reverse('frontend:candidate_resume_download', kwargs={'pk': self.profile_1.pk})

        with patch("utils.s3.get_presigned_url", return_value="https://s3.amazonaws.com/presigned-owner-test"):
            resp = self.client.get(download_url)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, "https://s3.amazonaws.com/presigned-owner-test")

    # 3. Authorization & Unauthorized Access Tests
    def test_unauthorized_candidate_cannot_download_another_candidate_resume(self):
        """Test candidate 2 cannot download candidate 1's resume (returns 403)."""
        self.client.force_login(self.candidate_user_2)
        download_url = reverse('frontend:candidate_resume_download', kwargs={'pk': self.profile_1.pk})

        resp = self.client.get(download_url)
        self.assertEqual(resp.status_code, 403)

    def test_unauthorized_candidate_cannot_preview_another_candidate_resume(self):
        """Test candidate 2 cannot preview candidate 1's resume (returns 403)."""
        self.client.force_login(self.candidate_user_2)
        preview_url = reverse('frontend:candidate_resume_preview', kwargs={'pk': self.profile_1.pk})

        resp = self.client.get(preview_url)
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_user_cannot_access_resume_download(self):
        """Test unauthenticated user is redirected to login."""
        download_url = reverse('frontend:candidate_resume_download', kwargs={'pk': self.profile_1.pk})
        resp = self.client.get(download_url)
        # LoginRequiredMixin redirects unauthenticated users
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith('/') or 'login' in resp.url)

    # 4. Missing / Deleted S3 Object Graceful Error Handling
    def test_missing_resume_file_returns_404_not_500(self):
        """Test requesting preview or download for candidate with no resume returns 404 (no 500 error)."""
        self.client.force_login(self.recruiter)
        preview_url = reverse('frontend:candidate_resume_preview', kwargs={'pk': self.profile_2.pk})
        download_url = reverse('frontend:candidate_resume_download', kwargs={'pk': self.profile_2.pk})

        preview_resp = self.client.get(preview_url)
        self.assertEqual(preview_resp.status_code, 404)

        download_resp = self.client.get(download_url)
        self.assertEqual(download_resp.status_code, 404)

    def test_deleted_s3_object_in_preview_handled_gracefully(self):
        """Test when S3 file is deleted/missing from storage, preview returns 404 without crashing."""
        self.client.force_login(self.recruiter)
        preview_url = reverse('frontend:candidate_resume_preview', kwargs={'pk': self.profile_1.pk})

        with patch.object(self.profile_1.resume.storage, 'exists', return_value=False):
            resp = self.client.get(preview_url)
            self.assertEqual(resp.status_code, 404)
            self.assertIn("Resume file was not found in storage.", resp.content.decode('utf-8'))

    # 5. Format Support: PDF, DOC, DOCX Previews and URLs
    def test_doc_and_docx_candidate_resume_access(self):
        """Test DOC and DOCX resumes can be accessed with presigned download links."""
        self.client.force_login(self.recruiter)

        # Upload DOC resume
        with patch.object(CandidateProfile._meta.get_field('resume'), 'storage', self.mock_storage), \
             patch("django.core.files.storage.default_storage", self.mock_storage), \
             patch("services.resume_storage_service.get_active_resume_storage", return_value=self.mock_storage):
            doc_key = save_candidate_resume_atomic(
                self.profile_1,
                b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 binary doc contents",
                "sample.doc"
            )

        self.profile_1.refresh_from_db()
        self.assertTrue(self.profile_1.resume.name.endswith(".doc"))

        with patch("utils.s3.get_presigned_url", return_value="https://s3.amazonaws.com/presigned-doc-url") as mock_ps:
            dl_url = reverse('frontend:candidate_resume_download', kwargs={'pk': self.profile_1.pk})
            resp = self.client.get(dl_url)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, "https://s3.amazonaws.com/presigned-doc-url")
            # Verify content_type passed was application/msword
            mock_ps.assert_called_once()
            call_kwargs = mock_ps.call_args[1]
            self.assertEqual(call_kwargs.get('content_type'), 'application/msword')
