import os
import uuid
import logging
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.rtf', '.txt', '.png', '.jpg', '.jpeg', '.webp'}

class ResumeUploadError(Exception):
    """Raised when resume upload to storage fails or verification fails."""
    pass

def get_active_resume_storage():
    """
    Returns the active resume storage backend.
    """
    return default_storage

def generate_unique_resume_key(original_filename: str) -> str:
    """
    Generates a deterministic, unique S3 object key for a candidate resume.
    Example: resumes/a1b2c3d4e5f67890.pdf
    """
    ext = os.path.splitext(original_filename or '')[1].lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        ext = '.pdf'
    unique_id = uuid.uuid4().hex
    return f"resumes/{unique_id}{ext}"

def verify_s3_object_exists(key: str, storage=None) -> bool:
    """
    Verifies that the object with the given key exists in the configured storage.
    """
    if not key:
        return False
    target_storage = storage or get_active_resume_storage()
    try:
        exists = bool(target_storage.exists(key))
        if exists:
            logger.info(f"[RESUME_S3_VERIFY_SUCCESS] Object '{key}' verified in storage.")
        else:
            logger.warning(f"[RESUME_S3_MISSING] Object '{key}' does not exist in storage.")
        return exists
    except Exception as e:
        logger.error(f"[RESUME_S3_VERIFY_ERROR] Error checking existence of '{key}': {e}")
        return False

def upload_and_verify_resume(file_input, original_filename: str, storage=None) -> tuple[str, bytes]:
    """
    Uploads a resume file to S3 and verifies that it exists before returning.
    
    Returns:
        (saved_key, file_bytes)
        
    Raises:
        ResumeUploadError: If file is empty, upload fails, or S3 verification fails.
    """
    target_storage = storage or get_active_resume_storage()
    logger.info(f"[RESUME_UPLOAD_START] Uploading resume '{original_filename}'...")
    
    # Read file bytes
    try:
        if isinstance(file_input, bytes):
            file_bytes = file_input
        elif hasattr(file_input, 'read'):
            if hasattr(file_input, 'seek'):
                file_input.seek(0)
            file_bytes = file_input.read()
            if hasattr(file_input, 'seek'):
                file_input.seek(0)
        else:
            raise ResumeUploadError("Invalid file input type provided.")
    except Exception as e:
        logger.error(f"[RESUME_UPLOAD_FAILED] Failed to read file bytes: {e}")
        raise ResumeUploadError(f"Failed to read upload file data: {e}") from e

    if not file_bytes:
        logger.error("[RESUME_UPLOAD_FAILED] File content is empty.")
        raise ResumeUploadError("Uploaded resume file is empty.")

    # Generate unique key
    target_key = generate_unique_resume_key(original_filename)

    # Upload to storage
    try:
        saved_key = target_storage.save(target_key, ContentFile(file_bytes))
    except Exception as e:
        logger.error(f"[RESUME_UPLOAD_FAILED] Storage save failed for '{target_key}': {e}", exc_info=True)
        raise ResumeUploadError(f"Resume upload failed. Candidate data was not changed: {e}") from e

    logger.info(f"[RESUME_S3_UPLOAD_SUCCESS] File saved as '{saved_key}'. Verifying object in S3...")

    # Verify object exists in storage
    if not verify_s3_object_exists(saved_key, storage=target_storage):
        logger.error(f"[RESUME_UPLOAD_FAILED] S3 object verification failed for '{saved_key}'.")
        # Attempt cleanup if partially created
        try:
            target_storage.delete(saved_key)
        except Exception:
            pass
        raise ResumeUploadError("Resume upload failed. The file could not be verified in AWS S3 storage. Candidate record was not changed.")

    logger.info(f"[RESUME_S3_VERIFY_SUCCESS] Resume successfully stored and verified at '{saved_key}'.")
    return saved_key, file_bytes

def save_candidate_resume_atomic(candidate_profile, file_input, original_filename: str, is_replacement: bool = True, user=None) -> str:
    """
    Safely uploads resume to S3, verifies S3 object, and ONLY THEN updates CandidateProfile.resume inside a DB transaction.
    
    If upload/verification fails:
    - Does NOT save a broken reference in DB
    - Preserves candidate profile and existing resume intact
    - Returns clear error
    """
    target_storage = get_active_resume_storage()
    old_resume_key = candidate_profile.resume.name if (candidate_profile.resume and candidate_profile.resume.name) else None
    
    # Upload and verify S3 object FIRST before touching DB
    saved_key, file_bytes = upload_and_verify_resume(file_input, original_filename, storage=target_storage)
    
    try:
        with transaction.atomic():
            candidate_profile.resume.name = saved_key
            candidate_profile.original_filename = original_filename
            update_fields = ['resume', 'original_filename']
            if user and getattr(user, 'role', '') != 'CANDIDATE':
                candidate_profile.uploaded_by = user
                update_fields.append('uploaded_by')
                if not candidate_profile.created_by:
                    candidate_profile.created_by = user
                    update_fields.append('created_by')
            candidate_profile.save(update_fields=update_fields)
            logger.info(f"[RESUME_DB_SAVE_SUCCESS] Candidate ID {candidate_profile.id} updated with resume key '{saved_key}'.")
            
            # Defer old resume cleanup until AFTER transaction commits
            if is_replacement and old_resume_key and old_resume_key != saved_key:
                def cleanup_old_resume():
                    try:
                        if target_storage.exists(old_resume_key):
                            target_storage.delete(old_resume_key)
                            logger.info(f"[RESUME_CLEANUP_SUCCESS] Deleted old resume '{old_resume_key}' after successful replacement.")
                    except Exception as e_clean:
                        logger.warning(f"[RESUME_CLEANUP_WARN] Failed to delete old resume '{old_resume_key}': {e_clean}")
                        
                transaction.on_commit(cleanup_old_resume)
                
        return saved_key
    except Exception as e:
        logger.error(f"[RESUME_DB_SAVE_FAILED] Failed to update candidate profile DB record: {e}", exc_info=True)
        # Attempt to delete newly uploaded object since DB save failed
        try:
            target_storage.delete(saved_key)
        except Exception:
            pass
        raise ResumeUploadError(f"Database save failed after S3 upload: {e}") from e

def copy_and_verify_original_resume(source_key: str, original_filename: str = None, storage=None) -> str:
    """
    Creates a verified copy of a resume (e.g. for original_file).
    """
    target_storage = storage or get_active_resume_storage()
    if not source_key or not target_storage.exists(source_key):
        return None
        
    ext = os.path.splitext(original_filename or source_key)[1].lower() or '.pdf'
    target_key = f"resumes/original/original_{uuid.uuid4().hex}{ext}"
    
    try:
        # Check S3 copy or open/save copy
        f = target_storage.open(source_key, 'rb')
        content = f.read()
        saved_key = target_storage.save(target_key, ContentFile(content))
        if verify_s3_object_exists(saved_key, storage=target_storage):
            return saved_key
    except Exception as e:
        logger.warning(f"[RESUME_ORIGINAL_COPY_WARN] Failed to copy original resume '{source_key}' to '{target_key}': {e}")
        
    return None
