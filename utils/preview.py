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

def convert_doc_to_pdf(doc_path, output_dir):
    """
    Converts a DOC file to PDF using headless LibreOffice.
    """
    soffice_path = getattr(settings, 'SOFFICE_PATH', 'soffice')
    possible_paths = [
        soffice_path,
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    
    success = False
    for path in possible_paths:
        try:
            cmd = [path, '--headless', '--convert-to', 'pdf', '--outdir', output_dir, doc_path]
            # Use shell=True on Windows if soffice is a batch/cmd file or in path, otherwise list is fine
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30)
            success = True
            break
        except Exception as e:
            logger.debug(f"LibreOffice run failed with path {path}: {e}")
            continue
            
    if not success:
        raise Exception("LibreOffice soffice was not found or failed to execute. Headless conversion is disabled.")

def get_premium_html_wrapper(content_body, title="Resume Preview"):
    """
    Wraps content in a styled premium HTML page for preview in iframes.
    """
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
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
    """
    if not candidate.resume:
        return HttpResponse(get_error_html_wrapper("No resume file associated with this profile."), status=404)

    file_path = candidate.resume.path
    if not os.path.exists(file_path):
        return HttpResponse(get_error_html_wrapper("Resume file was not found on disk."), status=404)

    filename = candidate.original_filename or os.path.basename(candidate.resume.name) or "resume"
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    # Calculate file metadata for fallback
    try:
        file_size_kb = round(os.path.getsize(file_path) / 1024, 1)
    except Exception:
        file_size_kb = 0.0
        
    mime_type = candidate.mime_type or f"application/{ext}"
    download_url = candidate.resume.url
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
