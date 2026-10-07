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
    CandidateProfile, DuplicateResumeLog, BulkResumeJob, BulkResumeItem,
    Education, Experience, CandidateSkill
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

    def test_excel_only_import_creates_candidates(self):
        """Excel-only upload (no ZIP) is accepted and imports candidates from rows."""
        excel_file = self._create_sample_excel([
            ["Acme Corp", "Engineer", "Bangalore", "Whitefield", "John Excel", "9811223344", "", ""],
            ["Globex", "Lead", "Hyderabad", "Hitec City", "Jane Excel", "9811223355", "", ""],
        ])
        response = self.client.post('/api/bulk-resume/validate/', {
            'candidates_excel': excel_file,
            'overwrite': 'false'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['valid_resumes'], 0)
        self.assertEqual(data['excel_rows'], 2)

        job = BulkResumeJob.objects.get(job_number=data['job_id'])
        self.assertEqual(job.total_files, 2)
        self.assertEqual(job.items.count(), 2)

        start_resp = self.client.post('/api/bulk-resume/start/', {
            'job_id': data['job_id'],
            'overwrite': 'false',
            'sync': 'true'
        })
        self.assertEqual(start_resp.status_code, 200)
        self.assertTrue(start_resp.json()['success'])

        job.refresh_from_db()
        self.assertEqual(job.successful_count, 2)
        self.assertTrue(User.objects.filter(phone_number='9811223344').exists())
        self.assertTrue(User.objects.filter(phone_number='9811223355').exists())

    def test_validate_requires_zip_or_excel(self):
        """Validation returns 400 only when neither ZIP nor Excel is provided."""
        response = self.client.post('/api/bulk-resume/validate/', {})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_excel_only_full_candidate_creation_from_real_file(self):
        """Excel-only import reads a real .xlsx file and creates full candidate DB records."""
        import tempfile

        headers = ["Company Name", "Role", "Location", "Name", "Contact Number", "Email"]
        rows = [
            ["Acme Corp", "Engineer", "Bangalore", "John Doe", "9811223344", "john.doe@example.com"],
            ["Globex", "Lead", "Hyderabad", "Jane Roe", "9811223355", "jane.roe@example.com"],
        ]
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(headers)
        for r in rows:
            ws.append(r)

        # Write a real .xlsx file to disk and upload it from disk (real fixture).
        fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb.save(tmp_path)
            with open(tmp_path, "rb") as f:
                excel_file = SimpleUploadedFile(
                    "candidates.xlsx",
                    f.read(),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            resp = self.client.post('/api/bulk-resume/validate/', {'candidates_excel': excel_file})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['success'])
            self.assertEqual(data['excel_rows'], 2)
            self.assertIn("Email", data['column_mapping'])
            self.assertIn("Contact Number", data['column_mapping'])

            start_resp = self.client.post('/api/bulk-resume/start/', {
                'job_id': data['job_id'],
                'sync': 'true'
            })
            self.assertEqual(start_resp.status_code, 200)
            self.assertTrue(start_resp.json()['success'])

            # Verify FINAL candidate DB records.
            john = User.objects.get(email='john.doe@example.com')
            jane = User.objects.get(email='jane.roe@example.com')
            self.assertEqual(john.phone_number, '9811223344')
            self.assertEqual(jane.phone_number, '9811223355')

            john_profile = CandidateProfile.objects.get(user=john)
            self.assertEqual(john_profile.full_name, 'John Doe')
            self.assertEqual(john_profile.current_company, 'Acme Corp')
            self.assertEqual(john_profile.current_designation, 'Engineer')
            self.assertEqual(john_profile.location, 'Bangalore')
        finally:
            os.unlink(tmp_path)

    def test_excel_only_empty_file_returns_error(self):
        """Validation does not fake success when zero Excel rows are loaded."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Company Name", "Role", "Name", "Email"])  # header only, no data rows
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        excel_file = SimpleUploadedFile(
            "empty.xlsx",
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response = self.client.post('/api/bulk-resume/validate/', {'candidates_excel': excel_file})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_excel_exact_structure_semantic_field_mapping_regression(self):
        """
        Regression test using the exact uploaded Excel structure:
        - Candidate Name -> Candidate Name
        - Resume Title -> Professional Summary
        - Contact No. -> Phone
        - Email -> Email
        - Work Exp -> Total Experience
        - Annual Salary -> Current/Annual CTC
        - Current Location -> Current Location
        - Preferred Location -> Preferred Location
        - Current Employer -> Current Company
        - Designation -> Current Designation
        - U.G. Course -> Education / Undergraduate
        - P.G. Course -> Education / Postgraduate
        - Post P.G. Course -> Education / Postgraduate/Additional Education
        - remaining relevant columns -> appropriate candidate fields

        Validates final DB record and candidate profile:
        - Do not put Resume Title into job designation.
        - Do not put U.G./P.G. course into summary.
        - Do not lose Annual Salary.
        - Populates CandidateRecord and related Experience/Education/Skills fields.
        - Preserves full Excel data.
        """
        import tempfile

        headers = [
            "Candidate Name",
            "Resume Title",
            "Contact No.",
            "Email",
            "Work Exp",
            "Annual Salary",
            "Current Location",
            "Preferred Location",
            "Current Employer",
            "Designation",
            "U.G. Course",
            "P.G. Course",
            "Post P.G. Course",
            "Key Skills",
            "Notice Period",
            "Vendor Notes"  # Non-standard column to test preservation
        ]
        row = [
            "Rahul Sharma",
            "Senior Full Stack Python Developer with 6+ years experience",
            "9876543210",
            "rahul.sharma@example.com",
            "6.5 Years",
            "18,00,000",
            "Bengaluru",
            "Hyderabad",
            "Acme Technologies",
            "Senior Software Engineer",
            "B.Tech Computer Science",
            "M.Tech Software Systems",
            "Executive PG Diploma in Machine Learning",
            "Python, Django, AWS, React, Docker",
            "30 Days",
            "Recommended by recruitment partner"
        ]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(headers)
        ws.append(row)

        fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb.save(tmp_path)
            with open(tmp_path, "rb") as f:
                excel_file = SimpleUploadedFile(
                    "candidates_exact.xlsx",
                    f.read(),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            # 1. Validate endpoint
            validate_resp = self.client.post('/api/bulk-resume/validate/', {
                'candidates_excel': excel_file,
                'overwrite': 'true'
            })
            self.assertEqual(validate_resp.status_code, 200)
            v_data = validate_resp.json()
            self.assertTrue(v_data['success'])
            self.assertEqual(v_data['excel_rows'], 1)

            # Check semantic mapping display
            cmap = v_data['column_mapping']
            self.assertEqual(cmap.get("Candidate Name"), "Candidate Name")
            self.assertEqual(cmap.get("Resume Title"), "Professional Summary")
            self.assertEqual(cmap.get("Contact No."), "Phone")
            self.assertEqual(cmap.get("Email"), "Email")
            self.assertEqual(cmap.get("Work Exp"), "Total Experience")
            self.assertEqual(cmap.get("Annual Salary"), "Annual Salary")
            self.assertEqual(cmap.get("Current Location"), "Current Location")
            self.assertEqual(cmap.get("Preferred Location"), "Preferred Location")
            self.assertEqual(cmap.get("Current Employer"), "Current Company")
            self.assertEqual(cmap.get("Designation"), "Current Designation")
            self.assertEqual(cmap.get("U.G. Course"), "UG Course")
            self.assertEqual(cmap.get("P.G. Course"), "PG Course")
            self.assertEqual(cmap.get("Post P.G. Course"), "Post PG Course")
            self.assertEqual(cmap.get("Key Skills"), "Skills")
            self.assertEqual(cmap.get("Notice Period"), "Notice Period")

            # 2. Start import synchronously
            start_resp = self.client.post('/api/bulk-resume/start/', {
                'job_id': v_data['job_id'],
                'overwrite': 'true',
                'sync': 'true'
            })
            self.assertEqual(start_resp.status_code, 200)
            self.assertTrue(start_resp.json()['success'])

            # 3. Validate FINAL database records
            user = User.objects.get(email="rahul.sharma@example.com")
            self.assertEqual(user.phone_number, "9876543210")

            profile = CandidateProfile.objects.get(user=user)

            # Candidate Name -> Candidate Name
            self.assertEqual(profile.full_name, "Rahul Sharma")

            # Resume Title -> Professional Summary
            self.assertEqual(profile.summary, "Senior Full Stack Python Developer with 6+ years experience")
            # Do NOT put Resume Title into job designation
            self.assertNotEqual(profile.current_designation, profile.summary)
            # Designation -> Current Designation
            self.assertEqual(profile.current_designation, "Senior Software Engineer")

            # Do NOT put U.G./P.G. course into summary
            self.assertNotIn("B.Tech", profile.summary)
            self.assertNotIn("M.Tech", profile.summary)

            # Work Exp -> Total Experience
            self.assertEqual(float(profile.total_experience), 6.5)

            # Annual Salary -> Current/Annual CTC (Do NOT lose Annual Salary!)
            self.assertIsNotNone(profile.current_salary)
            self.assertEqual(profile.current_salary, Decimal('1800000.00'))

            # Current Location -> Current Location
            self.assertEqual(profile.location, "Bengaluru")

            # Preferred Location -> Preferred Location
            self.assertEqual(profile.preferred_location, "Hyderabad")

            # Current Employer -> Current Company
            self.assertEqual(profile.current_company, "Acme Technologies")

            # Notice Period
            self.assertEqual(profile.notice_period, 30)

            # U.G. Course -> Education / Undergraduate
            ug_edu = profile.educations.filter(qualification_level=Education.QualificationLevel.UG).first()
            self.assertIsNotNone(ug_edu)
            self.assertEqual(ug_edu.degree, "B.Tech Computer Science")

            # P.G. Course -> Education / Postgraduate
            pg_edu = profile.educations.filter(qualification_level=Education.QualificationLevel.PG).first()
            self.assertIsNotNone(pg_edu)
            self.assertEqual(pg_edu.degree, "M.Tech Software Systems")

            # Post P.G. Course -> Education / Postgraduate/Additional Education
            ppg_edu = profile.educations.filter(degree="Executive PG Diploma in Machine Learning").first()
            self.assertIsNotNone(ppg_edu)

            # Experience record populated
            exp = profile.experiences.filter(is_current=True).first()
            self.assertIsNotNone(exp)
            self.assertEqual(exp.company_name, "Acme Technologies")
            self.assertEqual(exp.designation, "Senior Software Engineer")

            # Skills populated
            skill_names = set(profile.skills.values_list('skill_name', flat=True))
            self.assertTrue(skill_names.issuperset({"Python", "Django", "Aws", "React", "Docker"}))

            # Full Excel data preserved
            self.assertIn('raw_excel_data', profile.parsed_json)
            raw = profile.parsed_json['raw_excel_data']
            self.assertEqual(raw.get("Annual Salary"), "18,00,000")
            self.assertEqual(raw.get("Vendor Notes"), "Recommended by recruitment partner")

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_excel_header_variations_semantic_matching(self):
        """
        Tests handling variations like 'UG', 'U.G.', 'Graduate', 'PG', 'P.G.',
        'Post Graduate', 'Salary', 'CTC', etc., and verifies final DB records.
        """
        import tempfile

        headers = [
            "Name",
            "Headline",
            "Mobile",
            "Email Address",
            "Total Exp",
            "CTC",
            "Location",
            "Pref Location",
            "Employer",
            "Role",
            "U.G.",
            "P.G.",
            "Doctorate",
            "Skills"
        ]
        row = [
            "Priya Verma",
            "Lead AI Researcher and Data Scientist",
            "9811223344",
            "priya.verma@example.com",
            "5 Yrs 6 Months",
            "25 LPA",
            "Mumbai",
            "Pune",
            "DataCorp Labs",
            "Lead Scientist",
            "B.Sc Statistics",
            "M.Sc Computer Science",
            "Ph.D Artificial Intelligence",
            "Python, PyTorch, Transformers"
        ]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(headers)
        ws.append(row)

        fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb.save(tmp_path)
            with open(tmp_path, "rb") as f:
                excel_file = SimpleUploadedFile(
                    "variations.xlsx",
                    f.read(),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            resp = self.client.post('/api/bulk-resume/validate/', {
                'candidates_excel': excel_file,
                'overwrite': 'true'
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['success'])

            start_resp = self.client.post('/api/bulk-resume/start/', {
                'job_id': data['job_id'],
                'sync': 'true'
            })
            self.assertEqual(start_resp.status_code, 200)

            user = User.objects.get(email="priya.verma@example.com")
            self.assertEqual(user.phone_number, "9811223344")

            profile = CandidateProfile.objects.get(user=user)
            self.assertEqual(profile.full_name, "Priya Verma")
            self.assertEqual(profile.summary, "Lead AI Researcher and Data Scientist")
            self.assertEqual(profile.current_designation, "Lead Scientist")
            self.assertEqual(profile.current_company, "DataCorp Labs")
            self.assertEqual(profile.location, "Mumbai")
            self.assertEqual(profile.preferred_location, "Pune")
            self.assertEqual(float(profile.total_experience), 5.5)
            self.assertEqual(profile.current_salary, Decimal('2500000.00'))

            # Education variations
            ug_edu = profile.educations.filter(qualification_level=Education.QualificationLevel.UG).first()
            self.assertIsNotNone(ug_edu)
            self.assertEqual(ug_edu.degree, "B.Sc Statistics")

            pg_edu = profile.educations.filter(qualification_level=Education.QualificationLevel.PG).first()
            self.assertIsNotNone(pg_edu)
            self.assertEqual(pg_edu.degree, "M.Sc Computer Science")

            doc_edu = profile.educations.filter(degree="Ph.D Artificial Intelligence").first()
            self.assertIsNotNone(doc_edu)
            self.assertEqual(doc_edu.qualification_level, Education.QualificationLevel.DOCTORATE)

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

