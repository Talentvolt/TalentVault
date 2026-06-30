from pathlib import Path
import fitz


def extract_pdf_text(file_path):
    """
    Extract all text from PDF.
    """

    text = []

    pdf = fitz.open(file_path)

    for page in pdf:
        page_text = page.get_text()

        if page_text:
            text.append(page_text)

    pdf.close()

    return "\n".join(text)


def parse_resume(file_path):
    """
    Read PDF and return raw text.
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(file_path)

    if file_path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF supported.")

    raw_text = extract_pdf_text(file_path)

    return {
        "file_name": file_path.name,
        "raw_text": raw_text,
    }