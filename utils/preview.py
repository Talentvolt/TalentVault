import os
import io
import subprocess
import logging
import mammoth
from striprtf.striprtf import rtf_to_text
from django.conf import settings
from django.http import HttpResponse, FileResponse
from django.utils.html import escape

logger = logging.getLogger(__name__)

def _resolve_candidates(names_and_paths):
    """
    Resolve an ordered list of executable names / absolute paths to concrete
    invocations, deduplicated and preserving order.

    Bare names are resolved via PATH (``shutil.which``) but are kept even when
    ``which`` finds nothing, so ``subprocess`` can attempt its own PATH search.
    Absolute paths are kept only if the file actually exists.
    """
    import shutil

    resolved = []
    seen = set()
    for cand in names_and_paths:
        if not cand:
            continue
        if os.path.sep in cand or (os.altsep and os.altsep in cand):
            loc = cand if os.path.isfile(cand) else None
        else:
            loc = shutil.which(cand) or cand
        if loc and loc not in seen:
            seen.add(loc)
            resolved.append(loc)
    return resolved


def _antiword_candidates():
    """antiword executable candidates for Windows and Linux."""
    return _resolve_candidates([
        "antiword",
        "antiword.exe",
        "/usr/bin/antiword",
        "/usr/local/bin/antiword",
        r"C:\antiword\antiword.exe",
    ])


def _catdoc_candidates():
    """catdoc executable candidates for Windows and Linux."""
    return _resolve_candidates([
        "catdoc",
        "catdoc.exe",
        "/usr/bin/catdoc",
        "/usr/local/bin/catdoc",
    ])


def _libreoffice_candidates():
    """
    LibreOffice (soffice) executable candidates for Windows and Linux.

    Checks the configured ``SOFFICE_PATH``, PATH (``soffice``/``libreoffice``),
    the standard Windows install directories, and common Linux install paths.
    """
    cands = []
    soffice_setting = getattr(settings, 'SOFFICE_PATH', None)
    if soffice_setting:
        cands.append(soffice_setting)
    cands += [
        "soffice",
        "libreoffice",
        "soffice.exe",
        "libreoffice.exe",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/usr/local/bin/soffice",
        "/usr/local/bin/libreoffice",
        "/opt/libreoffice/program/soffice",
        "/opt/libreoffice24.2/program/soffice",
    ]
    return _resolve_candidates(cands)


def convert_doc_to_pdf(doc_path, output_dir):
    """
    Converts a DOC file to PDF using headless LibreOffice.
    """
    # LibreOffice needs a writable HOME (its user profile) even in headless
    # mode. On managed hosts HOME may be unset/read-only, so point it at a
    # per-call temp dir that we clean up afterwards.
    import tempfile

    env = os.environ.copy()
    home_tmp = None
    if not env.get("HOME") or not os.path.isdir(env.get("HOME", "")):
        try:
            home_tmp = tempfile.mkdtemp(prefix="soffice_home_")
            env["HOME"] = home_tmp
        except Exception:
            home_tmp = None

    success = False
    try:
        for path in _libreoffice_candidates():
            try:
                cmd = [path, '--headless', '--convert-to', 'pdf', '--outdir', output_dir, doc_path]
                # Use shell=True on Windows if soffice is a batch/cmd file or in path, otherwise list is fine
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30, env=env)
                success = True
                break
            except Exception as e:
                logger.debug(f"LibreOffice run failed with path {path}: {e}")
                continue
    finally:
        if home_tmp:
            try:
                import shutil
                shutil.rmtree(home_tmp, ignore_errors=True)
            except Exception:
                pass

    if not success:
        raise Exception("LibreOffice soffice was not found or failed to execute. Headless conversion is disabled.")


def _run_doc_extractor(cmd, name):
    """
    Runs a single .doc text extractor and returns clean text, or "" on failure.
    Non-printable characters (raw binary) are stripped so garbage is never
    returned as resume text.
    """
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    except Exception as e:
        logger.debug(f"{name} DOC extraction failed: {e}")
        return ""
    if res.returncode != 0:
        return ""
    text = res.stdout.decode("utf-8", errors="ignore")
    text = "".join(c for c in text if c.isprintable() or c in "\n\r\t")
    return text.strip()


def extract_text_from_doc(file_bytes):
    """
    Extracts plain text from a legacy .doc (OLE2 binary) file.

    Legacy .doc is a binary format that cannot be read as UTF-8 text and
    cannot be parsed by python-docx/mammoth. This helper centralises the
    available converters and returns clean text (never raw binary bytes and
    never an error string). Order of preference:

      1. antiword   -- installed in production (render.yaml), no LibreOffice
      2. catdoc     -- plain-text fallback
      3. LibreOffice -> PDF -> PyMuPDF text (existing conversion architecture)

    Returns the extracted text, or "" when every converter failed or yielded
    no usable content.
    """
    import tempfile

    if not file_bytes:
        return ""

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        # 1. antiword
        for antiword in _antiword_candidates():
            candidate = _run_doc_extractor([antiword, tmp_path], "antiword")
            if candidate:
                return candidate

        # 2. catdoc
        for catdoc in _catdoc_candidates():
            candidate = _run_doc_extractor([catdoc, tmp_path], "catdoc")
            if candidate:
                return candidate

        # 3. LibreOffice -> PDF -> text
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                convert_doc_to_pdf(tmp_path, tmpdir)
                pdfs = [f for f in os.listdir(tmpdir) if f.lower().endswith(".pdf")]
                if pdfs:
                    pdf_path = os.path.join(tmpdir, pdfs[0])
                    import fitz
                    doc = fitz.open(pdf_path)
                    try:
                        candidate = "\n".join(page.get_text() for page in doc).strip()
                    finally:
                        doc.close()
                    if candidate:
                        return candidate
        except Exception as e:
            logger.debug(f"LibreOffice DOC text extraction failed: {e}")

        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def get_premium_html_wrapper(content_body, title="Resume Preview"):
    """
    Wraps content in a styled premium HTML page for preview in iframes.
    """
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="robots" content="noindex, nofollow">
    <title>{escape(title)}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #1f2937;
            background-color: #f3f4f6;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
        }}
        .preview-container {{
            background: #ffffff;
            width: 100%;
            max-width: 850px;
            min-height: 100vh;
            padding: 40px 50px;
            box-sizing: border-box;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);
            border-radius: 8px;
            border: 1px solid #e5e7eb;
        }}
        /* Keep margins standard for printing/resumes */
        h1, h2, h3, h4, h5, h6 {{
            color: #111827;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}
        p {{
            line-height: 1.6;
            margin-bottom: 1em;
        }}
        pre {{
            font-family: 'Courier New', Courier, monospace;
            background-color: #f9fafb;
            padding: 15px;
            border-radius: 6px;
            border: 1px solid #e5e7eb;
            white-space: pre-wrap;
            word-break: break-all;
            color: #374151;
        }}
    </style>
</head>
<body>
    <div class="preview-container">
        {content_body}
    </div>
</body>
</html>"""

def get_error_html_wrapper(error_message):
    """
    Renders a premium error page inside the iframe.
    """
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #fef2f2;
            color: #991b1b;
            margin: 0;
            padding: 40px;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 80vh;
        }}
        .error-card {{
            background: #ffffff;
            border: 1px solid #fee2e2;
            border-radius: 8px;
            padding: 30px;
            max-width: 500px;
            text-align: center;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
        }}
        h3 {{
            margin-top: 0;
            color: #991b1b;
        }}
        p {{
            color: #7f1d1d;
            font-size: 14px;
            line-height: 1.5;
        }}
    </style>
</head>
<body>
    <div class="error-card">
        <h3>Preview Unavailable</h3>
        <p>{escape(error_message)}</p>
    </div>
</body>
</html>"""

def generate_resume_preview_response(candidate):
    """
    Processes the candidate's resume and returns an inline Django HTTP/File Response.
    Supports PDF, DOC, DOCX, RTF, TXT.
    Handles missing/deleted S3 objects gracefully with a user-friendly error instead of a 500.
    """
    if not candidate.resume or not candidate.resume.name:
        return HttpResponse(get_error_html_wrapper("No resume file associated with this profile."), status=404)

    try:
        exists = candidate.resume.storage.exists(candidate.resume.name)
    except Exception as e_exists:
        logger.warning(f"Storage exists check failed for {candidate.resume.name}: {e_exists}")
        exists = False

    if not exists:
        return HttpResponse(get_error_html_wrapper("Resume file was not found in storage."), status=404)

    import tempfile
    import os
    from utils.s3 import get_content_type
    
    file_path = None
    is_temp = False
    
    try:
        file_path = candidate.resume.path
    except NotImplementedError:
        # S3 storage or other non-local storage
        ext = os.path.splitext(candidate.resume.name)[1]
        try:
            candidate.resume.open("rb")
            file_content = candidate.resume.read()
            temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            temp_file.write(file_content)
            temp_file.close()
            file_path = temp_file.name
            is_temp = True
        except Exception as temp_err:
            logger.error(f"Failed to create temporary file for preview: {temp_err}", exc_info=True)
            return HttpResponse(get_error_html_wrapper("Resume file is no longer available in cloud storage."), status=404)

    filename = candidate.original_filename or os.path.basename(candidate.resume.name) or "resume"
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    # Calculate file metadata for fallback
    try:
        file_size_kb = round(os.path.getsize(file_path) / 1024, 1)
    except Exception:
        file_size_kb = 0.0
        
    mime_type = candidate.mime_type or get_content_type(filename)
    try:
        download_url = candidate.resume_file_url
    except Exception:
        download_url = "#"
    extracted_text = candidate.raw_resume_text or "No extracted text available."

    def get_fallback_html():
        body = f"""
        <div style="padding: 20px; text-align: center;">
            <div style="background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 30px; margin-bottom: 20px;">
                <svg style="width: 48px; height: 48px; color: #9ca3af; margin-bottom: 15px; display: inline-block;" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                </svg>
                <h4 style="margin-top: 5px; margin-bottom: 5px; color: #111827; font-size: 18px; font-weight: 600;">{escape(filename)}</h4>
                <p style="color: #6b7280; font-size: 14px; margin-bottom: 20px;">{escape(mime_type)} &bull; {file_size_kb} KB</p>
                <a href="{download_url}" target="_parent" style="display: inline-block; background-color: #2563eb; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; font-size: 14px; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05); transition: background-color 0.2s;">Download Resume</a>
            </div>
            
            <div style="text-align: left;">
                <h5 style="color: #374151; margin-bottom: 10px; font-size: 14px; font-weight: 600;">Extracted Text Content:</h5>
                <div style="max-height: 400px; overflow-y: auto; background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 15px; font-family: 'Courier New', Courier, monospace; font-size: 13px; white-space: pre-wrap; color: #4b5563; line-height: 1.5; text-align: left;">{escape(extracted_text)}</div>
            </div>
        </div>
        """
        return get_premium_html_wrapper(body, title=filename)

    try:
        if ext == 'pdf':
            # PDF preview using PyMuPDF
            try:
                import fitz
                import base64
                doc = fitz.open(file_path)
                html_elements = []
                for page in doc:
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
                    html_elements.append(f'<img src="data:image/png;base64,{img_base64}" style="width:100%; max-width: 100%; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #e5e7eb;" />')
                doc.close()
                html_body = "".join(html_elements)
                premium_html = get_premium_html_wrapper(html_body, title=candidate.full_name or "Resume Preview")
                return HttpResponse(premium_html, content_type='text/html')
            except Exception as e_pdf:
                logger.error(f"PyMuPDF PDF preview failed: {e_pdf}", exc_info=True)
                # Fallback to direct FileResponse (needed for tests with mock PDF bytes)
                try:
                    f = open(file_path, 'rb')
                    response = FileResponse(f, content_type='application/pdf')
                    response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
                    return response
                except Exception:
                    return HttpResponse(get_fallback_html(), content_type='text/html')

        elif ext == 'docx':
            # DOCX preview using Mammoth
            try:
                with open(file_path, "rb") as docx_file:
                    result = mammoth.convert_to_html(docx_file)
                    html_body = result.value
                    if not html_body:
                        raise Exception("Mammoth returned empty HTML.")
                    premium_html = get_premium_html_wrapper(html_body, title=candidate.full_name or "Resume Preview")
                    return HttpResponse(premium_html, content_type='text/html')
            except Exception as e_docx:
                logger.error(f"Mammoth DOCX preview failed: {e_docx}", exc_info=True)
                # Fallback to python-docx or graceful fallback
                try:
                    import docx
                    doc = docx.Document(file_path)
                    html_elements = []
                    for para in doc.paragraphs:
                        text = para.text.strip()
                        if text:
                            html_elements.append(f"<p>{escape(text)}</p>")
                    if not html_elements:
                        raise Exception("python-docx returned empty text.")
                    html_body = "".join(html_elements)
                    premium_html = get_premium_html_wrapper(html_body, title=candidate.full_name or "Resume Preview")
                    return HttpResponse(premium_html, content_type='text/html')
                except Exception as e_docx_fallback:
                    logger.error(f"python-docx DOCX preview failed: {e_docx_fallback}", exc_info=True)
                    return HttpResponse(get_fallback_html(), content_type='text/html')

        elif ext == 'doc':
            # DOC preview using antiword
            try:
                cmd = ["antiword", file_path]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10)
                text = res.stdout.decode('utf-8', errors='ignore')
                html_body = "".join([f"<p>{escape(line.strip())}</p>" for line in text.split('\n') if line.strip()])
                if not html_body:
                    raise Exception("Antiword returned empty text.")
                premium_html = get_premium_html_wrapper(html_body, title=candidate.full_name or "Resume Preview")
                return HttpResponse(premium_html, content_type='text/html')
            except Exception as e_antiword:
                logger.warning(f"Antiword DOC conversion failed or not installed: {e_antiword}")
                return HttpResponse(get_fallback_html(), content_type='text/html')

        elif ext == 'rtf':
            # RTF Render to HTML
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    rtf_content = f.read()
                text = rtf_to_text(rtf_content)
                html_body = "".join([f"<p>{escape(line.strip())}</p>" for line in text.split('\n') if line.strip()])
                premium_html = get_premium_html_wrapper(html_body, title=candidate.full_name or "Resume Preview")
                return HttpResponse(premium_html, content_type='text/html')
            except Exception as e_rtf:
                logger.error(f"RTF preview failed: {e_rtf}", exc_info=True)
                return HttpResponse(get_fallback_html(), content_type='text/html')

        elif ext == 'txt':
            # TXT Render to Plain Text inside styled pre block
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    txt_content = f.read()
                html_body = f"<pre>{escape(txt_content)}</pre>"
                premium_html = get_premium_html_wrapper(html_body, title=candidate.full_name or "Resume Preview")
                return HttpResponse(premium_html, content_type='text/html')
            except Exception as e_txt:
                logger.error(f"TXT preview failed: {e_txt}", exc_info=True)
                return HttpResponse(get_fallback_html(), content_type='text/html')

        else:
            return HttpResponse(get_fallback_html(), content_type='text/html')

    except Exception as e:
        logger.error(f"Error generating preview for candidate {candidate.id}: {e}", exc_info=True)
        return HttpResponse(get_fallback_html(), content_type='text/html')
    finally:
        if is_temp and file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
