"""
Regression tests for scanned / image-only PDF support in the resume parsing pipeline.

Covers:
  * normal text PDFs continue to use direct extraction (no OCR)
  * image/scanned PDFs are rendered at high DPI and OCR'd
  * OCR-recovered text is forwarded to Parseora via ``raw_text``
  * OCR failure is reported (no empty candidate is saved as "SUCCESS")
  * Parseora timeout is handled safely (NLP fallback / graceful failure)
"""

import io
from unittest.mock import patch, MagicMock

import pytest

from apps.candidates.utils import process_resume_file
from services.resume_intelligence import ResumeIntelligenceService


OCR_TEXT = (
    "Ayaj Khan\n"
    "Software Engineer\n"
    "Work Experience\n"
    "Senior Engineer at Acme Corp (2020 - 2023)\n"
    "Engineer at Beta Ltd (2017 - 2020)\n"
    "Intern at Gamma Inc (2016 - 2017)"
)

PARSED_RESULT = {
    "personal_info": {
        "name": "Ayaj Khan",
        "email": "ayaj@example.com",
        "phone": "9876543210",
        "location": "Jodhpur",
        "current_company": "Acme Corp",
        "current_designation": "Senior Engineer",
        "total_experience": 7.0,
    },
    "summary": "Software engineer.",
    "skills": ["Python"],
    "experience": [
        {"company": "Acme Corp", "designation": "Senior Engineer",
         "start_date": "2020-01-01", "end_date": "2023-01-01", "description": "did things"},
        {"company": "Beta Ltd", "designation": "Engineer",
         "start_date": "2017-01-01", "end_date": "2020-01-01", "description": "built stuff"},
        {"company": "Gamma Inc", "designation": "Intern",
         "start_date": "2016-01-01", "end_date": "2017-01-01", "description": "learned"},
    ],
    "education": [],
    "projects": [],
    "certifications": [],
}

_VALID_OCR_RESULT = {
    "text": OCR_TEXT,
    "engine": "PaddleOCR",
    "confidence": 95.0,
    "resume_type": "SCANNED_PDF",
    "largest_bold_name": None,
}


def _make_scanned_pdf_bytes(pages=1):
    """Build a PDF with NO text layer (image-only) using PyMuPDF + PIL."""
    import fitz
    from PIL import Image, ImageDraw

    doc = fitz.open()
    for _ in range(pages):
        img = Image.new("RGB", (1240, 1754), "white")
        draw = ImageDraw.Draw(img)
        draw.text((120, 120), "Ayaj Khan", fill="black")
        draw.text((120, 170), "Software Engineer", fill="black")
        draw.text((120, 220), "Work Experience", fill="black")
        draw.text((120, 280), "Senior Engineer at Acme Corp (2020 - 2023)", fill="black")
        draw.text((120, 340), "Engineer at Beta Ltd (2017 - 2020)", fill="black")
        draw.text((120, 400), "Intern at Gamma Inc (2016 - 2017)", fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page = doc.new_page(width=612, height=792)
        page.insert_image(page.rect, stream=buf.getvalue())
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _security_data(seed):
    return {
        "sanitized_filename": f"{seed}.pdf",
        "secure_filename": f"{seed}_secure.pdf",
        "sha256": seed.ljust(64, "0")[:64],
        "mime_type": "application/pdf",
        "scan_status": "PASSED",
        "scan_timestamp": None,
    }


def _fake_paddle_ocr(lines):
    """Return a MagicMock paddle instance whose .ocr() yields PaddleOCR-shaped output."""
    result = []
    for text in lines:
        bbox = [[0, 0], [100, 0], [100, 20], [0, 20]]
        result.append([bbox, (text, 0.98)])
    inst = MagicMock()
    inst.ocr.return_value = [result]
    return inst


def _run_process_resume_file(
    file_bytes,
    filename,
    ocr_result=_VALID_OCR_RESULT,
    parseora_result=PARSED_RESULT,
    parseora_side_effect=None,
):
    """Run process_resume_file with heavy external integrations mocked."""
    with patch(
        "services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline",
        return_value=ocr_result,
    ), patch(
        "apps.candidates.utils.parse_resume_via_parseora",
        return_value=parseora_result,
        side_effect=parseora_side_effect,
    ), patch(
        "apps.candidates.utils.extract_profile_photo",
        return_value=(None, None),
    ), patch(
        "services.resume_storage_service.upload_and_verify_resume",
        return_value=("resumes/test.pdf", b"x"),
    ), patch(
        "services.resume_storage_service.copy_and_verify_original_resume",
        return_value="resumes/original/test.pdf",
    ), patch(
        "services.candidate_matching_service.CandidateMatchingService.update_ats_scores",
        return_value=None,
    ), patch(
        "services.candidate_tagging_service.CandidateTaggingService.tag_candidate_profile",
        return_value=None,
    ):
        return process_resume_file(
            io.BytesIO(file_bytes),
            filename,
            security_data=_security_data("scanned_test"),
        )


# --------------------------------------------------------------------------- #
# 1. Normal text PDF uses direct extraction (no OCR)
# --------------------------------------------------------------------------- #

def test_normal_text_pdf_bypasses_ocr():
    from tests.test_resume_parser_fallback import VALID_PDF_BYTES
    with patch("services.resume_intelligence.get_paddle_ocr_instance") as mock_ocr:
        res = ResumeIntelligenceService.run_ocr_pipeline(VALID_PDF_BYTES, "text_resume.pdf")
        assert "text" in res
        # Direct extraction must not invoke the OCR engine.
        mock_ocr.assert_not_called()


# --------------------------------------------------------------------------- #
# 2. Image/scanned PDF is rendered and OCR'd
# --------------------------------------------------------------------------- #

def test_scanned_pdf_triggers_ocr():
    scanned_bytes = _make_scanned_pdf_bytes(pages=1)
    fake_ocr_text = [
        "Ayaj Khan",
        "Software Engineer",
        "Work Experience",
        "Senior Engineer at Acme Corp (2020 - 2023)",
    ]
    with patch(
        "services.resume_intelligence.get_paddle_ocr_instance",
        return_value=_fake_paddle_ocr(fake_ocr_text),
    ):
        res = ResumeIntelligenceService.run_ocr_pipeline(scanned_bytes, "scanned_resume.pdf")
    assert "Ayaj Khan" in res["text"]
    assert res["engine"] == "PaddleOCR"


# --------------------------------------------------------------------------- #
# 3. OCR-recovered text is forwarded to Parseora as raw_text
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_ocr_text_forwarded_to_parseora():
    scanned_bytes = _make_scanned_pdf_bytes(pages=1)
    captured = {}

    def _parseora(file_bytes, filename, raw_text=None):
        captured["raw_text"] = raw_text
        return PARSED_RESULT

    profile, status = _run_process_resume_file(
        scanned_bytes,
        "scanned_resume.pdf",
        parseora_side_effect=_parseora,
    )
    assert status == "SUCCESS"
    assert profile is not None
    # The OCR-recovered text must be sent to Parseora so it does not time out
    # trying to extract text from an image-only PDF.
    assert captured.get("raw_text")
    assert "Acme Corp" in captured["raw_text"]
    assert profile.experiences.count() == 3


# --------------------------------------------------------------------------- #
# 4. OCR failure must be reported, not saved as an empty "SUCCESS"
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_ocr_failure_reports_failure_not_success():
    scanned_bytes = _make_scanned_pdf_bytes(pages=1)
    empty_ocr = {
        "text": "",
        "engine": "None",
        "confidence": 0.0,
        "resume_type": "SCANNED_PDF",
        "largest_bold_name": None,
    }
    profile, status = _run_process_resume_file(
        scanned_bytes,
        "scanned_resume.pdf",
        ocr_result=empty_ocr,
        parseora_result=None,  # Parseora produced nothing
    )
    assert status != "SUCCESS"
    assert profile is None


# --------------------------------------------------------------------------- #
# 5. Parseora timeout is handled safely (falls back to NLP, no crash)
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_parseora_timeout_falls_back_gracefully():
    scanned_bytes = _make_scanned_pdf_bytes(pages=1)

    def _parseora_timeout(file_bytes, filename, raw_text=None):
        raise TimeoutError("Parseora timed out")

    profile, status = _run_process_resume_file(
        scanned_bytes,
        "scanned_resume.pdf",
        parseora_side_effect=_parseora_timeout,
    )
    # Must not raise; either a graceful failure or NLP fallback is acceptable.
    assert status in ("SUCCESS", "AUTOMATIC_PARSING_FAILED")
