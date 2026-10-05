"""
Hardening regression tests for the resume parsing pipeline.

These tests lock in the guarantees that prevent bad data from flowing through:

  * parser/converter error strings are never treated as resume text
  * binary garbage / empty files never become a "SUCCESS" candidate
  * an address is never mapped to the Professional Summary (Parseora + NLP)
  * Objective / Career Objective / Professional Summary map correctly
  * DOCX failure yields an explicit failure (empty text), not an error string
"""

import io
from unittest.mock import patch

import pytest

from apps.candidates.utils import clean_extracted_text, is_parser_error_text, process_resume_file
from services.resume_intelligence import ResumeIntelligenceService

OBJECTIVE = (
    "To enhance my professional skills, capabilities and knowledge in an "
    "organization which recognizes the value of hard work and trusts me with "
    "responsibilities and challenges."
)
ADDRESS = "Ram Kakade Chawl, Plot No 12, Near Bus Stop, Panvel, Raigad, Maharashtra 410206"


# --------------------------------------------------------------------------- #
# Text cleaning / error detection helpers
# --------------------------------------------------------------------------- #

def test_clean_extracted_text_strips_null_bytes_and_garbage():
    assert clean_extracted_text("John\x00\x01Doe\nEngineer") == "JohnDoe\nEngineer"
    assert clean_extracted_text(None) == ""
    assert clean_extracted_text("") == ""


def test_is_parser_error_text_detects_error_strings():
    assert is_parser_error_text("DOC Parse Error: LibreOffice not found")
    assert is_parser_error_text("Could not open document.")
    assert is_parser_error_text("Empty or unparseable ZIP file content")
    assert is_parser_error_text("RTF Parse Error: something")
    assert not is_parser_error_text("John Doe\nSoftware Engineer")


# --------------------------------------------------------------------------- #
# run_ocr_pipeline must never return error strings as text
# --------------------------------------------------------------------------- #

def test_docx_failure_returns_empty_text_not_error_string():
    # Not a valid DOCX (it's actually OLE2/PDF-like junk); python-docx raises.
    res = ResumeIntelligenceService.run_ocr_pipeline(b"not a real docx file", "bad.docx")
    assert res["text"] == ""
    assert "Parse Error" not in res["text"]
    assert res["confidence"] == 0.0


def test_zip_empty_returns_empty_text_not_error_string():
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("notes.csv", "no resume here")
    res = ResumeIntelligenceService.run_ocr_pipeline(buf.getvalue(), "bundle.zip")
    # Only .pdf/.docx/.doc/.rtf/.txt/.png/.jpg/.jpeg are eligible; none present.
    assert res["text"] == ""
    assert "unparseable" not in res["text"].lower()


# --------------------------------------------------------------------------- #
# Error text / empty / binary must never be saved as a SUCCESS candidate
# --------------------------------------------------------------------------- #

def _run(file_bytes, filename, ocr_result, parseora_result=None):
    with patch(
        "services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline",
        return_value=ocr_result,
    ), patch(
        "apps.candidates.utils.parse_resume_via_parseora",
        return_value=parseora_result,
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
            security_data={
                "sanitized_filename": filename,
                "secure_filename": filename,
                "sha256": "h" * 64,
                "mime_type": "application/octet-stream",
                "scan_status": "PASSED",
                "scan_timestamp": None,
            },
        )


@pytest.mark.django_db
def test_error_text_is_not_saved_as_success():
    ocr_result = {
        "text": "DOC Parse Error: LibreOffice was not found or failed to execute.",
        "engine": "soffice-pdf-fallback",
        "confidence": 50.0,
        "resume_type": "EDITABLE_DOC",
        "largest_bold_name": None,
    }
    profile, status = _run(b"\x00binary", "resume.doc", ocr_result, parseora_result=None)
    assert status != "SUCCESS"
    assert profile is None


@pytest.mark.django_db
def test_empty_file_is_not_saved_as_success():
    ocr_result = {"text": "", "engine": "None", "confidence": 0.0,
                  "resume_type": "UNKNOWN", "largest_bold_name": None}
    profile, status = _run(b"", "empty.pdf", ocr_result, parseora_result=None)
    assert status != "SUCCESS"
    assert profile is None


@pytest.mark.django_db
def test_binary_garbage_is_not_saved_as_success():
    ocr_result = {"text": "", "engine": "None", "confidence": 0.0,
                  "resume_type": "CORRUPTED", "largest_bold_name": None}
    profile, status = _run(b"\x00\x01\x02\x03\x04binary\xff\xfe", "garbage.pdf", ocr_result, parseora_result=None)
    assert status != "SUCCESS"
    assert profile is None


# --------------------------------------------------------------------------- #
# IMPORTANT REGRESSION: Objective -> summary, Address -> never summary
# --------------------------------------------------------------------------- #

RESUME_TEXT = (
    "Ram Kakade\n"
    "Software Engineer\n"
    "ram.kakade@example.com\n"
    "+91 98765 43210\n"
    "\n"
    "Objective:\n"
    f"{OBJECTIVE}\n"
    "\n"
    "Address:\n"
    f"{ADDRESS}\n"
    "\n"
    "Work Experience:\n"
    "Software Engineer at ABC Corp (2020 - Present)\n"
    "\n"
    "Education:\n"
    "B.E. Computer Engineering, Mumbai University (2016)\n"
    "\n"
    "Skills:\n"
    "Python, Java, SQL\n"
)


def test_nlp_objective_maps_to_summary_not_address():
    parsed = ResumeIntelligenceService.parse_resume_nlp(RESUME_TEXT)

    # Objective becomes the professional summary.
    assert parsed["summary"].startswith("To enhance my professional skills")

    # The postal address is never the summary.
    assert "Ram Kakade Chawl" not in parsed["summary"]
    assert "410206" not in parsed["summary"]
    assert "Panvel" not in parsed["summary"]

    # Address is captured as address, and other sections remain separate.
    assert "410206" in str(parsed["personal_info"].get("address", ""))
    assert parsed["skills"]
    assert parsed["experience"]
    assert parsed["education"]


def test_parseora_objective_maps_to_summary_not_address():
    from services.parseora_service import ParseoraService

    res = {
        "candidate": {
            "name": "Ram Kakade",
            "email": "ram.kakade@example.com",
            "phone": "+91 98765 43210",
            "summary": {"value": ADDRESS},
            "objective": {"value": ""},
        },
        "raw_parsed_data": {"career_objective": OBJECTIVE},
        "skills": {"technical_skills": ["Python", "Java", "SQL"]},
        "experience": [
            {"company_name": "ABC Corp", "job_title": "Software Engineer",
             "start_date": "2020-01-01", "end_date": "Present"},
        ],
        "education": [
            {"degree": "B.E", "college": "Mumbai University",
             "field_of_study": "Computer Engineering", "end_year": "2016"},
        ],
    }
    mapped = ParseoraService.map_response_to_talentvault(res)
    assert mapped["summary"] == OBJECTIVE
    assert "Ram Kakade Chawl" not in mapped["summary"]
    assert "410206" not in mapped["summary"]
    # Experience, education and skills remain intact.
    assert mapped["experience"]
    assert mapped["education"]
    assert mapped["skills"]
