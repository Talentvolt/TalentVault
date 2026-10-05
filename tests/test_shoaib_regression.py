"""
Regression for the real production failure on a Shoaib Siddiqui-style resume.

The parser previously produced:
    name = "Noida India", designation = "Professional / Confidential",
    work_experience = 0, education polluted with experience content.

These tests verify the GENERIC fixes (location-rejecting name validation,
section-aware experience/education recovery, raw-text reconciliation) against
the FINAL CandidateRecord.
"""

import io
import os
import tempfile
from unittest.mock import patch

import pytest

from apps.candidates.utils import process_resume_file
from services.parseora_service import ParseoraService
from services.resume_intelligence import ResumeIntelligenceService

RESUME_TEXT = (
    "SHOAIB SIDDIQUI\n"
    "Noida, India 201304\n"
    "9760686604\n"
    "Siddiquishoaib078@gmail.com\n"
    "linkedin.com/in/shoaib-siddiqui\n"
    "\n"
    "Professional Summary\n"
    "Resourceful Account Manager with excellent client oversight and account management experience.\n"
    "\n"
    "Skills\n"
    "Lead Generation\nCRM Management\nCold Calling\nRelationship Building\n"
    "Data Management\nTime Management\nAccount Management\nCustomer Need Analysis\n"
    "Product Demos\nUpselling and Cross-Selling\nB2B Sales\nPower BI\nMS Office\n"
    "\n"
    "Experience\n"
    "Account Manager (ISR)\nDenave India Pvt Ltd, Noida\n12/2024 - Current\n"
    "\n"
    "Inside Sales Executive\nJinactus Consulting Pvt Ltd\n06/2023 - 11/2024\n"
    "\n"
    "Business Development Executive (Internship)\nNavkar DreamSoft, Pune\n05/2022 - 07/2022\n"
    "\n"
    "Business Development Executive (Internship)\n99 App Technologies\n12/2021 - 01/2022\n"
    "\n"
    "Business Development Executive\nByju's\n12/2020 - 04/2021\n"
    "\n"
    "Education\n"
    "SRM Institute of Science and Technology\nB.Tech, IT, 05/2020\n"
    "\n"
    "Pune Institute of Business Management, Pune\nMBA, Marketing and Operations, 04/2023\n"
    "\n"
    "Certificates and Achievements\n"
    "Power BI / MS Office / Google Ads\n"
    "Sales Order Management and Supply Chain Management\n"
    "DIGILYTICS\n"
    "SRMIST awards\n"
    "Rajya Khel award\n"
)

# A deliberately bad Parseora response: location as name, empty experience,
# experience content injected into education.
BAD_PARSEORA_JSON = {
    "request_id": "req_shoaib_bad",
    "candidate": {
        "name": "Noida India",
        "email": "Siddiquishoaib078@gmail.com",
        "phone": "+91 9760686604",
        "summary": "",
        "current_designation": "Professional",
    },
    "skills": {"technical_skills": ["Lead Generation", "CRM Management", "MS Office"]},
    "experience": [],
    "education": [
        {"degree": "Account Manager (ISR)", "college": "Denave India Pvt Ltd",
         "field_of_study": "12/2024 - Current"},
    ],
}


def _build_pdf(text):
    import fitz
    doc = fitz.open()
    y = 72
    page = doc.new_page(width=612, height=792)
    for line in text.split("\n"):
        if y > 750:
            page = doc.new_page(width=612, height=792)
            y = 72
        page.insert_text((72, y), line, fontsize=11, fontname="helv")
        y += 16
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def local_media(settings):
    media_root = tempfile.mkdtemp(prefix="tv_shoaib_media_")
    settings.MEDIA_ROOT = media_root
    settings.DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    return media_root


def _security_data(seed):
    return {
        "sanitized_filename": f"{seed}.pdf",
        "secure_filename": f"{seed}_secure.pdf",
        "sha256": seed.ljust(64, "0")[:64],
        "mime_type": "application/pdf",
        "scan_status": "PASSED",
        "scan_timestamp": None,
    }


def test_nlp_parses_shoaib_resume_correctly():
    p = ResumeIntelligenceService.parse_resume_nlp(RESUME_TEXT)

    assert p["personal_info"]["name"] == "Shoaib Siddiqui"
    assert p["summary"].startswith("Resourceful Account Manager")

    companies = [e["company"] for e in p["experience"]]
    assert len(companies) == 5
    joined = " | ".join(companies)
    assert "Denave India Pvt Ltd" in joined
    assert "Jinactus Consulting Pvt Ltd" in joined
    assert "Navkar DreamSoft" in joined
    assert "99 App Technologies" in joined
    assert "Byju's" in joined

    institutions = [e["institution"] for e in p["education"]]
    assert len(institutions) == 2
    joined_inst = " | ".join(institutions)
    assert "SRM Institute of Science and Technology" in joined_inst
    assert "Pune Institute of Business Management" in joined_inst


def test_name_location_rejected():
    assert ResumeIntelligenceService.is_non_person_name("Noida India") is True
    assert ResumeIntelligenceService.is_valid_name("Noida India") is False
    assert ParseoraService._is_plausible_person_name("Noida India") is False
    assert ResumeIntelligenceService.is_valid_name("Shoaib Siddiqui") is True


@pytest.mark.django_db
def test_shoaib_final_candidate_record(local_media):
    pdf_bytes = _build_pdf(RESUME_TEXT)

    with patch(
        "services.parseora_service.ParseoraService.parse_resume",
        return_value=BAD_PARSEORA_JSON,
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
        profile, status = process_resume_file(
            io.BytesIO(pdf_bytes),
            "Shoaib_Siddiqui_-_Copy.pdf",
            security_data=_security_data("shoaib_live"),
        )

    assert status == "SUCCESS"
    assert profile is not None

    # Name is the real person, never the location.
    assert profile.full_name == "Shoaib Siddiqui"
    assert profile.full_name != "Noida India"

    # Designation is NOT the "Professional" placeholder.
    assert profile.current_designation != "Professional"

    # Summary contains the real Account Manager summary.
    assert "Resourceful Account Manager" in (profile.summary or "")

    # 5 real employment records, never 0.
    exps = list(profile.experiences.all())
    assert len(exps) == 5
    joined_companies = " | ".join(e.company_name for e in exps)
    for expected in ["Denave India Pvt Ltd", "Jinactus Consulting Pvt Ltd",
                     "Navkar DreamSoft", "99 App Technologies", "Byju's"]:
        assert expected in joined_companies

    # 2 education records, never polluted with experience content.
    edus = list(profile.educations.all())
    assert len(edus) == 2
    joined_inst = " | ".join(e.institution for e in edus)
    assert "SRM Institute of Science and Technology" in joined_inst
    assert "Pune Institute of Business Management" in joined_inst
    # Experience content must not leak into education.
    for ed in edus:
        blob = f"{ed.institution} {ed.degree} {ed.field_of_study or ''}"
        assert "Account Manager" not in blob
        assert "Denave India Pvt Ltd" not in blob
