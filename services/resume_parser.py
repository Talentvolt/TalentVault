from pathlib import Path


def extract_pdf_text(file_path):
    import fitz
    """
    Extract all text from PDF. Supports local path, Path, or file-like object/stream.
    """

    text = []

    if hasattr(file_path, 'read'):
        # File-like object or Django FieldFile/UploadedFile
        content = file_path.read()
        # Reset pointer if it has seek
        if hasattr(file_path, 'seek'):
            file_path.seek(0)
        pdf = fitz.open(stream=content, filetype="pdf")
    else:
        pdf = fitz.open(file_path)

    for page in pdf:
        page_text = page.get_text()

        if page_text:
            text.append(page_text)

    pdf.close()

    return "\n".join(text)


def parse_resume(file_path):
    """
    Read PDF and return raw text. Supports local path, Path, or file-like object.
    """

    if hasattr(file_path, 'read'):
        filename = getattr(file_path, 'name', 'resume.pdf')
        raw_text = extract_pdf_text(file_path)
    else:
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(file_path)

        if file_path.suffix.lower() != ".pdf":
            raise ValueError("Only PDF supported.")
        
        filename = file_path.name
        raw_text = extract_pdf_text(file_path)

    return {
        "file_name": filename,
        "raw_text": raw_text,
    }