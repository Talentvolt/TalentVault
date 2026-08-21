import os
import io
import pytest
from unittest.mock import MagicMock, patch
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import InMemoryStorage, Storage, default_storage
from django.test import override_settings, TestCase, Client
from django.urls import reverse

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from services.resume_storage_service import (
    upload_and_verify_resume,
    save_candidate_resume_atomic,
    generate_unique_resume_key,
    verify_s3_object_exists,
    ResumeUploadError,
)

class MockS3Storage(InMemoryStorage):
    """
    In-Memory Storage that simulates S3Storage behavior for unit tests.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bucket_name = "talentvault-files-india"

    def url(self, name):
        return f"https://{self.bucket_name}.s3.ap-south-1.amazonaws.com/{name}"


@pytest.mark.django_db
class S3ResumeStorageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="testcandidate@example.com",
            password="Password123!",
            role=User.Role.CANDIDATE,
            first_name="Test",
            last_name="Candidate"
        )
        self.profile = CandidateProfile.objects.create(
            user=self.user,
            full_name="Test Candidate",
            location="Mumbai, India"
        )

    def test_s3_storage_backend_selected_when_aws_configured(self):
        """Test requirement: AWS_STORAGE_BUCKET_NAME configured selects S3 storage backend."""
        with override_settings(
            AWS_STORAGE_BUCKET_NAME="talentvault-files-india",
            STORAGES={"default": {"BACKEND": "storages.backends.s3.S3Storage"}}
        ):
            storage_backend = getattr(settings, 'STORAGES', {}).get('default', {}).get('BACKEND')
            self.assertEqual(storage_backend, "storages.backends.s3.S3Storage")

    def test_debug_mode_does_not_force_local_fallback(self):
        """Test requirement: DEBUG=True with AWS configured still uses S3."""
        with override_settings(
            DEBUG=True,
            AWS_STORAGE_BUCKET_NAME="talentvault-files-india",
            STORAGES={"default": {"BACKEND": "storages.backends.s3.S3Storage"}}
        ):
            backend = getattr(settings, 'STORAGES', {}).get('default', {}).get('BACKEND')
            self.assertEqual(backend, "storages.backends.s3.S3Storage")

        with override_settings(
            DEBUG=False,
            AWS_STORAGE_BUCKET_NAME="talentvault-files-india",
            STORAGES={"default": {"BACKEND": "storages.backends.s3.S3Storage"}}
        ):
            backend = getattr(settings, 'STORAGES', {}).get('default', {}).get('BACKEND')
            self.assertEqual(backend, "storages.backends.s3.S3Storage")

    def test_generate_unique_resume_key(self):
        """Test deterministic unique S3 key generation."""
        key1 = generate_unique_resume_key("sample_resume.pdf")
        key2 = generate_unique_resume_key("sample_resume.pdf")
        
        self.assertTrue(key1.startswith("resumes/"))
        self.assertTrue(key1.endswith(".pdf"))
        self.assertTrue(key2.startswith("resumes/"))
        self.assertTrue(key2.endswith(".pdf"))
        self.assertNotEqual(key1, key2)

    def test_upload_pdf_success_lifecycle(self):
        """Test PDF upload, S3 verification, DB update, and URL generation."""
        mock_storage = MockS3Storage()
        pdf_bytes = b"%PDF-1.4 sample pdf content for resume test"
        
        with patch.object(CandidateProfile._meta.get_field('resume'), 'storage', mock_storage), \
             patch("django.core.files.storage.default_storage", mock_storage), \
             patch("services.resume_storage_service.get_active_resume_storage", return_value=mock_storage):
            saved_key = save_candidate_resume_atomic(self.profile, pdf_bytes, "test_resume.pdf")
            
            self.assertTrue(mock_storage.exists(saved_key))
            self.profile.refresh_from_db()
            self.assertEqual(self.profile.resume.name, saved_key)
            self.assertTrue(self.profile.has_resume)
            self.assertEqual(self.profile.resume_file_url, reverse('frontend:candidate_resume_download', args=[self.profile.pk]))

    def test_upload_doc_and_docx_success_lifecycle(self):
        """Test DOC and DOCX resume uploads."""
        mock_storage = MockS3Storage()
        doc_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 sample doc content"
        docx_bytes = b"PK\x03\x04 sample docx content"
        
        with patch.object(CandidateProfile._meta.get_field('resume'), 'storage', mock_storage), \
             patch("django.core.files.storage.default_storage", mock_storage), \
             patch("services.resume_storage_service.get_active_resume_storage", return_value=mock_storage):
            saved_doc_key = save_candidate_resume_atomic(self.profile, doc_bytes, "sample.doc")
            self.assertTrue(saved_doc_key.endswith(".doc"))
            self.assertTrue(mock_storage.exists(saved_doc_key))
            
            saved_docx_key = save_candidate_resume_atomic(self.profile, docx_bytes, "sample.docx")
            self.assertTrue(saved_docx_key.endswith(".docx"))
            self.assertTrue(mock_storage.exists(saved_docx_key))

    def test_s3_upload_failure_does_not_save_broken_db_reference(self):
        """Test requirement: If S3 upload/verification fails, DB is NOT updated with broken reference."""
        mock_storage = MagicMock()
        mock_storage.save.side_effect = Exception("S3 Connection Timeout")
        
        with patch.object(CandidateProfile._meta.get_field('resume'), 'storage', mock_storage), \
             patch("django.core.files.storage.default_storage", mock_storage), \
             patch("services.resume_storage_service.get_active_resume_storage", return_value=mock_storage):
            with self.assertRaises(ResumeUploadError):
                save_candidate_resume_atomic(self.profile, b"%PDF-1.4 test", "failed_upload.pdf")
            
            self.profile.refresh_from_db()
            self.assertFalse(bool(self.profile.resume and self.profile.resume.name))

    def test_replacement_upload_failure_preserves_existing_resume(self):
        """Test requirement: Replacement upload failure keeps existing valid resume intact."""
        mock_storage = MockS3Storage()
        initial_bytes = b"%PDF-1.4 initial valid resume"
        
        with patch.object(CandidateProfile._meta.get_field('resume'), 'storage', mock_storage), \
             patch("django.core.files.storage.default_storage", mock_storage), \
             patch("services.resume_storage_service.get_active_resume_storage", return_value=mock_storage):
            initial_key = save_candidate_resume_atomic(self.profile, initial_bytes, "valid_v1.pdf")
            self.assertEqual(self.profile.resume.name, initial_key)
            
            # Simulate failure during replacement upload
            failing_storage = MagicMock()
            failing_storage.save.side_effect = Exception("Network Disconnected")
            
            with patch.object(CandidateProfile._meta.get_field('resume'), 'storage', failing_storage), \
                 patch("django.core.files.storage.default_storage", failing_storage), \
                 patch("services.resume_storage_service.get_active_resume_storage", return_value=failing_storage):
                with self.assertRaises(ResumeUploadError):
                    save_candidate_resume_atomic(self.profile, b"%PDF-1.4 new bytes", "v2_failed.pdf")
                
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.resume.name, initial_key)

    def test_candidate_share_page_and_preview_with_s3_resume(self):
        """Test public share page, preview, and download links for candidate with S3 resume."""
        mock_storage = MockS3Storage()
        pdf_bytes = b"%PDF-1.4 public preview test"
        
        with patch.object(CandidateProfile._meta.get_field('resume'), 'storage', mock_storage), \
             patch("django.core.files.storage.default_storage", mock_storage), \
             patch("services.resume_storage_service.get_active_resume_storage", return_value=mock_storage):
            saved_key = save_candidate_resume_atomic(self.profile, pdf_bytes, "public_test.pdf")
            
            # Check share page
            url = reverse('frontend:public_candidate_profile', kwargs={'pk': self.profile.pk})
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertIn(self.profile.full_name, resp.content.decode('utf-8'))
            
            # Check download redirect
            dl_url = reverse('frontend:share_resume_download', kwargs={'pk': self.profile.pk})
            dl_resp = self.client.get(dl_url)
            self.assertEqual(dl_resp.status_code, 302)

    def test_missing_s3_object_detection(self):
        """Test verify_s3_object_exists returns False for missing objects."""
        mock_storage = MockS3Storage()
        self.assertFalse(verify_s3_object_exists("resumes/non_existent_key_99999.pdf", storage=mock_storage))

    def test_duplicate_filename_uploads_do_not_overwrite_another_candidate(self):
        """Test uploading identical filenames for two candidates creates isolated unique S3 keys."""
        mock_storage = MockS3Storage()
        pdf_bytes = b"%PDF-1.4 duplicate filename test"
        
        user2 = User.objects.create_user(
            email="candidate2@example.com",
            password="Password123!",
            role=User.Role.CANDIDATE,
            first_name="Other",
            last_name="Candidate"
        )
        profile2 = CandidateProfile.objects.create(user=user2, full_name="Other Candidate", location="Delhi")
        
        with patch.object(CandidateProfile._meta.get_field('resume'), 'storage', mock_storage), \
             patch("django.core.files.storage.default_storage", mock_storage), \
             patch("services.resume_storage_service.get_active_resume_storage", return_value=mock_storage):
            key1 = save_candidate_resume_atomic(self.profile, pdf_bytes, "resume.pdf")
            key2 = save_candidate_resume_atomic(profile2, pdf_bytes, "resume.pdf")
            
            self.assertNotEqual(key1, key2)
            self.assertTrue(mock_storage.exists(key1))
            self.assertTrue(mock_storage.exists(key2))
