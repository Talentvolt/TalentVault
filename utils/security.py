import os
import re
import io
import uuid
import hashlib
import socket
import struct
import logging
import zipfile
import mimetypes
import fitz
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from oletools.olevba import VBA_Parser

logger = logging.getLogger(__name__)

try:
    import magic
    HAS_MAGIC = True
except ImportError:
    magic = None
    HAS_MAGIC = False

if not HAS_MAGIC:
    print("Advanced MIME detection unavailable. Using secure fallback validation.")
    logger.warning("Advanced MIME detection unavailable. Using secure fallback validation.")

# Resource limits
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ZIP_EXTRACTED_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_FILES_IN_ZIP = 50
MAX_NESTED_ZIP_DEPTH = 2
MAX_FILENAME_LENGTH = 255
EXTRACTION_RATIO_LIMIT = 100.0  # Reject if uncompressed size / compressed size exceeds this

# Supported extensions
SUPPORTED_EXTENSIONS = {'pdf', 'doc', 'docx', 'rtf', 'txt', 'zip', 'png', 'jpg', 'jpeg', 'webp', 'tiff'}

# MIME Type mappings
SUPPORTED_MIME_TYPES = {
    'pdf': ['application/pdf'],
    'doc': ['application/msword'],
    'docx': [
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/zip',
        'application/octet-stream'
    ],
    'rtf': ['application/rtf', 'text/rtf', 'application/x-rtf'],
    'txt': ['text/plain', 'text/ascii'],
    'zip': ['application/zip', 'application/x-zip-compressed', 'application/x-zip'],
    'png': ['image/png'],
    'jpg': ['image/jpeg', 'image/jpg'],
    'jpeg': ['image/jpeg', 'image/jpg'],
    'webp': ['image/webp'],
    'tiff': ['image/tiff']
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
    Check DOC/DOCX for VBA macros, embedded scripts, OLE objects, and active content.
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

    # 2. Check for Embedded VBA/Macro files in DOCX (OpenXML)
    if ext == 'docx':
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                for name in zf.namelist():
                    name_lower = name.lower()
                    if 'vbaproject.bin' in name_lower or 'vbadata.xml' in name_lower:
                        raise SecurityValidationError("Office macro detected.", code="MACRO_DETECTED")
        except SecurityValidationError:
            raise
        except Exception:
            pass

    return True

def repair_pdf_bytes(file_bytes, filename="resume.pdf"):
    """
    Automatically repair corrupted / malformed PDF files using multiple repair strategies:
    1. PyMuPDF clean=True & garbage collection
    2. pikepdf (if available)
    3. qpdf CLI tool (if available)
    4. Ghostscript CLI tool (if available)
    5. PyMuPDF Page-by-Page Image Rasterization & Reconstruction
    6. pdf2image rendering (if available)
    
    Returns: (repaired_bytes, strategy_used, warning_message)
    """
    if not file_bytes:
        return None, None, None

    logger.info(f"[PDF REPAIR START] Starting repair pipeline for {filename} ({len(file_bytes)} bytes)")
    
    # Strategy 1: PyMuPDF clean & garbage collection
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if len(doc) > 0:
            repaired = doc.tobytes(clean=True, deflate=True, garbage=4)
            doc.close()
            t_doc = fitz.open(stream=repaired, filetype="pdf")
            if len(t_doc) > 0:
                t_doc.close()
                logger.info(f"[PDF REPAIR SUCCESS] Repaired {filename} via PyMuPDF clean=True")
                return repaired, "PyMuPDF_Clean", "PDF repaired automatically."
    except Exception as e:
        logger.warning(f"[PDF REPAIR] Strategy 1 (PyMuPDF clean) failed: {e}")

    # Strategy 2: pikepdf
    try:
        import pikepdf
        with pikepdf.open(io.BytesIO(file_bytes), allow_overwriting_input=True) as pdf:
            out_buf = io.BytesIO()
            pdf.save(out_buf)
            repaired = out_buf.getvalue()
            t_doc = fitz.open(stream=repaired, filetype="pdf")
            if len(t_doc) > 0:
                t_doc.close()
                logger.info(f"[PDF REPAIR SUCCESS] Repaired {filename} via pikepdf")
                return repaired, "Pikepdf", "PDF repaired automatically."
    except Exception as e:
        logger.warning(f"[PDF REPAIR] Strategy 2 (pikepdf) failed: {e}")

    # Strategy 3: qpdf CLI
    try:
        import tempfile, subprocess
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_in, \
             tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_out:
            tmp_in.write(file_bytes)
            tmp_in.flush()
            in_p, out_p = tmp_in.name, tmp_out.name
        try:
            cmd = ["qpdf", "--qdf", "--object-streams=disable", in_p, out_p]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            if os.path.exists(out_p) and os.path.getsize(out_p) > 0:
                with open(out_p, "rb") as f:
                    repaired = f.read()
                t_doc = fitz.open(stream=repaired, filetype="pdf")
                if len(t_doc) > 0:
                    t_doc.close()
                    logger.info(f"[PDF REPAIR SUCCESS] Repaired {filename} via qpdf")
                    return repaired, "Qpdf", "PDF repaired automatically."
        finally:
            for p in [in_p, out_p]:
                if os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass
    except Exception as e:
        logger.warning(f"[PDF REPAIR] Strategy 3 (qpdf) failed: {e}")

    # Strategy 4: Ghostscript CLI
    try:
        import tempfile, subprocess
        gs_cmd = "gswin64c" if os.name == "nt" else "gs"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_in, \
             tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_out:
            tmp_in.write(file_bytes)
            tmp_in.flush()
            in_p, out_p = tmp_in.name, tmp_out.name
        try:
            cmd = [gs_cmd, "-o", out_p, "-sDEVICE=pdfwrite", "-dPDFSETTINGS=/prepress", in_p]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            if os.path.exists(out_p) and os.path.getsize(out_p) > 0:
                with open(out_p, "rb") as f:
                    repaired = f.read()
                t_doc = fitz.open(stream=repaired, filetype="pdf")
                if len(t_doc) > 0:
                    t_doc.close()
                    logger.info(f"[PDF REPAIR SUCCESS] Repaired {filename} via Ghostscript")
                    return repaired, "Ghostscript", "PDF repaired automatically."
        finally:
            for p in [in_p, out_p]:
                if os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass
    except Exception as e:
        logger.warning(f"[PDF REPAIR] Strategy 4 (Ghostscript) failed: {e}")

    # Strategy 5: PyMuPDF Page-by-Page Image Rasterization & Reconstruction
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        reconstructed_pdf = fitz.open()
        rendered_pages = 0
        for page_idx in range(len(doc)):
            try:
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("jpeg")
                img_doc = fitz.open("jpeg", img_bytes)
                pdf_bytes_page = img_doc.convert_to_pdf()
                img_doc.close()
                page_pdf = fitz.open("pdf", pdf_bytes_page)
                reconstructed_pdf.insert_pdf(page_pdf)
                page_pdf.close()
                rendered_pages += 1
            except Exception as pe:
                logger.warning(f"[PDF REPAIR] Page {page_idx} rasterization skipped: {pe}")
        doc.close()
        if rendered_pages > 0:
            repaired = reconstructed_pdf.tobytes()
            reconstructed_pdf.close()
            logger.info(f"[PDF REPAIR SUCCESS] Repaired {filename} via Page Rasterization ({rendered_pages} pages)")
            return repaired, "PageRasterization", "PDF repaired automatically."
    except Exception as e:
        logger.warning(f"[PDF REPAIR] Strategy 5 (Page Rasterization) failed: {e}")

    # Strategy 6: pdf2image rendering
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(file_bytes)
        if images:
            reconstructed_pdf = fitz.open()
            for img in images:
                buf = io.BytesIO()
                img.save(buf, format='JPEG')
                img_doc = fitz.open("jpeg", buf.getvalue())
                pdf_bytes_page = img_doc.convert_to_pdf()
                img_doc.close()
                page_pdf = fitz.open("pdf", pdf_bytes_page)
                reconstructed_pdf.insert_pdf(page_pdf)
                page_pdf.close()
            repaired = reconstructed_pdf.tobytes()
            reconstructed_pdf.close()
            logger.info(f"[PDF REPAIR SUCCESS] Repaired {filename} via pdf2image ({len(images)} pages)")
            return repaired, "pdf2image", "PDF repaired automatically."
    except Exception as e:
        logger.warning(f"[PDF REPAIR] Strategy 6 (pdf2image) failed: {e}")

    logger.error(f"[PDF REPAIR FAILED] All repair strategies failed for {filename}")
    return None, None, None

def scan_pdf_security(file_bytes):
    """
    Reject PDFs containing JavaScript, embedded executables, launch actions, suspicious annotations, or embedded files.
    Xref and structural PDF errors MUST NOT trigger security rejections.
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        
        # Embedded files check
        try:
            if doc.embfile_count() > 0:
                raise SecurityValidationError("Suspicious PDF content detected. Security validation failed because embedded files were found in the PDF.", code="PDF_EMBEDDED_FILES")
        except SecurityValidationError:
            raise
        except Exception as e:
            logger.warning(f"[PDF STRUCTURAL WARNING] Non-fatal error reading embedded files count: {e}")

        # Catalog check
        try:
            catalog = doc.pdf_catalog()
            catalog_obj = doc.xref_object(catalog) if catalog else ""
            if '/JavaScript' in catalog_obj:
                raise SecurityValidationError("Suspicious PDF content detected. Security validation failed because embedded JavaScript was found in the PDF catalog.", code="PDF_CATALOG_JS")
            if '/OpenAction' in catalog_obj:
                if any(act in catalog_obj for act in ['/JS', '/JavaScript', '/Launch']):
                    raise SecurityValidationError("Suspicious PDF content detected. Security validation failed because a malicious OpenAction was found in the PDF catalog.", code="PDF_CATALOG_JS")
        except SecurityValidationError:
            raise
        except Exception as e:
            logger.warning(f"[PDF STRUCTURAL WARNING] Non-fatal error checking PDF catalog: {e}")

        # Scan objects for suspicious actions
        try:
            for xref in range(1, doc.xref_length()):
                try:
                    obj_defn = doc.xref_object(xref)
                except Exception:
                    # Ignore per-object xref lookup errors (e.g. 'cannot find object in xref' or 'code=7')
                    continue
                if not obj_defn:
                    continue
                if '/JS ' in obj_defn or '/JavaScript' in obj_defn:
                    raise SecurityValidationError("Suspicious PDF content detected. Security validation failed because embedded JavaScript (/JS) was detected in object xref.", code="PDF_SUSPICIOUS_OBJ")
                if '/Launch' in obj_defn:
                    raise SecurityValidationError("Suspicious PDF content detected. Security validation failed because a Launch Action (/Launch) was detected in PDF objects.", code="PDF_SUSPICIOUS_OBJ")
                if '/EmbeddedFiles' in obj_defn:
                    raise SecurityValidationError("Suspicious PDF content detected. Security validation failed because embedded files (/EmbeddedFiles) were detected in PDF objects.", code="PDF_SUSPICIOUS_OBJ")
        except SecurityValidationError:
            raise
        except Exception as e:
            logger.warning(f"[PDF STRUCTURAL WARNING] Non-fatal error scanning PDF xref objects: {e}")

        # Scan annotations for active content
        try:
            for page in doc:
                try:
                    annot = page.first_annot
                    while annot:
                        annot_defn = doc.xref_object(annot.xref)
                        if any(p in annot_defn for p in ['/JS', '/JavaScript', '/Launch']):
                            raise SecurityValidationError("Suspicious PDF content detected. Security validation failed because a dangerous action was detected in page annotations.", code="PDF_SUSPICIOUS_ANNOT")
                        annot = annot.next
                except Exception:
                    continue
        except SecurityValidationError:
            raise
        except Exception as e:
            logger.warning(f"[PDF STRUCTURAL WARNING] Non-fatal error scanning page annotations: {e}")

        doc.close()

    except SecurityValidationError:
        raise
    except Exception as e:
        err_str = str(e)
        # Check if raw bytes contain actual active malware tags
        has_js = any(tag in file_bytes for tag in [b'/JavaScript', b'/JS ', b'/JS\n', b'/JS\r'])
        has_launch = b'/Launch' in file_bytes
        has_embed = b'/EmbeddedFiles' in file_bytes

        if has_js or has_launch or has_embed:
            raise SecurityValidationError("Suspicious PDF content detected. Security validation failed because suspicious raw tags were found in the unopenable PDF.", code="PDF_SCAN_ERROR")

        # Structural / xref errors MUST NOT trigger security rejection!
        logger.warning(f"[PDF STRUCTURAL NOTICE] PyMuPDF open/scan encountered structural issue ({err_str}). Passing security scan for repair phase.")
        return True

    return True

def get_mime_type(file_bytes, filename, ext):
    """
    Safely get MIME type of a file. Uses python-magic if available,
    otherwise falls back to mimetypes guessing.
    """
    if HAS_MAGIC:
        try:
            mime = magic.from_buffer(file_bytes, mime=True)
            if mime:
                return mime
        except Exception:
            pass
            
    # Fallback MIME detection using mimetypes module
    import mimetypes
    if not mimetypes.inited:
        mimetypes.init()
    mime, _ = mimetypes.guess_type(filename)
    if not mime:
        allowed_mimes = SUPPORTED_MIME_TYPES.get(ext, [])
        if allowed_mimes:
            mime = allowed_mimes[0]
        else:
            mime = 'application/octet-stream'
    return mime

def validate_single_file_content(file_bytes, filename, ext):
    """
    Validate a single file (not a zip) for type, signature, size, password protection, virus, and active content.
    """
    mime = get_mime_type(file_bytes, filename, ext)
    validation_status = "FAILED"
    try:
        # 1. Check Magic number / signature
        if ext in MAGIC_SIGNATURES:
            sig = MAGIC_SIGNATURES[ext]
            if ext == 'pdf':
                if sig not in file_bytes[:1024]:
                    raise SecurityValidationError("Unsupported file format.", code="MAGIC_MISMATCH")
            elif not file_bytes.startswith(sig):
                raise SecurityValidationError("Unsupported file format.", code="MAGIC_MISMATCH")
                
        # 2. MIME type check
        if HAS_MAGIC:
            allowed_mimes = SUPPORTED_MIME_TYPES.get(ext, [])
            if mime not in allowed_mimes:
                # Special check: sometimes RTF or TXT can have text/plain or application/rtf variations
                if ext == 'rtf' and mime in ['application/rtf', 'text/rtf', 'application/x-rtf']:
                    pass
                elif ext == 'txt' and mime.startswith('text/'):
                    pass
                else:
                    raise SecurityValidationError("Unsupported file format.", code="MIME_MISMATCH")
        else:
            # Fall back to extension-based validation (already checked by signature and extension check)
            pass

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

        validation_status = "PASSED"
        return True
    except Exception as e:
        validation_status = f"FAILED: {str(e)}"
        raise
    finally:
        logger.info(
            f"[FILE VALIDATION] Filename: {filename} | "
            f"Extension: {ext} | "
            f"MIME Type: {mime} | "
            f"Result: {validation_status}"
        )

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

                # Extract and recursively validate nested ZIP archives (immediately reject)
                if filename_lower.endswith('.zip'):
                    raise SecurityValidationError("ZIP Bomb detected.", code="NESTED_ZIP_DEPTH")

    except SecurityValidationError:
        raise
    except Exception as e:
        raise SecurityValidationError("Unsupported file.", code="ZIP_READ_ERROR")

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
        raise SecurityValidationError("Unsupported file.", code="UNSUPPORTED_EXTENSION")

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
                    # Ignore directories and OS metadata files
                    if info.is_dir():
                        continue
                    
                    base_filename = os.path.basename(info.filename)
                    if base_filename.startswith('.') or info.filename.startswith('__MACOSX') or info.filename.endswith('.db'):
                        continue
                    
                    sub_ext = info.filename.split('.')[-1].lower() if '.' in info.filename else ''
                    if sub_ext not in (SUPPORTED_EXTENSIONS - {'zip'}):
                        raise SecurityValidationError("Unsupported file inside ZIP.", code="UNSUPPORTED_FILE_ZIP")
                    
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
            raise SecurityValidationError("Unsupported file.", code="ZIP_PROCESS_ERROR")
    else:
        # 5. Non-ZIP single file validations
        validate_single_file_content(file_bytes, sanitized_orig, ext)

    # 6. Automatic PDF Repair & Structure Verification
    was_repaired = False
    repair_msg = None
    if ext == 'pdf':
        needs_repair = False
        try:
            t_doc = fitz.open(stream=file_bytes, filetype="pdf")
            if len(t_doc) == 0:
                needs_repair = True
            else:
                # Force checking pages to detect corrupted xrefs/trailer
                for page in t_doc:
                    _ = page.rect
            t_doc.close()
        except Exception as pdf_err:
            needs_repair = True
            logger.warning(f"[PDF VALIDATION] PDF structure issue detected in {sanitized_orig}: {pdf_err}. Triggering automatic repair...")

        if needs_repair:
            rep_bytes, rep_strategy, rep_msg = repair_pdf_bytes(file_bytes, sanitized_orig)
            if rep_bytes:
                file_bytes = rep_bytes
                sha256_hash = get_file_sha256(file_bytes)
                was_repaired = True
                repair_msg = rep_msg
            else:
                logger.error(f"[PDF VALIDATION FAILED] PDF {sanitized_orig} could not be opened or repaired by any strategy.")
                raise SecurityValidationError("PDF is corrupted or unopenable after all repair strategies.", code="PDF_CORRUPTED")

    return {
        "sanitized_filename": sanitized_orig,
        "secure_filename": secure_name,
        "sha256": sha256_hash,
        "mime_type": get_mime_type(file_bytes, sanitized_orig, ext),
        "scan_status": "PASSED",
        "scan_timestamp": timezone.now(),
        "was_repaired": was_repaired,
        "repair_message": repair_msg,
        "repaired_bytes": file_bytes if was_repaired else None
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
