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

from apps.accounts.models import User
from apps.candidates.models import (
    CandidateProfile, DuplicateResumeLog, BulkResumeJob, BulkResumeItem
)
from apps.candidates.utils import process_resume_file
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
        """Extracts pure digits from contact number string/float."""
        if not phone_val:
            return ""
        digits = re.sub(r'[^\d]', '', str(phone_val).split('.')[0])
        # Strip leading country code 91 if 12 digits
        if len(digits) == 12 and digits.startswith('91'):
            digits = digits[2:]
        return digits

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
        if not zip_file:
            raise ValueError("A valid ZIP file containing resumes is required.")

        # Check ZIP size
        if hasattr(zip_file, 'size') and zip_file.size > MAX_ZIP_SIZE_BYTES:
            raise ValueError(f"ZIP file exceeds maximum allowed size of {MAX_ZIP_SIZE_BYTES // (1024*1024)}MB.")

        # Create temporary working directory for this job
        job_number = cls.generate_job_number()
        temp_base = os.path.join(settings.MEDIA_ROOT, 'temp_bulk_jobs', job_number)
        os.makedirs(temp_base, exist_ok=True)

        extracted_files = []
        skipped_files = []
        total_uncompressed_bytes = 0

        # 1. Read & Extract ZIP securely
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

        if not extracted_files and not skipped_files:
            raise ValueError("The uploaded ZIP archive contains no files.")

        # 2. Parse Excel file if provided
        excel_rows = []
        column_mapping = {}
        excel_filename = ""
        
        if excel_file:
            excel_filename = getattr(excel_file, 'name', 'candidates.xlsx')
            excel_rows, column_mapping = cls.parse_candidate_excel(excel_file)

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

        # 4. Create database records in atomic transaction
        with transaction.atomic():
            bulk_job = BulkResumeJob.objects.create(
                job_number=job_number,
                user=user,
                job=job,
                status=BulkResumeJob.Status.PENDING,
                zip_filename=getattr(zip_file, 'name', 'resumes.zip'),
                excel_filename=excel_filename,
                storage_dir=temp_base,
                overwrite=overwrite,
                total_files=len(extracted_files),
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
    @classmethod
    def parse_candidate_excel(cls, excel_file) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Parses an uploaded Excel (.xlsx, .xls) workbook according to the TalentVault
        candidate data structure.
        """
        import openpyxl

        if hasattr(excel_file, 'seek'):
            excel_file.seek(0)
        file_bytes = excel_file.read()

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active

        rows = list(sheet.iter_rows(values_only=True))
        if not rows or len(rows) < 1:
            return [], {}

        raw_headers = [str(h).strip() for h in rows[0] if h is not None]
        header_map = {}
        column_mapping_display = {}

        # Canonical mapping definition
        field_patterns = {
            'company': [r'company\s*name', r'current\s*company', r'company', r'employer', r'organization'],
            'designation': [r'role', r'designation', r'job\s*title', r'current\s*designation', r'current\s*role', r'position'],
            'location': [r'location', r'city', r'current\s*location'],
            'sub_location': [r'sub\s*location', r'area', r'preferred\s*location', r'branch'],
            'name': [r'candidate\s*name', r'full\s*name', r'name'],
            'phone': [r'contact\s*number', r'contact', r'phone', r'mobile', r'mobile\s*number', r'phone\s*number'],
            'resume_filename': [r'resume', r'cv', r'resume\s*file', r'filename', r'file\s*name', r'attachment'],
            'interviewed': [r'interviewed', r'interview\s*status', r'status'],
            'email': [r'email', r'email\s*address', r'email\s*id', r'mail'],
            'experience': [r'experience', r'total\s*experience', r'total\s*exp', r'exp\s*in\s*years', r'yrs\s*exp'],
            'salary': [r'salary', r'current\s*salary', r'ctc', r'current\s*ctc', r'lpa'],
            'expected_salary': [r'expected\s*salary', r'expected\s*ctc', r'ectc'],
            'skills': [r'skills', r'key\s*skills', r'primary\s*skills', r'tech\s*stack'],
            'notice_period': [r'notice\s*period', r'notice', r'np']
        }

        # Detect columns from raw headers
        for col_idx, header_text in enumerate(rows[0]):
            if header_text is None:
                continue
            h_clean = str(header_text).strip()
            h_lower = h_clean.lower()

            matched_field = None
            for field, patterns in field_patterns.items():
                for pat in patterns:
                    if re.search(pat, h_lower):
                        matched_field = field
                        break
                if matched_field:
                    break

            if matched_field:
                header_map[col_idx] = matched_field
                column_mapping_display[h_clean] = matched_field.replace('_', ' ').title()

        # Parse rows
        parsed_candidate_rows = []
        for row_values in rows[1:]:
            # Skip empty rows
            if not any(row_values):
                continue

            row_data = {}
            for col_idx, cell_value in enumerate(row_values):
                field_name = header_map.get(col_idx)
                if field_name and cell_value is not None:
                    row_data[field_name] = str(cell_value).strip()

            # Require at least one identifying property (Name, Phone, Email, or Resume filename)
            if any(row_data.get(k) for k in ['name', 'phone', 'email', 'resume_filename', 'company']):
                parsed_candidate_rows.append(row_data)

        return parsed_candidate_rows, column_mapping_display

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
    def _enrich_profile_from_excel(cls, profile: CandidateProfile, excel_data: Dict[str, Any]):
        """Enriches candidate profile using validated Excel metadata."""
        dirty = False
        if excel_data.get('company') and not profile.current_company:
            profile.current_company = excel_data['company'][:255]
            dirty = True
        if excel_data.get('designation') and not profile.current_designation:
            profile.current_designation = excel_data['designation'][:255]
            dirty = True
        if excel_data.get('location') and (not profile.location or profile.location == 'Unknown'):
            profile.location = excel_data['location'][:100]
            dirty = True
        if excel_data.get('sub_location') and not profile.preferred_location:
            profile.preferred_location = excel_data['sub_location'][:255]
            dirty = True
        if excel_data.get('name') and not profile.full_name:
            profile.full_name = excel_data['name'][:255]
            dirty = True

        if dirty:
            profile.save()

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
