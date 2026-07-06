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

    # Detect extension
    filename = candidate.original_filename or candidate.resume.name
    ext = filename.split('.')[-1].lower() if '.' in filename else ''

    try:
        if ext == 'pdf':
            # PDF Browser Preview
            f = open(file_path, 'rb')
            response = FileResponse(f, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
            return response

        elif ext == 'doc':
            # DOC Headless conversion to PDF
            previews_dir = os.path.join(settings.MEDIA_ROOT, 'previews')
            os.makedirs(previews_dir, exist_ok=True)
            
            # Secure name for converted PDF
            pdf_filename = f"{candidate.id}_preview.pdf"
            pdf_path = os.path.join(previews_dir, pdf_filename)
            
            # Convert if not already cached
            if not os.path.exists(pdf_path):
                convert_doc_to_pdf(file_path, previews_dir)
                # Headless command outputs to <doc_filename>.pdf in outdir
                # So we find it and rename it to our secure ID filename
                default_output_name = os.path.splitext(os.path.basename(file_path))[0] + ".pdf"
                default_output_path = os.path.join(previews_dir, default_output_name)
                if os.path.exists(default_output_path):
                    os.rename(default_output_path, pdf_path)
            
            if os.path.exists(pdf_path):
                f = open(pdf_path, 'rb')
                response = FileResponse(f, content_type='application/pdf')
                response['Content-Disposition'] = f'inline; filename="{pdf_filename}"'
                return response
            else:
                raise Exception("Converted PDF file was not generated.")

        elif ext == 'docx':
            # DOCX Preview Rendering with python-docx
            html_body = None
            try:
                import docx
                doc = docx.Document(file_path)
                
                # Helper function to iterate items in document order
                from docx.text.paragraph import Paragraph
                from docx.table import Table
                
                def iter_block_items(parent):
                    # For a Document, parent.element.body contains child elements
                    parent_elm = parent.element.body
                    for child in parent_elm.iterchildren():
                        if child.tag.endswith('p'):
                            yield Paragraph(child, parent)
                        elif child.tag.endswith('tbl'):
                            yield Table(child, parent)

                def is_bullet_paragraph(p):
                    style_name = p.style.name.lower() if p.style and p.style.name else ""
                    if 'bullet' in style_name or 'list' in style_name:
                        return True
                    text = p.text.strip()
                    if text and text[0] in ('•', '*', '-', 'o', '■', '▪', '♦', '✓', '✔', '★'):
                        return True
                    if text and ord(text[0]) in (0xf0b7, 0xf02d, 0x2022):
                        return True
                    return False

                def clean_bullet_text(text):
                    text = text.strip()
                    bullet_chars = ('•', '*', '-', 'o', '■', '▪', '♦', '✓', '✔', '★')
                    while text and (text[0] in bullet_chars or ord(text[0]) in (0xf0b7, 0xf02d, 0x2022)):
                        text = text[1:].lstrip()
                    return text

                html_elements = []
                in_list = False
                
                for block in iter_block_items(doc):
                    if isinstance(block, Paragraph):
                        text = block.text.strip()
                        if not text:
                            if in_list:
                                html_elements.append("</ul>")
                                in_list = False
                            html_elements.append("<br/>")
                            continue
                            
                        # Bullet/List
                        if is_bullet_paragraph(block):
                            if not in_list:
                                html_elements.append("<ul style='margin-top: 0.5em; margin-bottom: 0.5em;'>")
                                in_list = True
                            cleaned = clean_bullet_text(text)
                            html_elements.append(f"<li>{escape(cleaned)}</li>")
                        else:
                            if in_list:
                                html_elements.append("</ul>")
                                in_list = False
                                
                            style_name = block.style.name.lower() if block.style and block.style.name else ""
                            # Heading
                            if 'heading' in style_name or style_name in ('title', 'subtitle'):
                                level = 2
                                if '1' in style_name:
                                    level = 1
                                elif '3' in style_name:
                                    level = 3
                                elif '4' in style_name:
                                    level = 4
                                html_elements.append(f"<h{level}>{escape(text)}</h{level}>")
                            else:
                                html_elements.append(f"<p>{escape(text)}</p>")
                                
                    elif isinstance(block, Table):
                        if in_list:
                            html_elements.append("</ul>")
                            in_list = False
                            
                        table_html = ["<table border='1' style='border-collapse: collapse; width: 100%; margin-top: 1em; margin-bottom: 1em; border: 1px solid #e5e7eb;'>"]
                        for row in block.rows:
                            table_html.append("<tr>")
                            for cell in row.cells:
                                cell_paras = []
                                for cp in cell.paragraphs:
                                    ctext = cp.text.strip()
                                    if ctext:
                                        cell_paras.append(f"<p style='margin: 4px 0;'>{escape(ctext)}</p>")
                                cell_content = "".join(cell_paras) if cell_paras else "&nbsp;"
                                table_html.append(f"<td style='padding: 8px; border: 1px solid #e5e7eb;'>{cell_content}</td>")
                            table_html.append("</tr>")
                        table_html.append("</table>")
                        html_elements.append("".join(table_html))
                        
                if in_list:
                    html_elements.append("</ul>")
                    
                html_body = "".join(html_elements)
                if not html_body:
                    raise Exception("No text block items extracted from document.")
                    
            except Exception as e_docx:
                import traceback
                tb_docx = traceback.format_exc()
                print(f"[PREVIEW FALLBACK] python-docx engine failed: {e_docx}\nTraceback:\n{tb_docx}")
                logger.error(f"python-docx engine failed: {e_docx}", exc_info=True)
                
                # Safe plain text extraction fallback
                try:
                    import zipfile
                    import xml.etree.ElementTree as ET
                    text_runs = []
                    with zipfile.ZipFile(file_path, 'r') as z:
                        doc_xml = z.read('word/document.xml')
                        root = ET.fromstring(doc_xml)
                        namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                        for p in root.findall('.//w:p', namespaces):
                            p_text = []
                            for t in p.findall('.//w:t', namespaces):
                                if t.text:
                                    p_text.append(t.text)
                            para_text = "".join(p_text).strip()
                            if para_text:
                                text_runs.append(f"<p>{escape(para_text)}</p>")
                                
                    if text_runs:
                        html_body = "".join(text_runs)
                    else:
                        raise Exception("No text runs extracted from document.xml.")
                except Exception as e_manual:
                    tb_manual = traceback.format_exc()
                    print(f"[PREVIEW PARSING FAILURE] XML File: word/document.xml | Exception: {e_manual}\nTraceback:\n{tb_manual}")
                    logger.error(f"[PREVIEW PARSING FAILURE] XML File: word/document.xml | Exception: {e_manual}", exc_info=True)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            raw_text = f.read()
                        printable = "".join(c for c in raw_text if c.isprintable() or c in '\n\r\t')
                        html_body = f"<pre>{escape(printable[:2000])}</pre>"
                    except Exception:
                        html_body = "<p>Could not extract text preview from document.</p>"
            
            premium_html = get_premium_html_wrapper(html_body, title=candidate.full_name or "Resume Preview")
            return HttpResponse(premium_html, content_type='text/html')

        elif ext == 'rtf':
            # RTF Render to HTML
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                rtf_content = f.read()
            text = rtf_to_text(rtf_content)
            # Format text paragraphs
            html_body = "".join([f"<p>{escape(line.strip())}</p>" for line in text.split('\n') if line.strip()])
            premium_html = get_premium_html_wrapper(html_body, title=candidate.full_name or "Resume Preview")
            return HttpResponse(premium_html, content_type='text/html')

        elif ext == 'txt':
            # TXT Render to Plain Text inside styled pre block
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                txt_content = f.read()
            html_body = f"<pre>{escape(txt_content)}</pre>"
            premium_html = get_premium_html_wrapper(html_body, title=candidate.full_name or "Resume Preview")
            return HttpResponse(premium_html, content_type='text/html')

        else:
            return HttpResponse(get_error_html_wrapper("Unsupported preview format."), status=400)

    except Exception as e:
        logger.error(f"Error generating preview for candidate {candidate.id}: {e}", exc_info=True)
        # Return a user-friendly message inside the styled iframe
        err_msg = str(e)
        if "LibreOffice" in err_msg:
            err_msg = "LibreOffice not found or failed to execute on server. Headless DOC preview is currently disabled."
        return HttpResponse(get_error_html_wrapper(f"Could not load document preview. {err_msg}"), status=200)
