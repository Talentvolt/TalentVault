import io
import os
import zipfile
import pytest
import openpyxl
from decimal import Decimal
from django.test import TestCase, Client
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.candidates.models import (
    CandidateProfile, DuplicateResumeLog, BulkResumeJob, BulkResumeItem
)
from services.bulk_resume_parser_service import BulkResumeParserService


@pytest.mark.django_db
class TestBulkResumeParser(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            email='recruiter@talentvault.com',
            password='TestPassword123!',
            first_name='Recruiter',
            last_name='Admin'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _create_sample_zip(self, files_dict):
        """Creates an in-memory ZIP containing given filename -> content bytes mapping."""
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            for fname, content in files_dict.items():
                zf.writestr(fname, content)
        zip_buf.seek(0)
        return SimpleUploadedFile("sample_resumes.zip", zip_buf.read(), content_type="application/zip")

    def _create_sample_excel(self, rows_list, headers=None):
        """Creates an in-memory Excel workbook with given rows."""
        if headers is None:
            headers = ["Company Name", "Role", "Location", "Sub Location", "Name", "Contact Number", "Resume", "Interviewed"]
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(headers)
        for r in rows_list:
            ws.append(r)
        excel_buf = io.BytesIO()
        wb.save(excel_buf)
        excel_buf.seek(0)
        return SimpleUploadedFile("candidates.xlsx", excel_buf.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def _create_dummy_pdf(self, text_content="John Doe\nSoftware Engineer\nPython Django\nEmail: john.doe@example.com\nPhone: 9876543210"):
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        y = 750
        for line in text_content.split('\n'):
            line_str = line.strip()
            if line_str:
                c.drawString(100, y, line_str)
                y -= 25
        c.save()
        buf.seek(0)
        return buf.read()

    def test_validation_and_safe_zip_extraction(self):
        """Test ZIP extraction with supported and unsupported file rejection."""
        files = {
            "john_doe.pdf": self._create_dummy_pdf("John Doe\nSoftware Developer"),
            "jane_smith.docx": self._create_dummy_pdf("Jane Smith\nBackend Lead"),
            "unsupported.txt": b"Random text note",
            "nested.zip": b"Fake nested archive",
            "dangerous.exe": b"MZ executable"
        }
        zip_file = self._create_sample_zip(files)
        excel_file = self._create_sample_excel([
            ["Acme Corp", "Backend Dev", "Bangalore", "Whitefield", "John Doe", "9876543210", "john_doe.pdf", "No"],
            ["Tech Solutions", "Lead", "Hyderabad", "Hitec City", "Jane Smith", "9876543211", "jane_smith.docx", "Yes"]
        ])

        summary = BulkResumeParserService.validate_and_stage_upload(
            zip_file=zip_file,
            excel_file=excel_file,
            user=self.user,
            overwrite=False
        )

        self.assertTrue(summary['success'])
        self.assertEqual(summary['valid_resumes'], 2)
        self.assertEqual(summary['skipped_files'], 3)
        self.assertEqual(summary['excel_rows'], 2)
        self.assertEqual(summary['matched_count'], 2)

        # Verify database objects created
        job = BulkResumeJob.objects.get(job_number=summary['job_id'])
        self.assertEqual(job.total_files, 2)
        self.assertEqual(job.skipped_count, 3)
        self.assertEqual(job.items.count(), 5)

    def test_excel_column_normalization_matching(self):
        """Test column matching with Google Sheet structure."""
        excel_file = self._create_sample_excel([
            ["Cars 24", "KAM", "Bangalore", "NA", "Rangaswamy", "7892094411", "RANGASWAMY .pdf", ""],
            ["Cars 24", "RA", "Hyderabad", "NA", "S.D.BHAVANA", "9573486734", "S.D.Bhavana 3 (1).pdf", ""]
        ])
        parsed_rows, mapping = BulkResumeParserService.parse_candidate_excel(excel_file)
        self.assertEqual(len(parsed_rows), 2)
        self.assertIn("Company Name", mapping)
        self.assertIn("Contact Number", mapping)
        self.assertEqual(parsed_rows[0]['company'], "Cars 24")
        self.assertEqual(parsed_rows[0]['designation'], "KAM")
        self.assertEqual(parsed_rows[0]['phone'], "7892094411")

    def test_bulk_validation_api_endpoint(self):
        """Test HTTP POST /api/bulk-resume/validate/."""
        files = {
            "candidate1.pdf": self._create_dummy_pdf("Candidate One\nPython Developer\nEmail: c1@example.com"),
            "candidate2.docx": self._create_dummy_pdf("Candidate Two\nReact Developer\nEmail: c2@example.com")
        }
        zip_file = self._create_sample_zip(files)
        response = self.client.post('/api/bulk-resume/validate/', {
            'resumes_zip': zip_file,
            'overwrite': 'false'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['valid_resumes'], 2)
        self.assertEqual(data['skipped_files'], 0)

    def test_bulk_start_and_status_api(self):
        """Test HTTP POST /api/bulk-resume/start/ and GET /api/bulk-resume/status/<job_number>/."""
        files = {
            "test_candidate.pdf": self._create_dummy_pdf("Alex Taylor\nPython Engineer\nEmail: alex@example.com\nPhone: 9811223344")
        }
        zip_file = self._create_sample_zip(files)
        summary = BulkResumeParserService.validate_and_stage_upload(
            zip_file=zip_file,
            user=self.user,
            overwrite=True
        )
        job_id = summary['job_id']

        # Trigger start API with sync=true for deterministic test execution
        response = self.client.post('/api/bulk-resume/start/', {
            'job_id': job_id,
            'overwrite': 'true',
            'sync': 'true'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        # Query status API
        status_res = self.client.get(f'/api/bulk-resume/status/{job_id}/')
        self.assertEqual(status_res.status_code, 200)
        data = status_res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['job_number'], job_id)
        self.assertEqual(data['total_files'], 1)

    def test_csv_report_generation(self):
        """Test CSV report generation endpoint."""
        files = {
            "report_test.pdf": self._create_dummy_pdf("Report Candidate\nDevOps")
        }
        zip_file = self._create_sample_zip(files)
        summary = BulkResumeParserService.validate_and_stage_upload(
            zip_file=zip_file,
            user=self.user
        )
        job_id = summary['job_id']

        # Generate report
        report_res = self.client.get(f'/api/bulk-resume/report/{job_id}/')
        self.assertEqual(report_res.status_code, 200)
        self.assertEqual(report_res['Content-Type'], 'text/csv')
        csv_text = report_res.content.decode('utf-8')
        self.assertIn("Filename", csv_text)
        self.assertIn("report_test.pdf", csv_text)

    def test_duplicate_handling_overwrite_off_vs_on(self):
        """Test that duplicate candidates are skipped when overwrite=False and updated when overwrite=True."""
        # Create existing user and candidate
        existing_user = User.objects.create(email="dup.candidate@talentvault.com", phone_number="9112233445", role=User.Role.CANDIDATE)
        profile = CandidateProfile.objects.create(user=existing_user, full_name="Original Name", location="Delhi")

        files = {
            "dup_resume.pdf": self._create_dummy_pdf("Dup Candidate\nPhone: 9112233445\nEmail: dup.candidate@talentvault.com")
        }
        excel_rows = [
            ["Company", "Role", "Delhi", "", "Dup Candidate", "9112233445", "dup_resume.pdf", ""]
        ]
        
        # Test Overwrite OFF (Skipped)
        zip_file = self._create_sample_zip(files)
        excel_file = self._create_sample_excel(excel_rows)
        summary_off = BulkResumeParserService.validate_and_stage_upload(
            zip_file=zip_file, excel_file=excel_file, user=self.user, overwrite=False
        )
        job_off = BulkResumeJob.objects.get(job_number=summary_off['job_id'])
        item_off = job_off.items.first()
        BulkResumeParserService._process_single_item(item_off, job_off, user=self.user, overwrite=False)
        
        item_off.refresh_from_db()
        self.assertEqual(item_off.status, BulkResumeItem.Status.SKIPPED)
        self.assertEqual(item_off.action_taken, 'SKIPPED_DUPLICATE')

        # Test Overwrite ON (Updated)
        zip_file2 = self._create_sample_zip(files)
        excel_file2 = self._create_sample_excel(excel_rows)
        summary_on = BulkResumeParserService.validate_and_stage_upload(
            zip_file=zip_file2, excel_file=excel_file2, user=self.user, overwrite=True
        )
        job_on = BulkResumeJob.objects.get(job_number=summary_on['job_id'])
        item_on = job_on.items.first()
        BulkResumeParserService._process_single_item(item_on, job_on, user=self.user, overwrite=True)

        item_on.refresh_from_db()
        self.assertEqual(item_on.status, BulkResumeItem.Status.UPDATED)
        self.assertEqual(item_on.action_taken, 'UPDATED')

    def test_corrupted_pdf_crash_isolation(self):
        """Test that a corrupted PDF or parser failure does not crash the batch and marks item as FAILED."""
        files = {
            "good_resume1.pdf": self._create_dummy_pdf("Good Candidate 1\nEmail: good1@example.com"),
            "corrupted_resume.pdf": b"CORRUPTED_BINARY_DATA_NOT_A_VALID_PDF_%%%###",
            "good_resume2.pdf": self._create_dummy_pdf("Good Candidate 2\nEmail: good2@example.com")
        }
        zip_file = self._create_sample_zip(files)
        summary = BulkResumeParserService.validate_and_stage_upload(zip_file=zip_file, user=self.user)
        job = BulkResumeJob.objects.get(job_number=summary['job_id'])
        
        # Process all items
        for item in job.items.filter(status=BulkResumeItem.Status.PENDING):
            BulkResumeParserService._process_single_item(item, job, user=self.user)

        job.refresh_from_db()
        self.assertEqual(job.processed_files, 3)
        self.assertGreaterEqual(job.failed_count, 1)

        corrupted_item = job.items.get(filename="corrupted_resume.pdf")
        self.assertEqual(corrupted_item.status, BulkResumeItem.Status.FAILED)
        self.assertEqual(corrupted_item.action_taken, 'FAILED')

    def test_large_batch_50_resumes(self):
        """Test processing a batch of 50 resumes with Excel matching."""
        files = {}
        excel_rows = []
        for i in range(50):
            fname = f"candidate_{i:03d}.pdf"
            files[fname] = self._create_dummy_pdf(f"Candidate {i}\nSoftware Engineer\nEmail: cand{i}@example.com\nPhone: 900000{i:04d}")
            excel_rows.append(["TalentTech", "Software Engineer", "Bangalore", "Koramangala", f"Candidate {i}", f"900000{i:04d}", fname, ""])

        zip_file = self._create_sample_zip(files)
        excel_file = self._create_sample_excel(excel_rows)

        summary = BulkResumeParserService.validate_and_stage_upload(
            zip_file=zip_file,
            excel_file=excel_file,
            user=self.user,
            overwrite=True
        )

        self.assertEqual(summary['valid_resumes'], 50)
        self.assertEqual(summary['matched_count'], 50)

        job = BulkResumeJob.objects.get(job_number=summary['job_id'])
        self.assertEqual(job.total_files, 50)

        # Process a batch of 10 items
        for item in list(job.items.filter(status=BulkResumeItem.Status.PENDING))[:10]:
            BulkResumeParserService._process_single_item(item, job, user=self.user, overwrite=True)

        job.refresh_from_db()
        self.assertEqual(job.processed_files, 10)

    def test_single_resume_parser_endpoint_preserved(self):
        """Verify that the single resume parser view renders and functions properly."""
        response = self.client.get('/resume-parser/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn("Resume Parser Workspace", html)
        self.assertIn("Bulk Resume Parser", html)
        self.assertIn("Single Resume / Manual", html)
        self.assertIn("Manual Resume Parsing", html)
