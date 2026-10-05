"""
Regression tests for legacy .doc (OLE2 binary) resume parsing.

These tests drive the REAL pipeline for a real .doc file:

    process_resume_file -> run_ocr_pipeline (DOC branch) -> extract_text_from_doc
        -> (antiword -> catdoc -> LibreOffice) -> Parseora -> CandidateRecord

Coverage:

  * converter fallback chain (unit, ``subprocess.run`` stubbed)
  * a REAL .doc file converted by the REAL LibreOffice/antiword binary
  * end-to-end persistence: name / email / phone / experience / education /
    skills, plus "Parseora receives clean text, never binary .doc bytes"
  * conversion failure yields an explicit parse failure (no empty candidate)

The only external boundaries stubbed in the end-to-end test are the Parseora
HTTP API, resume storage, photo extraction, and ATS/tagging. The .doc
conversion itself runs for real when a converter is installed.
"""

import io
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.candidates.utils import process_resume_file
from services.resume_intelligence import ResumeIntelligenceService
from utils.preview import extract_text_from_doc

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
REAL_DOC_FIXTURE = os.path.join(FIXTURES_DIR, "sample_resume.doc")

# Real OLE2 Compound File Binary (.doc) header followed by opaque content
# (used only by the mocked-converter unit tests).
DOC_BYTES = (
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x3e\x00\x03\x00\xfe\xff\x09\x00"
    b"\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00"
    + b"legacy word document content"
)

DOC_TEXT = (
    "Amit Sharma\n"
    "Senior Software Engineer\n"
    "amit.sharma@example.com\n"
    "+91 90123 45678\n"
    "WORK EXPERIENCE\n"
    "Senior Engineer at TechCorp (2020 - 2024)\n"
    "Engineer at SoftLabs (2017 - 2020)\n"
    "EDUCATION\n"
    "B.Tech in Computer Science, IIT Delhi (2017)\n"
    "SKILLS\n"
    "Python, Django, SQL"
)

# Realistic Parseora structured response matching the real .doc resume content.
PARSEORA_RESUME_JSON = {
    "request_id": "req_legacy_doc_001",
    "candidate": {
        "name": "Amit Sharma",
        "email": "amit.sharma@example.com",
        "phone": "+91 90123 45678",
        "current_company": "TechCorp",
        "current_designation": "Senior Engineer",
        "current_location": "Bangalore",
        "summary": "Senior software engineer with backend expertise.",
    },
    "skills": {"technical_skills": ["Python", "Django", "SQL"]},
    "experience": [
        {"company_name": "TechCorp", "job_title": "Senior Engineer",
         "start_date": "2020-01-01", "end_date": "2024-01-01",
         "location": "Bangalore", "responsibilities": ["Built services"]},
        {"company_name": "SoftLabs", "job_title": "Engineer",
         "start_date": "2017-01-01", "end_date": "2020-01-01",
         "location": "Mumbai", "responsibilities": ["Developed apps"]},
    ],
    "education": [
        {"degree": "B.Tech", "college": "IIT Delhi",
         "field_of_study": "Computer Science", "end_year": "2017"},
    ],
    "projects": [],
    "certifications": [],
    "languages": [],
    "achievements": [],
}


def _converter_available():
    """True when at least one .doc text converter is actually installed."""
    for exe in ("antiword", "catdoc", "soffice", "libreoffice"):
        if shutil.which(exe):
            return True
    for p in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/usr/bin/antiword",
        "/usr/bin/catdoc",
    ):
        if os.path.isfile(p):
            return True
    return False


def _load_real_doc():
    with open(REAL_DOC_FIXTURE, "rb") as fh:
        return fh.read()


@pytest.fixture
def local_media(settings):
    media_root = tempfile.mkdtemp(prefix="tv_doc_media_")
    settings.MEDIA_ROOT = media_root
    settings.DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    return media_root


def _security_data(seed):
    return {
        "sanitized_filename": f"{seed}.doc",
        "secure_filename": f"{seed}_secure.doc",
        "sha256": seed.ljust(64, "0")[:64],
        "mime_type": "application/msword",
        "scan_status": "PASSED",
        "scan_timestamp": None,
    }


def _text_result():
    return SimpleNamespace(returncode=0, stdout=DOC_TEXT.encode("utf-8"), stderr=b"")


def _exe(cmd):
    return os.path.basename(cmd[0]).lower()


# --------------------------------------------------------------------------- #
# extract_text_from_doc converter chain (unit, converter binary stubbed)
# --------------------------------------------------------------------------- #

def test_extract_text_from_doc_uses_antiword_first():
    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append(_exe(cmd))
        if "antiword" in _exe(cmd):
            return _text_result()
        raise AssertionError(f"unexpected converter after antiword: {cmd}")

    with patch("utils.preview.subprocess.run", side_effect=_fake_run):
        text = extract_text_from_doc(DOC_BYTES)

    assert text == DOC_TEXT
    assert calls and "antiword" in calls[0]
    assert not any("catdoc" in c or "soffice" in c or "libreoffice" in c for c in calls)


def test_extract_text_from_doc_falls_back_to_catdoc():
    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append(_exe(cmd))
        if "antiword" in _exe(cmd):
            raise FileNotFoundError(_exe(cmd))
        if "catdoc" in _exe(cmd):
            return _text_result()
        raise AssertionError(f"unexpected converter: {cmd}")

    with patch("utils.preview.subprocess.run", side_effect=_fake_run):
        text = extract_text_from_doc(DOC_BYTES)

    assert text == DOC_TEXT
    assert any("catdoc" in c for c in calls)


def test_extract_text_from_doc_returns_empty_when_all_converters_fail():
    def _fake_run(cmd, **kwargs):
        raise FileNotFoundError(_exe(cmd))

    with patch("utils.preview.subprocess.run", side_effect=_fake_run):
        text = extract_text_from_doc(DOC_BYTES)

    assert text == ""


def test_extract_text_from_doc_strips_binary_garbage():
    garbage = b"John Doe\x00\x01\x02\xff\xfeemail@example.com"

    def _fake_run(cmd, **kwargs):
        if "antiword" in _exe(cmd):
            return SimpleNamespace(returncode=0, stdout=garbage, stderr=b"")
        raise AssertionError(f"unexpected converter: {cmd}")

    with patch("utils.preview.subprocess.run", side_effect=_fake_run):
        text = extract_text_from_doc(DOC_BYTES)

    assert "\x00" not in text and "\xff" not in text
    assert "John Doe" in text
    assert "email@example.com" in text


# --------------------------------------------------------------------------- #
# run_ocr_pipeline DOC branch (unit)
# --------------------------------------------------------------------------- #

def test_run_ocr_pipeline_doc_returns_clean_text():
    with patch("utils.preview.subprocess.run", return_value=_text_result()):
        res = ResumeIntelligenceService.run_ocr_pipeline(DOC_BYTES, "resume.doc")

    assert res["text"] == DOC_TEXT
    assert "Parse Error" not in res["text"]
    assert res["engine"] == "doc-text-extractor"
    assert res["resume_type"] == "EDITABLE_DOC"


def test_run_ocr_pipeline_doc_failure_returns_empty_not_error_string():
    def _fake_run(cmd, **kwargs):
        raise FileNotFoundError(_exe(cmd))

    with patch("utils.preview.subprocess.run", side_effect=_fake_run):
        res = ResumeIntelligenceService.run_ocr_pipeline(DOC_BYTES, "resume.doc")

    assert res["text"] == ""
    assert res["engine"] == "doc-conversion-failed"
    assert res["confidence"] == 0.0


# --------------------------------------------------------------------------- #
# REAL .doc conversion (LibreOffice/antiword actually executed)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _converter_available(), reason="no .doc converter installed")
def test_extract_text_from_doc_real_doc_file():
    text = extract_text_from_doc(_load_real_doc())

    assert text
    assert "Amit Sharma" in text
    assert "amit.sharma@example.com" in text
    assert "TechCorp" in text
    assert "SoftLabs" in text
    assert "IIT Delhi" in text
    assert "Python" in text
    # Never an error string / binary blob.
    assert "Parse Error" not in text
    assert "\x00" not in text


# --------------------------------------------------------------------------- #
# End-to-end with a REAL .doc file (real conversion, real mapping, real DB)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _converter_available(), reason="no .doc converter installed")
@pytest.mark.django_db
def test_real_doc_resume_parses_candidate(local_media):
    captured = {}

    def _fake_parseora(file_bytes, filename, raw_text=None, timeout=None):
        captured["file_bytes"] = file_bytes
        captured["filename"] = filename
        captured["raw_text"] = raw_text
        return PARSEORA_RESUME_JSON

    with patch(
        "services.parseora_service.ParseoraService.parse_resume",
        side_effect=_fake_parseora,
    ), patch(
        "apps.candidates.utils.extract_profile_photo",
        return_value=(None, None),
    ), patch(
        "services.resume_storage_service.upload_and_verify_resume",
        return_value=("resumes/test.doc", b"x"),
    ), patch(
        "services.resume_storage_service.copy_and_verify_original_resume",
        return_value="resumes/original/test.doc",
    ), patch(
        "services.candidate_matching_service.CandidateMatchingService.update_ats_scores",
        return_value=None,
    ), patch(
        "services.candidate_tagging_service.CandidateTaggingService.tag_candidate_profile",
        return_value=None,
    ):
        profile, status = process_resume_file(
            io.BytesIO(_load_real_doc()),
            "amit_resume.doc",
            security_data=_security_data("real_doc"),
        )

    assert status == "SUCCESS"
    assert profile is not None

    # Parseora received clean text (never the binary .doc bytes).
    assert captured.get("filename") == "extracted.txt"
    assert isinstance(captured.get("file_bytes"), bytes)
    text_sent = captured.get("file_bytes", b"").decode("utf-8", errors="ignore")
    assert "Amit Sharma" in text_sent
    assert captured.get("raw_text")
    assert "TechCorp" in captured.get("raw_text", "")
    assert captured.get("file_bytes") != _load_real_doc()

    # Name & contact
    assert profile.full_name == "Amit Sharma"
    assert profile.user.email == "amit.sharma@example.com"
    assert profile.user.phone_number == "9012345678"

    # Work experience
    exps = list(profile.experiences.all())
    assert {(e.company_name.lower(), e.designation.lower()) for e in exps} == {
        ("techcorp", "senior engineer"),
        ("softlabs", "engineer"),
    }

    # Education
    edus = list(profile.educations.all())
    assert len(edus) == 1
    assert edus[0].institution.lower() == "iit delhi"
    assert edus[0].degree == "B.Tech"
    assert edus[0].field_of_study == "Computer Science"

    # Skills
    skill_names = {s.skill_name.lower() for s in profile.skills.all()}
    assert {"python", "django", "sql"}.issubset(skill_names)

    # Clean extracted text persisted (never binary / error string).
    assert "Parse Error" not in profile.raw_resume_text
    assert "amit.sharma@example.com" in profile.raw_resume_text


# --------------------------------------------------------------------------- #
# Conversion failure -> explicit parse failure (never an empty candidate)
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_doc_conversion_failure_is_not_saved_and_parseora_not_called(local_media):
    parseora_called = []

    def _fake_parseora(*args, **kwargs):
        parseora_called.append(True)
        return PARSEORA_RESUME_JSON

    def _converter_fails(cmd, **kwargs):
        raise FileNotFoundError(_exe(cmd))

    with patch("utils.preview.subprocess.run", side_effect=_converter_fails), patch(
        "services.parseora_service.ParseoraService.parse_resume",
        side_effect=_fake_parseora,
    ), patch(
        "apps.candidates.utils.extract_profile_photo",
        return_value=(None, None),
    ), patch(
        "services.resume_storage_service.upload_and_verify_resume",
        return_value=("resumes/test.doc", b"x"),
    ), patch(
        "services.resume_storage_service.copy_and_verify_original_resume",
        return_value="resumes/original/test.doc",
    ), patch(
        "services.candidate_matching_service.CandidateMatchingService.update_ats_scores",
        return_value=None,
    ), patch(
        "services.candidate_tagging_service.CandidateTaggingService.tag_candidate_profile",
        return_value=None,
    ):
        profile, status = process_resume_file(
            io.BytesIO(DOC_BYTES),
            "corrupt_resume.doc",
            security_data=_security_data("corrupt_doc"),
        )

    assert status != "SUCCESS"
    assert profile is None
    # Binary .doc must never reach Parseora when extraction failed.
    assert parseora_called == []
