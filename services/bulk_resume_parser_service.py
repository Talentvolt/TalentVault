import os
import io
import re
import gc
import time
import zipfile
import logging
import hashlib
import tempfile
import threading
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

from django.conf import settings
from django.utils import timezone
from django.db import models, transaction, connection
from django.db.models import Q
from django.core.files.base import ContentFile

from decimal import Decimal

from apps.accounts.models import User
from apps.candidates.models import (
    CandidateProfile, DuplicateResumeLog, BulkResumeJob, BulkResumeItem,
    Experience, Education, CandidateSkill
)
from apps.candidates.utils import process_resume_file, make_internal_login_email, is_placeholder_email
from utils.security import sanitize_filename

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.pdf', '.doc', '.docx'}
DANGEROUS_EXTENSIONS = {'.exe', '.bat', '.cmd', '.sh', '.vbs', '.js', '.py', '.bin', '.dll', '.so', '.jar', '.scr', '.msi'}
MAX_ZIP_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
MAX_UNCOMPRESSED_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
DEFAULT_BATCH_SIZE = getattr(settings, 'BULK_PARSE_BATCH_SIZE', 5)
ITEM_TIMEOUT_SECONDS = getattr(settings, 'BULK_PARSE_ITEM_TIMEOUT', 30)


class BulkResumeParserService:
    """
    Production-ready, asynchronous, crash-safe Bulk Resume Parser Service.
    Supports:
    1. ZIP containing resumes (.pdf, .doc, .docx)
    2. Excel (.xlsx, .xls) containing candidate data matching the TalentVault candidate structure
    """

    @classmethod
    def generate_job_number(cls) -> str:
        """Generates a human-friendly unique job number e.g. TV-1024 or TV-849201."""
        import random
        for _ in range(10):
            num = f"TV-{random.randint(100000, 999999)}"
            if not BulkResumeJob.objects.filter(job_number=num).exists():
                return num
        return f"TV-{int(time.time() * 1000) % 10000000:07d}"

    @classmethod
    def sanitize_zip_path(cls, path: str) -> str:
        """Strips leading slashes, path traversal '../', and normalizes separators."""
        cleaned = path.replace('\\', '/').strip('/')
        parts = [p for p in cleaned.split('/') if p and p != '..']
        return '/'.join(parts)

    @classmethod
    def normalize_key(cls, val: str) -> str:
        """Normalizes a filename, email, phone, or name for confident cross-matching."""
        if not val:
            return ""
        # Remove extra whitespace and lowercase
        clean = str(val).strip().lower()
        # Remove common extension if matching filenames
        clean = re.sub(r'\.(pdf|docx?|doc)$', '', clean)
        # Remove non-alphanumeric characters for fuzzy fallback
        return re.sub(r'[^a-z0-9]', '', clean)

    @classmethod
    def normalize_phone(cls, phone_val: Any) -> str:
        """
        Extracts and normalizes a single valid primary phone number from an Excel value.
        Handles:
        - 10-digit phone
        - +91 formatted phone
        - phone with spaces/dashes
        - multiple phone numbers separated by /, commas, semicolons, etc.
        - phone with extension (e.g. ext 123, x402)
        - invalid or overlong phone values: returns empty string (save NULL in DB).
        Never truncates a phone number blindly.
        Guarantees returned value length <= 15 (fitting User.phone_number max_length=15).
        """
        if not phone_val:
            return ""

        # Handle float / int / string representations
        if isinstance(phone_val, float):
            raw_str = f"{phone_val:.0f}" if phone_val.is_integer() else str(phone_val).split('.')[0]
        else:
            raw_str = str(phone_val).strip()
            if raw_str.endswith('.0') and raw_str[:-2].isdigit():
                raw_str = raw_str[:-2]

        raw_str = raw_str.strip()
        if not raw_str or raw_str.lower() in ('none', 'null', 'nan', 'n/a', 'na', '-', 'nil', 'not available'):
            return ""

        # Strip extension patterns: ext, ext., extension, x followed by numbers
        # e.g., '9876543210 ext 1234', '+91 9876543210 x402', '080-12345678 Extension: 405'
        ext_pattern = r'(?:[\s,\-_/]+(?:ext(?:ension)?\.?|ex\.?|x)\s*[:#]?\s*\d+|\b(?:ext(?:ension)?\.?|ex\.?)\s*[:#]?\s*\d+)'
        cleaned_str = re.sub(ext_pattern, '', raw_str, flags=re.IGNORECASE).strip()

        # Split on multiple phone separators: /, \, comma, semicolon, pipe, newlines, 'or', 'and', '&'
        chunks = re.split(r'[/\\,;|\n\r\t]|(?:\s+(?:or|and|&)\s+)', cleaned_str, flags=re.IGNORECASE)

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue

            # Strip prefixes like 'Mob:', 'Phone:', 'Tel:', 'Contact:'
            chunk_clean = re.sub(r'^(?:mob(?:ile)?|ph(?:one)?|tel(?:ephone)?|contact)\s*[:.\-]?\s*', '', chunk, flags=re.IGNORECASE).strip()

            # Extract pure digits
            digits = re.sub(r'\D', '', chunk_clean)
            if not digits:
                continue

            # Reject all zeros or too short
            if set(digits) == {'0'} or len(digits) < 7:
                continue

            # Strip Indian country code 91 if 12 digits
            if len(digits) == 12 and digits.startswith('91'):
                digits = digits[2:]
            # Strip leading trunk prefix 0 if 11 digits
            elif len(digits) == 11 and digits.startswith('0'):
                digits = digits[1:]

            # A valid primary phone must fit in User.phone_number (max_length=15)
            if 7 <= len(digits) <= 15:
                return digits

        # Secondary fallback: search for a standard 10-digit number in original string
        match = re.search(r'\b(?:\+?91[\-\s]?)?([6-9]\d{9})\b', raw_str)
        if match:
            cand = match.group(1)
            if len(cand) <= 15 and set(cand) != {'0'}:
                return cand

        # If unparseable or overlong without valid components, return empty (save NULL).
        # Never blindly truncate overlong garbage strings.
        return ""

    # =========================================================================
    # STEP 1: VALIDATION & EXTRACTION
    # =========================================================================
    @classmethod
    def validate_and_stage_upload(
        cls,
        zip_file,
        excel_file=None,
        user=None,
        job=None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Validates ZIP and Excel files, safely stages resume files to disk,
        matches Excel metadata to resumes, and creates database job and item records.
        """
        if not zip_file and not excel_file:
            raise ValueError("Please upload a ZIP file of resumes or an Excel file of candidate data.")

        # Check ZIP size
        if zip_file and hasattr(zip_file, 'size') and zip_file.size > MAX_ZIP_SIZE_BYTES:
            raise ValueError(f"ZIP file exceeds maximum allowed size of {MAX_ZIP_SIZE_BYTES // (1024*1024)}MB.")

        # Create temporary working directory for this job
        job_number = cls.generate_job_number()
        temp_base = os.path.join(settings.MEDIA_ROOT, 'temp_bulk_jobs', job_number)
        os.makedirs(temp_base, exist_ok=True)

        extracted_files = []
        skipped_files = []
        total_uncompressed_bytes = 0

        # 1. Read & Extract ZIP securely (optional)
        if zip_file:
            try:
                zip_bytes = zip_file.read()
                if not zipfile.is_zipfile(io.BytesIO(zip_bytes)):
                    raise ValueError("The uploaded file is not a valid ZIP archive.")

                with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                    for zip_info in zf.infolist():
                        raw_filename = zip_info.filename
                        
                        # Ignore directories
                        if zip_info.is_dir() or raw_filename.endswith('/'):
                            continue

                        safe_rel_path = cls.sanitize_zip_path(raw_filename)
                        base_name = os.path.basename(safe_rel_path)
                        
                        # Skip hidden / macOS resource files
                        if base_name.startswith('.') or base_name.startswith('__MACOSX'):
                            continue

                        ext = os.path.splitext(base_name)[1].lower()

                        # Check for dangerous / executable extensions
                        if ext in DANGEROUS_EXTENSIONS:
                            skipped_files.append({
                                "filename": base_name,
                                "reason": f"Dangerous file type rejected ({ext})"
                            })
                            continue

                        # Check for nested zip archives
                        if ext == '.zip':
                            skipped_files.append({
                                "filename": base_name,
                                "reason": "Nested archives are not supported"
                            })
                            continue

                        # Check for supported resume types
                        if ext not in SUPPORTED_EXTENSIONS:
                            skipped_files.append({
                                "filename": base_name,
                                "reason": f"Unsupported file type ({ext or 'no extension'}). Supported: PDF, DOC, DOCX"
                            })
                            continue

                        # Check decompression size (ZIP bomb protection)
                        total_uncompressed_bytes += zip_info.file_size
                        if total_uncompressed_bytes > MAX_UNCOMPRESSED_TOTAL_BYTES:
                            raise ValueError("ZIP archive decompressed size exceeds maximum safe limit (2GB).")

                        # Extract file safely to disk
                        target_disk_path = os.path.join(temp_base, base_name)
                        # Handle duplicate filenames in subdirectories by suffixing
                        counter = 1
                        file_stem, file_ext = os.path.splitext(base_name)
                        while os.path.exists(target_disk_path):
                            target_disk_path = os.path.join(temp_base, f"{file_stem}_{counter}{file_ext}")
                            counter += 1

                        with zf.open(zip_info) as source, open(target_disk_path, 'wb') as dest:
                            dest.write(source.read())

                        extracted_files.append({
                            "filename": os.path.basename(target_disk_path),
                            "disk_path": target_disk_path,
                            "file_size": os.path.getsize(target_disk_path)
                        })

            except Exception as e:
                logger.error(f"[BULK PARSER ZIP ERROR] Failed extracting ZIP: {e}", exc_info=True)
                raise ValueError(f"ZIP processing error: {str(e)}")

        if zip_file and not extracted_files and not skipped_files:
            raise ValueError("The uploaded ZIP archive contains no files.")

        # 2. Parse Excel file if provided
        excel_rows = []
        column_mapping = {}
        excel_filename = ""
        
        if excel_file:
            excel_filename = getattr(excel_file, 'name', 'candidates.xlsx')
            excel_rows, column_mapping = cls.parse_candidate_excel(excel_file)

        # Fail loudly when Excel is the only source but no rows were actually read,
        # instead of reporting a false success with zero candidate rows.
        if not zip_file and excel_file and not excel_rows:
            raise ValueError(
                "No candidate rows could be read from the Excel file. "
                "Please upload a valid .xlsx or .xls file with a header row and at least one candidate row."
            )

        # 3. Match Excel rows with extracted resume files
        matched_count = 0
        excel_matched_indices = set()
        file_excel_map = {}

        if excel_rows:
            # Build lookup indexes from Excel rows
            excel_by_filename = {}
            excel_by_phone = {}
            excel_by_email = {}
            excel_by_name = {}

            for idx, row in enumerate(excel_rows):
                # By resume filename
                rf = row.get('resume_filename') or ''
                if rf:
                    excel_by_filename[cls.normalize_key(rf)] = idx
                    excel_by_filename[rf.strip().lower()] = idx
                # By phone
                p = cls.normalize_phone(row.get('phone'))
                if p:
                    excel_by_phone[p] = idx
                # By email
                e = (row.get('email') or '').strip().lower()
                if e:
                    excel_by_email[e] = idx
                # By name
                n = cls.normalize_key(row.get('name'))
                if n and len(n) > 3:
                    excel_by_name[n] = idx

            # Match each extracted file
            for file_info in extracted_files:
                fname = file_info['filename']
                matched_idx = None

                # Try filename match
                norm_fname = cls.normalize_key(fname)
                if norm_fname in excel_by_filename:
                    matched_idx = excel_by_filename[norm_fname]
                elif fname.strip().lower() in excel_by_filename:
                    matched_idx = excel_by_filename[fname.strip().lower()]
                elif norm_fname in excel_by_name:
                    matched_idx = excel_by_name[norm_fname]

                if matched_idx is not None:
                    file_excel_map[fname] = excel_rows[matched_idx]
                    excel_matched_indices.add(matched_idx)
                    matched_count += 1

        # Excel-only import: when no ZIP is provided, every Excel row becomes a
        # standalone candidate item (no resume file to parse).
        excel_only_rows = []
        if not zip_file and excel_rows:
            excel_only_rows = excel_rows

        # 4. Create database records in atomic transaction
        with transaction.atomic():
            bulk_job = BulkResumeJob.objects.create(
                job_number=job_number,
                user=user,
                job=job,
                status=BulkResumeJob.Status.PENDING,
                zip_filename=getattr(zip_file, 'name', '') if zip_file else '',
                excel_filename=excel_filename,
                storage_dir=temp_base,
                overwrite=overwrite,
                total_files=len(extracted_files) + len(excel_only_rows),
                processed_files=0,
                successful_count=0,
                updated_count=0,
                skipped_count=len(skipped_files),
                failed_count=0,
                validation_summary={
                    "total_detected": len(extracted_files) + len(skipped_files),
                    "valid_resumes": len(extracted_files),
                    "skipped_files": len(skipped_files),
                    "skipped_details": skipped_files,
                    "excel_rows": len(excel_rows),
                    "matched_count": matched_count,
                    "unmatched_excel_count": len(excel_rows) - len(excel_matched_indices),
                    "column_mapping": column_mapping
                }
            )

            # Create items for valid resumes
            item_objs = []
            for file_info in extracted_files:
                fname = file_info['filename']
                excel_meta = file_excel_map.get(fname, {})
                item_objs.append(BulkResumeItem(
                    job=bulk_job,
                    filename=fname,
                    file_path=file_info['disk_path'],
                    file_size=file_info['file_size'],
                    status=BulkResumeItem.Status.PENDING,
                    excel_metadata=excel_meta,
                    candidate_name=excel_meta.get('name', ''),
                    candidate_email=excel_meta.get('email', ''),
                    candidate_phone=excel_meta.get('phone', '')
                ))

            # Also create records for initially skipped files (for complete reporting)
            for skipped in skipped_files:
                item_objs.append(BulkResumeItem(
                    job=bulk_job,
                    filename=skipped['filename'],
                    file_path='',
                    file_size=0,
                    status=BulkResumeItem.Status.SKIPPED,
                    action_taken='SKIPPED_UNSUPPORTED',
                    reason=skipped['reason']
                ))

            # Create items for Excel-only candidate rows (no resume file present)
            for idx, row in enumerate(excel_only_rows):
                fname = (row.get('resume_filename') or '').strip() or f"excel_candidate_{idx + 1}"
                item_objs.append(BulkResumeItem(
                    job=bulk_job,
                    filename=fname,
                    file_path='',
                    file_size=0,
                    status=BulkResumeItem.Status.PENDING,
                    excel_metadata=row,
                    candidate_name=row.get('name', ''),
                    candidate_email=row.get('email', ''),
                    candidate_phone=row.get('phone', '')
                ))

            BulkResumeItem.objects.bulk_create(item_objs)

        return {
            "success": True,
            "job_id": bulk_job.job_number,
            "db_id": str(bulk_job.id),
            "zip_filename": bulk_job.zip_filename,
            "total_detected": len(extracted_files) + len(skipped_files),
            "valid_resumes": len(extracted_files),
            "skipped_files": len(skipped_files),
            "skipped_details": skipped_files,
            "excel_uploaded": bool(excel_file),
            "excel_filename": excel_filename,
            "excel_rows": len(excel_rows),
            "matched_count": matched_count,
            "unmatched_excel_count": len(excel_rows) - len(excel_matched_indices),
            "column_mapping": column_mapping
        }

    # =========================================================================
    # STEP 2: EXCEL PARSER & COLUMN NORMALIZATION
    # =========================================================================
    # Canonical semantic mapping definition for Excel headers
    EXCEL_FIELD_PATTERNS = [
        ('resume_title', [
            r'\bresume\s*title\b',
            r'\bcv\s*title\b',
            r'\bprofile\s*title\b',
            r'\bprofessional\s*summary\b',
            r'\bprofile\s*summary\b',
            r'\bexecutive\s*summary\b',
            r'\bcareer\s*summary\b',
            r'\bcareer\s*objective\b',
            r'\bobjective\b',
            r'\bheadline\b',
            r'\babout(?:\s*me)?\b',
            r'\bbio\b',
            r'^summary$',
        ], "Professional Summary"),

        ('resume_filename', [
            r'\bresume\s*(?:file|filename|attachment|doc|path)\b',
            r'\bcv\s*(?:file|filename|attachment|doc|path)\b',
            r'\bfile\s*name\b',
            r'\bfilename\b',
            r'\battachment\b',
            r'^resume$',
            r'^cv$',
        ], "Resume Filename"),

        ('name', [
            r'\bcandidate\s*name\b',
            r'\bapplicant\s*name\b',
            r'\bfull\s*name\b',
            r'\bname\s*of\s*(?:the\s*)?candidate\b',
            r'^name$',
            r'^candidate$',
        ], "Candidate Name"),

        ('phone', [
            r'\bcontact\s*no\.?\b',
            r'\bcontact\s*num(?:ber)?\b',
            r'\bphone\s*no\.?\b',
            r'\bphone\s*num(?:ber)?\b',
            r'\bmobile\s*no\.?\b',
            r'\bmobile\s*num(?:ber)?\b',
            r'\bcell\s*no\.?\b',
            r'\bcell\s*phone\b',
            r'\btelephone\b',
            r'\btel\s*no\.?\b',
            r'^contact$',
            r'^phone$',
            r'^mobile$',
            r'^cell$',
        ], "Phone"),

        ('email', [
            r'\bemail\s*id\b',
            r'\bemail\s*address\b',
            r'\be-?mail\b',
            r'\bmail\s*id\b',
            r'^email$',
            r'^mail$',
        ], "Email"),

        ('experience', [
            r'\bwork\s*exp(?:erience)?\b',
            r'\btotal\s*exp(?:erience)?\b',
            r'\btotal\s*work\s*exp(?:erience)?\b',
            r'\byears?\s*of\s*exp(?:erience)?\b',
            r'\bexp(?:erience)?\s*(?:in\s*)?years?\b',
            r'\bexp(?:erience)?\s*\(years?\)\b',
            r'\bexp(?:erience)?\s*\(yrs?\)\b',
            r'\byrs\s*exp\b',
            r'\bexp\s*in\s*yrs\b',
            r'^exp$',
            r'^experience$',
        ], "Total Experience"),

        ('expected_salary', [
            r'\bexpected\s*(?:annual\s*)?(?:salary|ctc|package)\b',
            r'\bectc\b',
        ], "Expected CTC"),

        ('salary', [
            r'\bannual\s*salary\b',
            r'\bannual\s*ctc\b',
            r'\bcurrent\s*(?:annual\s*)?salary\b',
            r'\bcurrent\s*(?:annual\s*)?ctc\b',
            r'\bfixed\s*ctc\b',
            r'\btotal\s*ctc\b',
            r'\bgross\s*(?:salary|ctc)\b',
            r'\bannual\s*package\b',
            r'\bcurrent\s*package\b',
            r'^salary$',
            r'^ctc$',
            r'^lpa$',
        ], "Annual Salary"),

        ('preferred_location', [
            r'\bpreferred\s*locations?\b',
            r'\bpref\s*locations?\b',
            r'\bpreferred\s*city\b',
            r'\bpref\s*city\b',
            r'\bdesired\s*location\b',
            r'\brelocation\s*location\b',
            r'\bsub\s*location\b',
            r'^area$',
        ], "Preferred Location"),

        ('location', [
            r'\bcurrent\s*location\b',
            r'\bpresent\s*location\b',
            r'\bcurrent\s*city\b',
            r'\bpresent\s*city\b',
            r'^location$',
            r'^city$',
            r'^town$',
        ], "Current Location"),

        ('company', [
            r'\bcurrent\s*employer\b',
            r'\bcurrent\s*company\b',
            r'\bcurrent\s*org(?:anization)?\b',
            r'\bpresent\s*employer\b',
            r'\bpresent\s*company\b',
            r'\bpresent\s*org(?:anization)?\b',
            r'\bcompany\s*name\b',
            r'^company$',
            r'^employer$',
            r'^organization$',
        ], "Current Company"),

        ('designation', [
            r'\bcurrent\s*designation\b',
            r'\bpresent\s*designation\b',
            r'^designation$',
            r'\bcurrent\s*role\b',
            r'\bpresent\s*role\b',
            r'\bjob\s*role\b',
            r'^role$',
            r'\bcurrent\s*position\b',
            r'\bpresent\s*position\b',
            r'^position$',
            r'\bcurrent\s*job\s*title\b',
            r'\bjob\s*title\b',
        ], "Current Designation"),

        ('post_pg_course', [
            r'\bpost\s*p\.?g\.?\s*course\b',
            r'\bpost\s*pg\s*course\b',
            r'\bpost\s*p\.?g\.?\s*degree\b',
            r'\bpost\s*pg\s*degree\b',
            r'\bpost\s*(?:post\s*|\-)+graduat(?:e|ion)(?:\s*course|\s*degree)?\b',
            r'\bpost\s*p\.?g\.?\b',
            r'\bpost\s*pg\b',
            r'\bppg\s*course\b',
            r'\bppg\b',
            r'\bdoctorate(?:\s*course)?\b',
            r'\bph\.?d(?:\s*course)?\b',
        ], "Post PG Course"),

        ('pg_course', [
            r'\bp\.?g\.?\s*course\b',
            r'\bpg\s*course\b',
            r'\bp\.?g\.?\s*degree\b',
            r'\bpg\s*degree\b',
            r'\bpost\s*graduat(?:e|ion)\s*course\b',
            r'\bpost\s*graduat(?:e|ion)\s*degree\b',
            r'\bpost\s*graduat(?:e|ion)\b',
            r'\bpostgraduate\b',
            r'\bmasters?(?:(?:\'|\")?s)?(?:\s*degree|\s*course)?\b',
            r'^p\.?g\.?$',
            r'^pg$',
            r'^post\s*graduate$',
        ], "PG Course"),

        ('ug_course', [
            r'\bu\.?g\.?\s*course\b',
            r'\bug\s*course\b',
            r'\bu\.?g\.?\s*degree\b',
            r'\bug\s*degree\b',
            r'\bunder\s*graduat(?:e|ion)\s*course\b',
            r'\bundergraduate\s*course\b',
            r'\bunder\s*graduat(?:e|ion)\s*degree\b',
            r'\bundergraduate\s*degree\b',
            r'\bunder\s*graduat(?:e|ion)\b',
            r'\bundergraduate\b',
            r'\bgraduat(?:e|ion)\s*course\b',
            r'\bgraduat(?:e|ion)\s*degree\b',
            r'\bbachelors?(?:(?:\'|\")?s)?(?:\s*degree|\s*course)?\b',
            r'\bbasic\s*graduat(?:e|ion)\b',
            r'^graduat(?:e|ion)$',
            r'^graduate$',
            r'^u\.?g\.?$',
            r'^ug$',
        ], "UG Course"),

        ('ug_institute', [
            r'\bu\.?g\.?\s*(?:college|institute|university)\b',
            r'\bug\s*(?:college|institute|university)\b',
            r'\bgraduat(?:e|ion)\s*(?:college|institute|university)\b',
        ], "UG Institute"),

        ('pg_institute', [
            r'\bp\.?g\.?\s*(?:college|institute|university)\b',
            r'\bpg\s*(?:college|institute|university)\b',
            r'\bpost\s*graduat(?:e|ion)\s*(?:college|institute|university)\b',
        ], "PG Institute"),

        ('ug_year', [
            r'\bu\.?g\.?\s*(?:passing\s*)?year\b',
            r'\bug\s*(?:passing\s*)?year\b',
            r'\bgraduat(?:e|ion)\s*(?:passing\s*)?year\b',
        ], "UG Passing Year"),

        ('pg_year', [
            r'\bp\.?g\.?\s*(?:passing\s*)?year\b',
            r'\bpg\s*(?:passing\s*)?year\b',
            r'\bpost\s*graduat(?:e|ion)\s*(?:passing\s*)?year\b',
        ], "PG Passing Year"),

        ('skills', [
            r'\bkey\s*skills\b',
            r'\bprimary\s*skills\b',
            r'\bit\s*skills\b',
            r'\btechnical\s*skills\b',
            r'\btech\s*stack\b',
            r'^skills$',
        ], "Skills"),

        ('notice_period', [
            r'\bnotice\s*period\b',
            r'^notice$',
            r'^np$',
        ], "Notice Period"),

        ('dob', [
            r'\bdate\s*of\s*birth\b',
            r'^dob$',
            r'\bbirth\s*date\b',
        ], "Date of Birth"),

        ('gender', [
            r'^gender$',
            r'^sex$',
        ], "Gender"),

        ('department', [
            r'\bfunctional\s*area\b',
            r'^department$',
            r'^function$',
        ], "Department"),

        ('industry', [
            r'^industry$',
        ], "Industry"),

        ('linkedin', [
            r'\blinkedin(?:\s*url|\s*profile)?\b',
        ], "LinkedIn URL"),

        ('interviewed', [
            r'\binterview\s*status\b',
            r'^interviewed$',
            r'^status$',
        ], "Interview Status"),
    ]

    @classmethod
    def _match_column_header(cls, header_text: Any) -> Tuple[Optional[str], Optional[str]]:
        """
        Semantically matches an uploaded column header to a known canonical field
        and human-friendly display label, independent of column position.
        """
        if header_text is None:
            return None, None
        h_clean = str(header_text).strip()
        if not h_clean:
            return None, None
        h_lower = h_clean.lower()
        h_norm = ' '.join(re.sub(r'[\._\-/]', ' ', h_lower).split())

        for field, patterns, disp in cls.EXCEL_FIELD_PATTERNS:
            for pat in patterns:
                if re.search(pat, h_lower) or re.search(pat, h_norm):
                    return field, disp
        return None, None

    @classmethod
    def parse_candidate_excel(cls, excel_file) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Parses an uploaded Excel (.xlsx, .xls) workbook according to the TalentVault
        candidate data structure using semantic header matching. Preserves full
        Excel data so no columns are discarded.
        """
        if hasattr(excel_file, 'seek'):
            excel_file.seek(0)
        file_bytes = excel_file.read()
        filename = getattr(excel_file, 'name', '')

        rows = cls._read_excel_rows(file_bytes, filename)

        # Drop fully-empty rows before detecting the header row.
        rows = [r for r in rows if any(v is not None and str(v).strip() != '' for v in r)]
        if not rows:
            return [], {}

        header_idx = cls._detect_header_row(rows)
        if header_idx is None:
            return [], {}

        header_row = rows[header_idx]
        header_map = {}
        column_mapping_display = {}

        for col_idx, header_text in enumerate(header_row):
            field_name, disp_name = cls._match_column_header(header_text)
            if field_name:
                header_map[col_idx] = field_name
                column_mapping_display[str(header_text).strip()] = disp_name

        # Parse rows below the detected header row.
        parsed_candidate_rows = []
        for row_values in rows[header_idx + 1:]:
            row_data = {}
            raw_columns = {}
            for col_idx, cell_value in enumerate(row_values):
                if cell_value is None or str(cell_value).strip() == '':
                    continue
                cell_str = str(cell_value).strip()

                # Preserve full original column header -> value
                if col_idx < len(header_row) and header_row[col_idx] is not None:
                    raw_h = str(header_row[col_idx]).strip()
                    if raw_h:
                        raw_columns[raw_h] = cell_str
                        # Also expose raw column name on row_data so non-standard columns aren't lost
                        row_data[raw_h] = cell_str

                field_name = header_map.get(col_idx)
                if field_name:
                    row_data[field_name] = cell_str

            if not row_data:
                continue

            # Populate backward/forward convenient aliases
            if 'resume_title' in row_data and 'summary' not in row_data:
                row_data['summary'] = row_data['resume_title']
            if 'preferred_location' in row_data and 'sub_location' not in row_data:
                row_data['sub_location'] = row_data['preferred_location']
            if 'salary' in row_data and 'current_salary' not in row_data:
                row_data['current_salary'] = row_data['salary']
            if 'experience' in row_data and 'work_exp' not in row_data:
                row_data['work_exp'] = row_data['experience']

            # Attach full raw dictionary to preserve 100% of the Excel data
            row_data['_raw'] = raw_columns

            # Require at least one identifying property (Name, Phone, Email, Resume filename, Company, or Resume Title)
            if any(row_data.get(k) for k in ['name', 'phone', 'email', 'resume_filename', 'company', 'resume_title']):
                parsed_candidate_rows.append(row_data)

        return parsed_candidate_rows, column_mapping_display

    @classmethod
    def _read_excel_rows(cls, file_bytes: bytes, filename: str = '') -> List[List[Any]]:
        """
        Reads an Excel workbook into a list of rows, supporting both .xlsx
        (openpyxl) and legacy .xls (xlrd) formats.
        """
        import openpyxl

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            sheet = wb.active
            return [list(r) for r in sheet.iter_rows(values_only=True)]
        except Exception as openpyxl_err:
            try:
                import xlrd
                book = xlrd.open_workbook(file_contents=file_bytes)
                sheet = book.sheet_by_index(0)
                rows = []
                for r in range(sheet.nrows):
                    row = []
                    for c in range(sheet.ncols):
                        cell = sheet.cell(r, c)
                        value = cell.value
                        # Keep phone numbers / numeric IDs as clean integers.
                        if cell.ctype == xlrd.XL_CELL_NUMBER and isinstance(value, float) and value.is_integer():
                            value = int(value)
                        row.append(value)
                    rows.append(row)
                return rows
            except Exception:
                raise ValueError(
                    f"Could not read Excel file '{filename or 'upload'}'. "
                    f"Only valid .xlsx and .xls files are supported."
                ) from openpyxl_err

    @classmethod
    def _detect_header_row(cls, rows: List[List[Any]], field_patterns: Any = None, max_scan: int = 10) -> Optional[int]:
        """
        Finds the header row by scanning the first few rows and selecting the row
        with the most recognized candidate-data columns (handles title/leading rows).
        """
        best_idx = None
        best_score = 0
        limit = min(len(rows), max_scan)
        for idx in range(limit):
            matched = 0
            for cell in rows[idx]:
                field_name, _ = cls._match_column_header(cell)
                if field_name:
                    matched += 1
            if matched > best_score:
                best_score = matched
                best_idx = idx

        # Require at least two recognized columns to consider a row a header.
        if best_idx is None or best_score < 2:
            return None
        return best_idx

    @classmethod
    def get_job(cls, job_number_or_id: str) -> Optional[BulkResumeJob]:
        """Safely fetches BulkResumeJob by UUID or human-readable job_number."""
        if not job_number_or_id:
            return None
        import uuid
        job_str = str(job_number_or_id).strip()
        try:
            val = uuid.UUID(job_str)
            job = BulkResumeJob.objects.filter(id=val).first()
            if job:
                return job
        except (ValueError, TypeError, AttributeError):
            pass
        return BulkResumeJob.objects.filter(job_number=job_str).first()

    # =========================================================================
    # STEP 3: ASYNCHRONOUS BATCH PROCESSING ENGINE
    # =========================================================================
    @classmethod
    def start_background_processing(cls, job_number_or_id: str, overwrite: Optional[bool] = None, sync: bool = False) -> bool:
        """
        Launches background thread for non-blocking parsing of the bulk job.
        If sync=True, executes synchronously in current thread (useful for testing).
        """
        job = cls.get_job(job_number_or_id)
        if not job:
            raise ValueError(f"Job {job_number_or_id} not found.")

        if job.status == BulkResumeJob.Status.PROCESSING:
            return True  # Already running

        if overwrite is not None:
            job.overwrite = overwrite
            job.save(update_fields=['overwrite'])

        job.status = BulkResumeJob.Status.PROCESSING
        job.started_at = timezone.now()
        job.save(update_fields=['status', 'started_at'])

        if sync:
            cls._run_bulk_job_worker(str(job.id))
            return True

        # Launch independent background daemon thread
        worker_thread = threading.Thread(
            target=cls._run_bulk_job_worker,
            args=(str(job.id),),
            daemon=True,
            name=f"BulkParserWorker-{job.job_number}"
        )
        worker_thread.start()
        return True

    @classmethod
    def _run_bulk_job_worker(cls, job_id: str):
        """
        Worker thread function that processes items in batches of 5-10 with memory cleanup.
        """
        connection.close()  # Refresh DB connection in thread

        job = None
        for attempt in range(5):
            try:
                job = BulkResumeJob.objects.get(id=job_id)
                break
            except Exception:
                time.sleep(0.05)

        if not job:
            logger.error(f"[BULK WORKER] Job {job_id} could not be loaded.")
            return

        logger.info(f"[BULK WORKER START] Starting processing for Job {job.job_number} (Total valid: {job.total_files})")

        # Query pending items
        pending_items = list(job.items.filter(status=BulkResumeItem.Status.PENDING).order_by('id'))
        
        batch_size = DEFAULT_BATCH_SIZE
        user = job.user
        job_target = job.job
        overwrite = job.overwrite

        for i in range(0, len(pending_items), batch_size):
            batch = pending_items[i:i + batch_size]
            
            for item in batch:
                cls._process_single_item(item, job, user=user, job_target=job_target, overwrite=overwrite)
                # Yield between files so the web worker can keep serving requests
                # while a long bulk parse is running in the background thread.
                time.sleep(0.02)

            # Memory management: Garbage collection after each batch
            gc.collect()
            time.sleep(0.02)  # Small yield for I/O and server responsiveness

        # Finalize job status
        with transaction.atomic():
            job.refresh_from_db()
            job.status = BulkResumeJob.Status.COMPLETED
            job.completed_at = timezone.now()
            job.current_file = ""
            job.save()

        logger.info(f"[BULK WORKER COMPLETED] Finished Job {job.job_number}: Success={job.successful_count}, Updated={job.updated_count}, Skipped={job.skipped_count}, Failed={job.failed_count}")
        connection.close()

    @classmethod
    def _process_single_item(
        cls,
        item: BulkResumeItem,
        job: BulkResumeJob,
        user: Optional[User] = None,
        job_target=None,
        overwrite: bool = False
    ):
        """
        Processes a single resume file with independent error isolation, atomic DB save,
        and timeout protection.
        """
        item.status = BulkResumeItem.Status.PROCESSING
        item.save(update_fields=['status'])

        # Update job's live current_file
        job.current_file = item.filename
        job.save(update_fields=['current_file'])

        file_path = item.file_path
        if not file_path and item.excel_metadata:
            # Excel-only candidate row (no resume file): create/update from metadata.
            cls._process_excel_only_item(item, job, user=user, job_target=job_target, overwrite=overwrite)
            return

        if not file_path or not os.path.exists(file_path):
            item.status = BulkResumeItem.Status.FAILED
            item.action_taken = 'FAILED'
            item.reason = "Resume file not found on staging disk."
            item.processed_at = timezone.now()
            item.save()

            BulkResumeJob.objects.filter(id=job.id).update(
                processed_files=models.F('processed_files') + 1,
                failed_count=models.F('failed_count') + 1
            )
            return

        # Attempt isolated parsing
        try:
            excel_data = item.excel_metadata or {}
            cand_email = (excel_data.get('email') or item.candidate_email or '').strip()
            cand_phone = cls.normalize_phone(excel_data.get('phone') or item.candidate_phone or '')

            # Check duplicate by Excel metadata if overwrite is False
            if not overwrite and (cand_email or cand_phone):
                existing_user = None
                if cand_email:
                    existing_user = User.objects.filter(email=cand_email).first()
                if not existing_user and cand_phone:
                    existing_user = User.objects.filter(phone_number=cand_phone).first()

                if existing_user:
                    profile = getattr(existing_user, 'candidate_profile', None)
                    item.status = BulkResumeItem.Status.SKIPPED
                    item.action_taken = 'SKIPPED_DUPLICATE'
                    item.candidate = profile
                    item.candidate_name = (profile.full_name if profile else "") or excel_data.get('name', '')
                    item.candidate_email = (profile.user.email if profile else "") or cand_email
                    item.candidate_phone = (profile.user.phone_number if profile else "") or cand_phone
                    item.reason = "Duplicate profile skipped (Email or Mobile number already exists)."
                    item.processed_at = timezone.now()
                    item.save()

                    DuplicateResumeLog.objects.create(
                        email=cand_email,
                        phone=cand_phone,
                        filename=item.filename,
                        action_taken='SKIPPED'
                    )

                    BulkResumeJob.objects.filter(id=job.id).update(
                        processed_files=models.F('processed_files') + 1,
                        skipped_count=models.F('skipped_count') + 1
                    )
                    return

            is_existing_candidate = False
            if cand_email or cand_phone:
                q_user = Q()
                if cand_email:
                    q_user |= Q(email=cand_email)
                if cand_phone:
                    q_user |= Q(phone_number=cand_phone)
                is_existing_candidate = User.objects.filter(q_user).exists()

            with open(file_path, 'rb') as f:
                file_bytes = f.read()

            file_obj = io.BytesIO(file_bytes)
            
            # Use candidate utils process_resume_file
            profile, status = process_resume_file(
                file_obj=file_obj,
                filename=item.filename,
                overwrite=overwrite,
                user=None,
                uploaded_by=user
            )

            # Apply Excel metadata override/enrichment if available
            if profile and excel_data:
                cls._enrich_profile_from_excel(profile, excel_data)

            # Map candidate to job if job_target is set
            if profile and job_target:
                from apps.applications.models import Application
                from services.candidate_matching_service import CandidateMatchingService
                try:
                    app, created = Application.objects.get_or_create(job=job_target, candidate=profile)
                    CandidateMatchingService.update_ats_scores(candidate_id=profile.id, job_id=job_target.id)
                except Exception as e_map:
                    logger.warning(f"Error mapping bulk candidate {profile.id} to job {job_target.id}: {e_map}")

            # Record success / duplicate outcome
            if status == "SUCCESS":
                if overwrite and is_existing_candidate:
                    item.status = BulkResumeItem.Status.UPDATED
                    item.action_taken = 'UPDATED'
                    item.candidate = profile
                    item.candidate_name = profile.full_name or excel_data.get('name', '')
                    item.candidate_email = profile.user.email
                    item.candidate_phone = profile.user.phone_number or excel_data.get('phone', '')
                    item.reason = "Existing candidate profile updated."
                    item.processed_at = timezone.now()
                    item.save()

                    BulkResumeJob.objects.filter(id=job.id).update(
                        processed_files=models.F('processed_files') + 1,
                        updated_count=models.F('updated_count') + 1
                    )
                else:
                    item.status = BulkResumeItem.Status.COMPLETED
                    item.action_taken = 'CREATED'
                    item.candidate = profile
                    item.candidate_name = profile.full_name or excel_data.get('name', '')
                    item.candidate_email = profile.user.email
                    item.candidate_phone = profile.user.phone_number or excel_data.get('phone', '')
                    item.reason = "Candidate profile created successfully."
                    item.processed_at = timezone.now()
                    item.save()

                    BulkResumeJob.objects.filter(id=job.id).update(
                        processed_files=models.F('processed_files') + 1,
                        successful_count=models.F('successful_count') + 1
                    )

            elif status == "DUPLICATE":
                if overwrite and profile:
                    item.status = BulkResumeItem.Status.UPDATED
                    item.action_taken = 'UPDATED'
                    item.candidate = profile
                    item.candidate_name = profile.full_name or excel_data.get('name', '')
                    item.candidate_email = profile.user.email
                    item.candidate_phone = profile.user.phone_number or excel_data.get('phone', '')
                    item.reason = "Existing candidate profile updated."
                    item.processed_at = timezone.now()
                    item.save()

                    BulkResumeJob.objects.filter(id=job.id).update(
                        processed_files=models.F('processed_files') + 1,
                        updated_count=models.F('updated_count') + 1
                    )
                else:
                    item.status = BulkResumeItem.Status.SKIPPED
                    item.action_taken = 'SKIPPED_DUPLICATE'
                    item.candidate = profile
                    item.candidate_name = (profile.full_name if profile else "") or excel_data.get('name', '')
                    item.candidate_email = (profile.user.email if profile else "") or excel_data.get('email', '')
                    item.candidate_phone = (profile.user.phone_number if profile else "") or excel_data.get('phone', '')
                    item.reason = "Duplicate profile skipped (Email or Mobile number already exists)."
                    item.processed_at = timezone.now()
                    item.save()

                    BulkResumeJob.objects.filter(id=job.id).update(
                        processed_files=models.F('processed_files') + 1,
                        skipped_count=models.F('skipped_count') + 1
                    )
            else:
                # Parsing failed for this single document
                reason_detail = cls._map_error_status(status)
                item.status = BulkResumeItem.Status.FAILED
                item.action_taken = 'FAILED'
                item.reason = reason_detail
                item.candidate_name = excel_data.get('name', '')
                item.candidate_email = excel_data.get('email', '')
                item.candidate_phone = excel_data.get('phone', '')
                item.processed_at = timezone.now()
                item.save()

                BulkResumeJob.objects.filter(id=job.id).update(
                    processed_files=models.F('processed_files') + 1,
                    failed_count=models.F('failed_count') + 1
                )

        except Exception as e:
            logger.error(f"[BULK PARSE FILE FAILED] File {item.filename}: {e}", exc_info=True)
            item.status = BulkResumeItem.Status.FAILED
            item.action_taken = 'FAILED'
            item.reason = f"Unexpected parser error: {str(e)[:200]}"
            item.processed_at = timezone.now()
            item.save()

            BulkResumeJob.objects.filter(id=job.id).update(
                processed_files=models.F('processed_files') + 1,
                failed_count=models.F('failed_count') + 1
            )

    @classmethod
    def _process_excel_only_item(
        cls,
        item: BulkResumeItem,
        job: BulkResumeJob,
        user: Optional[User] = None,
        job_target=None,
        overwrite: bool = False
    ):
        """
        Creates or updates a candidate profile directly from an Excel row when no
        resume file is attached to the item (Excel-only import).
        """
        excel_data = item.excel_metadata or {}

        name = (excel_data.get('name') or '').strip()
        email = (excel_data.get('email') or '').strip().lower()
        phone = cls.normalize_phone(excel_data.get('phone') or '')

        if not name and not email and not phone:
            item.status = BulkResumeItem.Status.SKIPPED
            item.action_taken = 'SKIPPED_NO_IDENTITY'
            item.reason = "Excel row has no candidate name, email, or phone to import."
            item.processed_at = timezone.now()
            item.save()

            BulkResumeJob.objects.filter(id=job.id).update(
                processed_files=models.F('processed_files') + 1,
                skipped_count=models.F('skipped_count') + 1
            )
            return

        try:
            # Stable login identifier for candidates without a real email.
            login_email = email if (email and not is_placeholder_email(email)) else make_internal_login_email(f"excel:{phone or name or item.filename}")

            # Duplicate detection by email or phone.
            existing_user = None
            if email:
                existing_user = User.objects.filter(email=email).first()
            if not existing_user and phone:
                existing_user = User.objects.filter(phone_number=phone).first()

            if existing_user and not overwrite:
                profile = getattr(existing_user, 'candidate_profile', None)
                item.status = BulkResumeItem.Status.SKIPPED
                item.action_taken = 'SKIPPED_DUPLICATE'
                item.candidate = profile
                item.candidate_name = (profile.full_name if profile else "") or name
                item.candidate_email = (profile.user.email if profile else "") or email
                item.candidate_phone = (profile.user.phone_number if profile else "") or phone
                item.reason = "Duplicate profile skipped (Email or Mobile number already exists)."
                item.processed_at = timezone.now()
                item.save()

                DuplicateResumeLog.objects.create(
                    email=email,
                    phone=phone,
                    filename=item.filename,
                    action_taken='SKIPPED'
                )

                BulkResumeJob.objects.filter(id=job.id).update(
                    processed_files=models.F('processed_files') + 1,
                    skipped_count=models.F('skipped_count') + 1
                )
                return

            if existing_user and overwrite:
                user_obj = existing_user
                if phone:
                    user_obj.phone_number = phone
                user_obj.save(update_fields=['phone_number'])
                DuplicateResumeLog.objects.create(
                    email=email,
                    phone=phone,
                    filename=item.filename,
                    action_taken='UPDATED'
                )
                was_existing = True
            else:
                user_obj, created_user = User.objects.get_or_create(
                    email=login_email,
                    defaults={'role': User.Role.CANDIDATE, 'phone_number': phone or None}
                )
                if created_user:
                    user_obj.set_unusable_password()
                    user_obj.save()
                was_existing = False

            profile, created_profile = CandidateProfile.objects.get_or_create(user=user_obj)

            cls._enrich_profile_from_excel(profile, excel_data)

            if not profile.location:
                profile.location = 'Unknown'
                profile.save(update_fields=['location'])

            # Map candidate to job if job_target is set.
            if job_target:
                from apps.applications.models import Application
                from services.candidate_matching_service import CandidateMatchingService
                try:
                    Application.objects.get_or_create(job=job_target, candidate=profile)
                    CandidateMatchingService.update_ats_scores(candidate_id=profile.id, job_id=job_target.id)
                except Exception as e_map:
                    logger.warning(f"Error mapping bulk candidate {profile.id} to job {job_target.id}: {e_map}")

            item.candidate = profile
            item.candidate_name = profile.full_name or name
            item.candidate_email = profile.user.email
            item.candidate_phone = profile.user.phone_number or phone
            item.processed_at = timezone.now()

            if overwrite and was_existing:
                item.status = BulkResumeItem.Status.UPDATED
                item.action_taken = 'UPDATED'
                item.reason = "Existing candidate profile updated."
            else:
                item.status = BulkResumeItem.Status.COMPLETED
                item.action_taken = 'CREATED'
                item.reason = "Candidate profile created from Excel data."
            item.save()

            if overwrite and was_existing:
                BulkResumeJob.objects.filter(id=job.id).update(
                    processed_files=models.F('processed_files') + 1,
                    updated_count=models.F('updated_count') + 1
                )
            else:
                BulkResumeJob.objects.filter(id=job.id).update(
                    processed_files=models.F('processed_files') + 1,
                    successful_count=models.F('successful_count') + 1
                )

        except Exception as e:
            logger.error(f"[BULK EXCEL IMPORT FAILED] Row {item.filename}: {e}", exc_info=True)
            item.status = BulkResumeItem.Status.FAILED
            item.action_taken = 'FAILED'
            item.reason = f"Unexpected Excel import error: {str(e)[:200]}"
            item.processed_at = timezone.now()
            item.save()

            BulkResumeJob.objects.filter(id=job.id).update(
                processed_files=models.F('processed_files') + 1,
                failed_count=models.F('failed_count') + 1
            )

    @classmethod
    def _parse_salary_value(cls, val: Any) -> Optional[Decimal]:
        """
        Parses salary / CTC values from Excel.
        Handles:
        - "1200000", "12,00,000", "Rs. 12,00,000", "INR 1200000"
        - "12 LPA", "12.5 Lakhs", "12.5 Lacs", "12.5"
        - numeric 1200000, 12, 12.5
        """
        if val is None:
            return None
        val_str = str(val).strip()
        if not val_str or val_str.lower() in ('none', 'null', 'nan', '-', 'n/a'):
            return None

        # Clean string: remove currency signs and commas
        cleaned = re.sub(r'[\$,₹]', '', val_str, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(?:rs\.?|inr|inr\.)\b', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.replace(',', '').strip()

        is_lpa = bool(re.search(r'\b(?:lpa|lakhs?|lacs?)\b', val_str, re.IGNORECASE))

        # Extract numeric portion
        match = re.search(r'\d+(?:\.\d+)?', cleaned)
        if not match:
            return None

        try:
            num = float(match.group(0))
            if is_lpa or num < 100.0:
                amount = num * 100000.0
            else:
                amount = num
            return Decimal(str(round(amount, 2)))
        except Exception:
            return None

    @classmethod
    def _parse_experience_value(cls, val: Any) -> Optional[Decimal]:
        """
        Parses total experience in years from Excel.
        Handles:
        - "5", "5.5", 5, 5.5
        - "5 Years", "5 Yrs", "5.5 yrs", "5 Years 6 Months", "5 yrs 6 mos"
        - "Fresher", "0"
        """
        if val is None:
            return None
        val_str = str(val).strip()
        if not val_str or val_str.lower() in ('none', 'null', 'nan', '-', 'n/a'):
            return None

        if val_str.lower() in ('fresher', 'entry level'):
            return Decimal('0.0')

        years_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:years?|yrs?)', val_str, re.IGNORECASE)
        months_match = re.search(r'(\d+)\s*(?:months?|mos?)', val_str, re.IGNORECASE)

        if years_match or months_match:
            years = float(years_match.group(1)) if years_match else 0.0
            months = float(months_match.group(1)) if months_match else 0.0
            total = years + (months / 12.0)
            return Decimal(str(round(min(total, 99.9), 1)))

        match = re.search(r'\d+(?:\.\d+)?', val_str)
        if match:
            try:
                num = float(match.group(0))
                return Decimal(str(round(min(num, 99.9), 1)))
            except Exception:
                return None
        return None

    @classmethod
    def _parse_notice_period(cls, val: Any) -> Optional[int]:
        if val is None:
            return None
        val_str = str(val).strip().lower()
        if not val_str or val_str in ('none', 'null', 'nan', '-'):
            return None
        if 'immediate' in val_str or val_str == '0':
            return 0
        match = re.search(r'\d+', val_str)
        if match:
            try:
                days = int(match.group(0))
                if 'month' in val_str:
                    days = days * 30
                return days
            except Exception:
                pass
        return None

    @classmethod
    def _parse_year(cls, val: Any) -> Optional[int]:
        if val is None:
            return None
        match = re.search(r'\b(19\d\d|20\d\d)\b', str(val))
        if match:
            try:
                return int(match.group(1))
            except Exception:
                pass
        return None

    @classmethod
    def _sync_excel_experience(cls, profile: CandidateProfile, company: str, designation: str, summary: str = ""):
        comp = (company or profile.current_company or '').strip()
        desig = (designation or profile.current_designation or '').strip()
        if not comp and not desig:
            return

        existing_exp = profile.experiences.filter(is_current=True).first()
        if existing_exp:
            if comp and not existing_exp.company_name:
                existing_exp.company_name = comp[:255]
            if desig and not existing_exp.designation:
                existing_exp.designation = desig[:255]
            existing_exp.save()
        else:
            match = profile.experiences.filter(company_name__iexact=comp).first() if comp else None
            if match:
                if desig:
                    match.designation = desig[:255]
                match.is_current = True
                match.save()
            else:
                Experience.objects.create(
                    profile=profile,
                    company_name=(comp or "Current Employer")[:255],
                    designation=(desig or "Current Role")[:255],
                    is_current=True,
                    description=summary[:1000] if summary else ""
                )

    @classmethod
    def _sync_excel_education(cls, profile: CandidateProfile, excel_data: Dict[str, Any]):
        # U.G. Course -> Education / Undergraduate
        ug_course = (excel_data.get('ug_course') or '').strip()
        if ug_course:
            ug_inst = (excel_data.get('ug_institute') or "Not Specified").strip()
            ug_year = cls._parse_year(excel_data.get('ug_year'))
            existing_ug = profile.educations.filter(
                qualification_level=Education.QualificationLevel.UG
            ).first()
            if existing_ug:
                existing_ug.degree = ug_course[:255]
                if ug_inst and existing_ug.institution in ("", "Not Specified"):
                    existing_ug.institution = ug_inst[:255]
                if ug_year:
                    existing_ug.passing_year = ug_year
                existing_ug.save()
            else:
                Education.objects.create(
                    profile=profile,
                    qualification_level=Education.QualificationLevel.UG,
                    degree=ug_course[:255],
                    institution=ug_inst[:255],
                    passing_year=ug_year
                )

        # P.G. Course -> Education / Postgraduate
        pg_course = (excel_data.get('pg_course') or '').strip()
        if pg_course:
            pg_inst = (excel_data.get('pg_institute') or "Not Specified").strip()
            pg_year = cls._parse_year(excel_data.get('pg_year'))
            existing_pg = profile.educations.filter(
                qualification_level=Education.QualificationLevel.PG
            ).first()
            if existing_pg:
                existing_pg.degree = pg_course[:255]
                if pg_inst and existing_pg.institution in ("", "Not Specified"):
                    existing_pg.institution = pg_inst[:255]
                if pg_year:
                    existing_pg.passing_year = pg_year
                existing_pg.save()
            else:
                Education.objects.create(
                    profile=profile,
                    qualification_level=Education.QualificationLevel.PG,
                    degree=pg_course[:255],
                    institution=pg_inst[:255],
                    passing_year=pg_year
                )

        # Post P.G. Course -> Education / Postgraduate / Additional Education
        post_pg_course = (excel_data.get('post_pg_course') or '').strip()
        if post_pg_course:
            post_pg_lower = post_pg_course.lower()
            if any(term in post_pg_lower for term in ['ph.d', 'phd', 'doctor', 'doctorate']):
                qual_level = Education.QualificationLevel.DOCTORATE
            else:
                qual_level = Education.QualificationLevel.PG

            existing_post_pg = profile.educations.filter(
                degree__iexact=post_pg_course
            ).first()
            if not existing_post_pg:
                Education.objects.create(
                    profile=profile,
                    qualification_level=qual_level,
                    degree=post_pg_course[:255],
                    institution="Not Specified"
                )

    @classmethod
    def _sync_excel_skills(cls, profile: CandidateProfile, excel_data: Dict[str, Any]):
        skills_raw = (excel_data.get('skills') or '').strip()
        if not skills_raw:
            return

        skill_names = [s.strip() for s in re.split(r'[,;\n|/]', skills_raw) if s.strip()]
        existing_skills = set(profile.skills.values_list('skill_name', flat=True))
        new_skills = []
        for s in skill_names:
            clean_s = s.title()[:100]
            if clean_s.lower() not in {e.lower() for e in existing_skills}:
                new_skills.append(CandidateSkill(
                    profile=profile,
                    skill_name=clean_s
                ))
                existing_skills.add(clean_s)

        if new_skills:
            CandidateSkill.objects.bulk_create(new_skills, ignore_conflicts=True)

        if not profile.original_skills:
            profile.original_skills = list(existing_skills)
            profile.save(update_fields=['original_skills'])

    @classmethod
    def _enrich_profile_from_excel(cls, profile: CandidateProfile, excel_data: Dict[str, Any]):
        """
        Enriches candidate profile and related records (Experience, Education, Skills)
        using validated Excel metadata according to the required semantic field mapping.
        """
        if not profile or not excel_data:
            return

        dirty_profile = False
        dirty_user = False
        user_obj = getattr(profile, 'user', None)

        # 1. Candidate Name -> Candidate Name
        name = (excel_data.get('name') or excel_data.get('candidate_name') or '').strip()
        if name and (not profile.full_name or profile.full_name.lower() in ('unknown', 'candidate', '')):
            profile.full_name = name[:255]
            dirty_profile = True
        elif name and profile.full_name != name:
            profile.full_name = name[:255]
            dirty_profile = True

        # 2. Resume Title -> Professional Summary
        # CRITICAL: Do NOT put Resume Title into designation!
        # CRITICAL: Do NOT put U.G./P.G. course into summary!
        resume_title = (excel_data.get('resume_title') or excel_data.get('summary') or '').strip()
        if resume_title:
            profile.summary = resume_title
            profile.original_summary = resume_title
            dirty_profile = True

        # 3. Contact No. -> Phone (User model & candidate profile)
        phone_raw = excel_data.get('phone') or excel_data.get('contact_number') or excel_data.get('contact_no')
        if phone_raw and user_obj:
            norm_phone = cls.normalize_phone(phone_raw)
            if norm_phone and norm_phone != user_obj.phone_number:
                if not User.objects.filter(phone_number=norm_phone).exclude(id=user_obj.id).exists():
                    user_obj.phone_number = norm_phone
                    dirty_user = True

        # 4. Email -> Email (User model)
        email_raw = (excel_data.get('email') or '').strip().lower()
        if email_raw and user_obj:
            if not user_obj.email or is_placeholder_email(user_obj.email) or user_obj.email != email_raw:
                if not User.objects.filter(email=email_raw).exclude(id=user_obj.id).exists():
                    user_obj.email = email_raw
                    dirty_user = True

        # 5. Work Exp -> Total Experience (CandidateProfile.total_experience)
        exp_raw = excel_data.get('experience') or excel_data.get('work_exp')
        if exp_raw is not None and str(exp_raw).strip() != '':
            parsed_exp = cls._parse_experience_value(exp_raw)
            if parsed_exp is not None:
                profile.total_experience = parsed_exp
                dirty_profile = True

        # 6. Annual Salary -> Current/Annual CTC (CandidateProfile.current_salary)
        # CRITICAL: Do NOT lose Annual Salary!
        salary_raw = excel_data.get('salary') or excel_data.get('annual_salary') or excel_data.get('current_salary') or excel_data.get('ctc')
        if salary_raw is not None and str(salary_raw).strip() != '':
            parsed_salary = cls._parse_salary_value(salary_raw)
            if parsed_salary is not None:
                profile.current_salary = parsed_salary
                dirty_profile = True

        exp_sal_raw = excel_data.get('expected_salary') or excel_data.get('expected_ctc')
        if exp_sal_raw is not None and str(exp_sal_raw).strip() != '':
            parsed_exp_sal = cls._parse_salary_value(exp_sal_raw)
            if parsed_exp_sal is not None:
                profile.expected_salary = parsed_exp_sal
                dirty_profile = True

        # 7. Current Location -> Current Location (CandidateProfile.location)
        curr_loc = (excel_data.get('location') or excel_data.get('current_location') or '').strip()
        if curr_loc:
            profile.location = curr_loc[:100]
            dirty_profile = True
        elif not profile.location:
            profile.location = 'Unknown'
            dirty_profile = True

        # 8. Preferred Location -> Preferred Location (CandidateProfile.preferred_location)
        pref_loc = (excel_data.get('preferred_location') or excel_data.get('sub_location') or '').strip()
        if pref_loc:
            profile.preferred_location = pref_loc[:255]
            dirty_profile = True

        # 9. Current Employer -> Current Company (CandidateProfile.current_company)
        company = (excel_data.get('company') or excel_data.get('current_employer') or '').strip()
        if company:
            profile.current_company = company[:255]
            dirty_profile = True

        # 10. Designation -> Current Designation (CandidateProfile.current_designation)
        designation = (excel_data.get('designation') or '').strip()
        if designation:
            profile.current_designation = designation[:255]
            dirty_profile = True

        # 11. Remaining candidate fields: Notice Period, DOB, Gender, Department, Industry
        notice_raw = excel_data.get('notice_period')
        if notice_raw is not None and str(notice_raw).strip() != '':
            np_val = cls._parse_notice_period(notice_raw)
            if np_val is not None:
                profile.notice_period = np_val
                dirty_profile = True

        gender_raw = (excel_data.get('gender') or '').strip().upper()
        if gender_raw in dict(CandidateProfile._meta.get_field('gender').choices):
            profile.gender = gender_raw
            dirty_profile = True

        dept_raw = (excel_data.get('department') or '').strip()
        if dept_raw:
            profile.department = dept_raw[:150]
            dirty_profile = True

        industry_raw = (excel_data.get('industry') or '').strip()
        if industry_raw:
            profile.industry = industry_raw[:150]
            dirty_profile = True

        # 12. Preserve full Excel data in parsed_json and resume versions
        raw_map = excel_data.get('_raw') or {k: str(v) for k, v in excel_data.items() if not k.startswith('_')}
        if not isinstance(profile.parsed_json, dict):
            profile.parsed_json = {}
        profile.parsed_json['raw_excel_data'] = raw_map

        # Sync parsed_json['personal_info']
        pi = profile.parsed_json.setdefault('personal_info', {})
        if profile.full_name:
            pi['name'] = profile.full_name
        if profile.current_company:
            pi['current_company'] = profile.current_company
        if profile.current_designation:
            pi['current_designation'] = profile.current_designation
        if profile.location:
            pi['location'] = profile.location
        if profile.summary:
            profile.parsed_json['summary'] = profile.summary
        if profile.current_salary is not None:
            pi['current_salary'] = float(profile.current_salary) / 100000.0
        if profile.total_experience is not None:
            pi['total_experience'] = float(profile.total_experience)

        # Also preserve in resume_versions if active
        ver_str = str(profile.current_version)
        if profile.resume_versions and ver_str in profile.resume_versions:
            v_data = profile.resume_versions[ver_str].setdefault('data', {})
            v_data['raw_excel_data'] = raw_map
            v_data['summary'] = profile.summary

        dirty_profile = True

        # Save user and profile
        if dirty_user and user_obj:
            user_obj.save()
        if dirty_profile:
            profile.save()

        # 13. Populate related Experience records
        if company or designation:
            cls._sync_excel_experience(profile, company, designation, resume_title)

        # 14. Populate related Education records (UG, PG, Post PG)
        cls._sync_excel_education(profile, excel_data)

        # 15. Populate related CandidateSkill records
        cls._sync_excel_skills(profile, excel_data)

    @classmethod
    def _map_error_status(cls, status_code: str) -> str:
        mapping = {
            "INVALID_FORMAT": "Unsupported resume format.",
            "READ_ERROR": "Corrupted file / unable to read file stream.",
            "OCR_FAILED": "Text extraction failed or empty document.",
            "AUTOMATIC_PARSING_FAILED": "Could not extract structured candidate details.",
            "SAVE_FAILED": "Database validation error while saving candidate record.",
            "SECURITY_FAILED": "Failed security scan."
        }
        return mapping.get(status_code, f"Parsing failed ({status_code})")

    # =========================================================================
    # STEP 4: REPORT GENERATION (CSV)
    # =========================================================================
    @classmethod
    def generate_csv_report(cls, job_number_or_id: str) -> str:
        """
        Generates a downloadable CSV processing report for the bulk parsing job.
        Columns: Filename, Status, Candidate Name, Email, Mobile, Action, Reason, Timestamp
        """
        import csv

        job = cls.get_job(job_number_or_id)
        if not job:
            raise ValueError(f"Job {job_number_or_id} not found.")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Filename',
            'Status',
            'Candidate Name',
            'Email',
            'Mobile',
            'Action',
            'Reason',
            'Timestamp'
        ])

        for item in job.items.all().order_by('id'):
            ts = item.processed_at.strftime('%Y-%m-%d %H:%M:%S') if item.processed_at else ''
            writer.writerow([
                item.filename,
                item.status,
                item.candidate_name,
                item.candidate_email,
                item.candidate_phone,
                item.action_taken,
                item.reason,
                ts
            ])

        return output.getvalue()
