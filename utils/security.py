import os
import re
import io
import uuid
import hashlib
import socket
import struct
import logging
import zipfile
import magic
import fitz
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from oletools.olevba import VBA_Parser

logger = logging.getLogger(__name__)

# Resource limits
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ZIP_EXTRACTED_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_FILES_IN_ZIP = 50
MAX_NESTED_ZIP_DEPTH = 2
MAX_FILENAME_LENGTH = 255
EXTRACTION_RATIO_LIMIT = 100.0  # Reject if uncompressed size / compressed size exceeds this

# Supported extensions
SUPPORTED_EXTENSIONS = {'pdf', 'doc', 'docx', 'rtf', 'txt', 'zip'}

# MIME Type mappings
SUPPORTED_MIME_TYPES = {
    'pdf': ['application/pdf'],
    'doc': ['application/msword'],
    'docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
    'rtf': ['application/rtf', 'text/rtf', 'application/x-rtf'],
    'txt': ['text/plain'],
    'zip': ['application/zip', 'application/x-zip-compressed', 'application/x-zip']
}

# Magic numbers
MAGIC_SIGNATURES = {
    'pdf': b'%PDF',
    'zip': b'PK\x03\x04',
    'docx': b'PK\x03\x04',
    'doc': b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1',
    'rtf': b'{\\rtf'
}

class SecurityValidationError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code

def sanitize_filename(filename):
    """
    Sanitize the filename by removing path traversals and keeping safe characters.
    """
    # Remove directory paths
    base_name = os.path.basename(filename)
    # Remove path traversal characters
    base_name = base_name.replace('..', '').replace('/', '').replace('\\', '')
    # Strip leading/trailing dots/spaces
    base_name = base_name.strip('. ')
    # Split ext
    name_part, ext_part = os.path.splitext(base_name)
    # Keep only alphanumeric, dashes, underscores
    name_clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name_part)
    ext_clean = re.sub(r'[^a-zA-Z0-9]', '', ext_part)
    
    final_name = f"{name_clean}.{ext_clean}" if ext_clean else name_clean
    if len(final_name) > MAX_FILENAME_LENGTH:
        final_name = final_name[-MAX_FILENAME_LENGTH:]
    return final_name

def generate_secure_filename(filename):
    """
    Generate a secure, random filename to store on disk to prevent path injection or exposing server paths.
    """
    ext = os.path.splitext(filename)[1].lower()
    return f"{uuid.uuid4().hex}{ext}"

def get_file_sha256(file_bytes):
    return hashlib.sha256(file_bytes).hexdigest()

def scan_bytes_with_clamd(file_bytes, host=None, port=None):
    """
    Scan file bytes using ClamAV clamd network socket.
    """
    if host is None:
        host = getattr(settings, 'CLAMAV_HOST', '127.0.0.1')
    if port is None:
        port = getattr(settings, 'CLAMAV_PORT', 3310)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10.0)
        s.connect((host, port))
    except Exception as e:
        logger.warning(f"ClamAV clamd is not running or unreachable at {host}:{port}: {e}")
        # In strict mode, we should reject. If strict mode is False (local dev fallback), allow.
        if getattr(settings, 'CLAMAV_STRICT', False):
            raise SecurityValidationError("Malicious file detected.\nUpload blocked.", code="CLAMAV_ERROR")
        return "CLEAN", None

    try:
        # Send zINSTREAM command (modern instream command with zero-terminated chunk structure)
        s.sendall(b"zINSTREAM\0")
        offset = 0
        while offset < len(file_bytes):
            chunk = file_bytes[offset:offset+4096]
            s.sendall(struct.pack("!I", len(chunk)) + chunk)
            offset += len(chunk)
        # Send zero-length chunk to terminate
        s.sendall(struct.pack("!I", 0))
        
        response = s.recv(1024).decode('utf-8', errors='ignore').strip()
        s.close()
        
        if "FOUND" in response:
            virus_name = response.split("FOUND")[0].replace("stream:", "").strip()
            return "INFECTED", virus_name
        return "CLEAN", None
    except Exception as e:
        logger.error(f"Error during clamd scan: {e}")
        if getattr(settings, 'CLAMAV_STRICT', False):
            raise SecurityValidationError("Malicious file detected.\nUpload blocked.", code="CLAMAV_ERROR")
        return "ERROR", str(e)

def detect_password_protection(file_bytes, ext):
    """
    Check if the document or archive is password protected.
    """
    if ext == 'pdf':
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            return bool(doc.is_encrypted)
        except Exception:
            return False
    elif ext in ['docx', 'zip']:
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:
                        return True
        except Exception:
            return False
    elif ext == 'doc':
        try:
            import olefile
            if olefile.isOleFile(io.BytesIO(file_bytes)):
                ole = olefile.OleFileIO(io.BytesIO(file_bytes))
                # Standard OLE encryption headers
                if ole.exists('EncryptionInfo') or ole.exists('encryptioninfo') or ole.exists('EncryptedPackage'):
                    return True
        except Exception:
            return False
    return False

def scan_office_security(file_bytes, filename, ext):
    """
    Check DOC/DOCX for VBA macros, embedded scripts, OLE objects, external links, active content, and DDE.
    """
    if ext not in ['doc', 'docx']:
        return True
    
    # 1. VBA Macro Check using oletools.olevba
    try:
        parser = VBA_Parser(filename=filename, data=file_bytes)
        if parser.detect_vba_macros():
            raise SecurityValidationError("Office macro detected.", code="MACRO_DETECTED")
    except SecurityValidationError:
        raise
    except Exception:
        # If not an OLE/OpenXML file, it doesn't have macros
        pass

    # 2. Check for Embedded Objects and External Relationships in DOCX (OpenXML)
    if ext == 'docx':
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                for name in zf.namelist():
                    # Embedded objects/active content
                    if 'word/embeddings/' in name or 'embeddings/' in name:
                        raise SecurityValidationError("Office macro detected.", code="OLE_EMBEDDING")
                    # Check relationships for external templates / active scripting / DDE
                    if name.endswith('.rels'):
                        content = zf.read(name).decode('utf-8', errors='ignore')
                        # External templates or suspicious targets
                        if 'TargetMode="External"' in content:
                            if any(x in content.lower() for x in ['.dotm', '.exe', '.vbs', '.vbe', '.bat', '.cmd', '.js', '.ps1', 'http://', 'https://']):
                                raise SecurityValidationError("Office macro detected.", code="EXTERNAL_RELATIONSHIP")
        except SecurityValidationError:
            raise
        except Exception:
            pass

    return True

def scan_pdf_security(file_bytes):
    """
    Reject PDFs containing JavaScript, embedded executables, launch actions, suspicious annotations, or embedded files.
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        # Embedded files check
        if doc.embfile_count() > 0:
            raise SecurityValidationError("Suspicious PDF content detected.", code="PDF_EMBEDDED_FILES")
            
        # Catalog check
        catalog = doc.pdf_catalog()
        catalog_obj = doc.xref_object(catalog)
        if any(x in catalog_obj for x in ['/Names', '/JavaScript', '/OpenAction']):
            raise SecurityValidationError("Suspicious PDF content detected.", code="PDF_CATALOG_JS")

        # Scan objects for suspicious actions
        for xref in range(1, doc.xref_length()):
            obj_defn = doc.xref_object(xref)
            if not obj_defn:
                continue
            # Search for JS, JavaScript, Launch, AA (Additional Actions), EmbeddedFiles, FS
            if any(p in obj_defn for p in ['/JS', '/JavaScript', '/Launch', '/AA', '/EmbeddedFiles', '/FS']):
                raise SecurityValidationError("Suspicious PDF content detected.", code="PDF_SUSPICIOUS_OBJ")

        # Scan annotations for active content
        for page in doc:
            annot = page.first_annot
            while annot:
                annot_defn = doc.xref_object(annot.xref)
                if any(p in annot_defn for p in ['/JS', '/JavaScript', '/Launch', '/AA', '/FS']):
                    raise SecurityValidationError("Suspicious PDF content detected.", code="PDF_SUSPICIOUS_ANNOT")
                annot = annot.next
                
    except SecurityValidationError:
        raise
    except Exception as e:
        raise SecurityValidationError(f"Suspicious PDF content detected.", code="PDF_SCAN_ERROR")

    return True

def validate_single_file_content(file_bytes, filename, ext):
    """
    Validate a single file (not a zip) for type, signature, size, password protection, virus, and active content.
    """
    # 1. Check Magic number / signature
    if ext in MAGIC_SIGNATURES:
        sig = MAGIC_SIGNATURES[ext]
        if not file_bytes.startswith(sig):
            raise SecurityValidationError("Unsupported file format.", code="MAGIC_MISMATCH")
            
    # 2. MIME type check
    mime = magic.from_buffer(file_bytes, mime=True)
    allowed_mimes = SUPPORTED_MIME_TYPES.get(ext, [])
    if mime not in allowed_mimes:
        # Special check: sometimes RTF or TXT can have text/plain or application/rtf variations
        if ext == 'rtf' and mime in ['application/rtf', 'text/rtf', 'application/x-rtf']:
            pass
        elif ext == 'txt' and mime.startswith('text/'):
            pass
        else:
            raise SecurityValidationError("Unsupported file format.", code="MIME_MISMATCH")

    # 3. Password protection check
    if detect_password_protection(file_bytes, ext):
        raise SecurityValidationError("Password protected document.", code="PASSWORD_PROTECTED")

    # 4. Malware / Virus Scan
    status, virus_info = scan_bytes_with_clamd(file_bytes)
    if status == "INFECTED":
        raise SecurityValidationError("Virus detected.", code="VIRUS_DETECTED")

    # 5. Office security scan (macros, active content, etc.)
    if ext in ['doc', 'docx']:
        scan_office_security(file_bytes, filename, ext)

    # 6. PDF security scan
    if ext == 'pdf':
        scan_pdf_security(file_bytes)

    # 7. Plain text check for TXT
    if ext == 'txt':
        # Ensure it doesn't contain null bytes (often binary files)
        if b'\x00' in file_bytes:
            raise SecurityValidationError("Unsupported file format.", code="BINARY_TXT")

    return True

def validate_zip_archive(zip_bytes, current_depth=1):
    """
    Recursively validates a ZIP archive (up to depth 2) and checks zip bomb properties.
    """
    if current_depth > MAX_NESTED_ZIP_DEPTH:
        raise SecurityValidationError("ZIP Bomb detected.", code="NESTED_ZIP_DEPTH")

    try:
        zip_io = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(zip_io) as zf:
            infolist = zf.infolist()
            
            # File count limit
            if len(infolist) > MAX_FILES_IN_ZIP:
                raise SecurityValidationError("ZIP Bomb detected.", code="MAX_FILES")

            total_uncompressed_size = 0
            
            for info in infolist:
                # Path traversal check
                if '..' in info.filename or info.filename.startswith('/') or info.filename.startswith('\\'):
                    raise SecurityValidationError("ZIP Bomb detected.", code="PATH_TRAVERSAL")
                
                # Check for symbolic links
                # (external_attr >> 16) & 0o170000 == 0o120000 checks for symlink flag
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise SecurityValidationError("ZIP Bomb detected.", code="SYMBOLIC_LINK")

                # Size accumulator
                total_uncompressed_size += info.file_size
                if total_uncompressed_size > MAX_ZIP_EXTRACTED_SIZE:
                    raise SecurityValidationError("ZIP Bomb detected.", code="ZIP_EXTRACTED_LIMIT")

                # Extraction ratio check
                if info.compress_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > EXTRACTION_RATIO_LIMIT:
                        raise SecurityValidationError("ZIP Bomb detected.", code="EXTRACTION_RATIO")

                # Reject ZIP if it contains password protection
                if info.flag_bits & 0x1:
                    raise SecurityValidationError("Encrypted archive not allowed.", code="ENCRYPTED_ZIP")

                filename_lower = info.filename.lower()
                
                # Danger extension check
                dangerous_exts = {
                    '.exe', '.dll', '.bat', '.ps1', '.sh', '.msi', '.apk', '.js', '.vbs', '.cmd', '.scr', '.pif'
                }
                for dext in dangerous_exts:
                    if filename_lower.endswith(dext) or f"{dext}." in filename_lower:
                        raise SecurityValidationError("Executable found inside ZIP.", code="DANGEROUS_FILE_ZIP")

                # Double extension or hidden executable check (e.g. "resume.pdf .exe" or ".exe")
                # Filename starting with . and having a dangerous extension or containing space-padded extensions
                if re.search(r'\.[a-zA-Z0-9]+\s+\.[a-zA-Z0-9]+', filename_lower):
                    raise SecurityValidationError("Executable found inside ZIP.", code="DOUBLE_EXTENSION_ZIP")

                # Extract and recursively validate nested ZIP archives
                if filename_lower.endswith('.zip'):
                    nested_bytes = zf.read(info.filename)
                    validate_zip_archive(nested_bytes, current_depth + 1)

    except SecurityValidationError:
        raise
    except Exception as e:
        raise SecurityValidationError(f"Unsupported file format.", code="ZIP_READ_ERROR")

    return True

def perform_all_security_validations(file_bytes, original_filename):
    """
    Runs ALL security validations on the uploaded document or ZIP.
    If ANY validation fails, raises SecurityValidationError.
    """
    # 1. Size Validation (Check before anything else)
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise SecurityValidationError("File too large.", code="FILE_TOO_LARGE")

    # 2. Extension validation
    ext = original_filename.split('.')[-1].lower() if '.' in original_filename else ''
    if ext not in SUPPORTED_EXTENSIONS:
        raise SecurityValidationError("Unsupported file format.", code="UNSUPPORTED_EXTENSION")

    # 3. Secure filename generation & original sanitization
    sanitized_orig = sanitize_filename(original_filename)
    secure_name = generate_secure_filename(original_filename)
    sha256_hash = get_file_sha256(file_bytes)

    # 4. ZIP specific validation
    if ext == 'zip':
        # Scan ZIP archive for malware
        status, virus_info = scan_bytes_with_clamd(file_bytes)
        if status == "INFECTED":
            raise SecurityValidationError("Virus detected.", code="VIRUS_DETECTED")
            
        # Validate ZIP structure and nested zips
        validate_zip_archive(file_bytes)
        
        # Scan extracted files inside ZIP
        # Extract files inside ZIP and scan them
        try:
            zip_io = io.BytesIO(file_bytes)
            with zipfile.ZipFile(zip_io) as zf:
                for info in zf.infolist():
                    if info.is_dir() or info.filename.endswith('.zip'):
                        continue
                    
                    sub_ext = info.filename.split('.')[-1].lower() if '.' in info.filename else ''
                    if sub_ext not in (SUPPORTED_EXTENSIONS - {'zip'}):
                        # ZIP contains files with unsupported formats
                        continue # We skip non-resume formats, but wait:
                        # Requirements say "Only resume files continue", which means we skip unsupported files inside ZIP.
                        # However, if there are executable files or other dangerous objects inside, we would have already caught them in dangerous_exts check.
                    
                    sub_bytes = zf.read(info.filename)
                    # Virus scan each extracted file
                    sub_status, sub_virus = scan_bytes_with_clamd(sub_bytes)
                    if sub_status == "INFECTED":
                        raise SecurityValidationError("Virus detected.", code="VIRUS_DETECTED_INSIDE_ZIP")
                        
                    # Security validate each extracted file
                    validate_single_file_content(sub_bytes, info.filename, sub_ext)
        except SecurityValidationError:
            raise
        except Exception as e:
            raise SecurityValidationError("Unsupported file format.", code="ZIP_PROCESS_ERROR")
    else:
        # 5. Non-ZIP single file validations
        validate_single_file_content(file_bytes, sanitized_orig, ext)

    return {
        "sanitized_filename": sanitized_orig,
        "secure_filename": secure_name,
        "sha256": sha256_hash,
        "mime_type": magic.from_buffer(file_bytes, mime=True),
        "scan_status": "PASSED",
        "scan_timestamp": timezone.now()
    }

def log_upload_attempt(filename, sha256, user, virus_result, malware_result, reason_for_rejection=None):
    """
    Log file upload details for audit purposes, ensuring no internal server paths are exposed.
    """
    user_str = user.email if (user and hasattr(user, 'email')) else str(user)
    log_msg = (
        f"[UPLOAD AUDIT] Filename: {filename} | "
        f"Hash: {sha256 or 'N/A'} | "
        f"Time: {timezone.now().isoformat()} | "
        f"User: {user_str} | "
        f"Virus Result: {virus_result} | "
        f"Malware Result: {malware_result} | "
        f"Status: {'REJECTED' if reason_for_rejection else 'PASSED'}"
    )
    if reason_for_rejection:
        log_msg += f" | Reason: {reason_for_rejection}"
    logger.info(log_msg)
    print(log_msg)
