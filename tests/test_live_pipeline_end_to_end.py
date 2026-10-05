"""
End-to-end tests that trace a REAL PDF resume through the LIVE pipeline:

    FILE -> extraction (real PyMuPDF) -> Parseora (mocked HTTP, real mapping)
         -> validation -> CandidateRecord -> final candidate profile

These verify the FINAL database record, not intermediate AI JSON.
"""

import io
import os
import tempfile
from unittest.mock import patch

import pytest

from apps.candidates.utils import process_resume_file
from services.parseora_service import ParseoraService


def _build_pdf(text):
    """Create a real text PDF with PyMuPDF (no OCR needed)."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 72
    for line in text.split("\n"):
        page.insert_text((72, y), line, fontsize=11, fontname="helv")
        y += 16
    data = doc.tobytes()
    doc.close()
    return data


RESUME_TEXT = (
    "Parul Rai\n"
    "Digital Marketing Professional\n"
    "parul.rai@example.com\n"
    "+91 98765 43210\n"
    "\n"
    "Objective:\n"
    "To enhance my professional skills and contribute to organizational growth "
    "through data-driven marketing.\n"
    "\n"
    "Address:\n"
    "C/O Prabhu Nath Singh, Balughat, Muzaffarpur, 842001 (Bihar)\n"
    "\n"
    "Work Experience:\n"
    "Digital Marketing Executive, Advertech Solutions (2021 - Present)\n"
    "Marketing Associate, BrandWorks (2019 - 2021)\n"
    "\n"
    "Skills:\n"
    "Google Ads, SEO, Digital Marketing, Social Media Campaigns\n"
    "\n"
    "Education:\n"
    "MBA Marketing, Pune University (2019)\n"
)

# A deliberately bad Parseora response: wrong name ("Google Ads"), address in
# summary, and a fake job ("Social Media Campaigns"). The pipeline must correct
# all of these before persisting.
BAD_PARSEORA_JSON = {
    "request_id": "req_live_001",
    "candidate": {
        "name": "Google Ads",
        "email": "parul.rai@example.com",
        "phone": "+91 98765 43210",
        "summary": "C/O Prabhu Nath Singh, Balughat, Muzaffarpur, 842001 (Bihar)",
        "career_objective": "To enhance my professional skills and contribute to organizational growth through data-driven marketing.",
    },
    "skills": {"technical_skills": ["Google Ads", "SEO", "Digital Marketing", "Social Media Campaigns"]},
    "experience": [
        {"job_title": "Digital Marketing Executive", "company_name": "Advertech Solutions",
         "start_date": "2021-01-01", "end_date": "Present",
         "responsibilities": ["Managed Google Ads campaigns"]},
        {"job_title": "Marketing Associate", "company_name": "BrandWorks",
         "start_date": "2019-01-01", "end_date": "2021-01-01"},
        {"job_title": "Social Media Campaigns"},
    ],
    "education": [
        {"degree": "MBA", "college": "Pune University", "field_of_study": "Marketing", "end_year": "2019"},
    ],
}


@pytest.fixture
def local_media(settings):
    media_root = tempfile.mkdtemp(prefix="tv_live_media_")
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


@pytest.mark.django_db
def test_real_pdf_live_pipeline_final_record(local_media):
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
            "parul_resume.pdf",
            security_data=_security_data("live_parul"),
        )

    assert status == "SUCCESS"
    assert profile is not None

    # Candidate name is a real person name, NOT the skill "Google Ads".
    assert profile.full_name != "Google Ads"
    assert profile.full_name == "Parul Rai"

    # Summary is the Objective, NOT the address.
    assert profile.summary.startswith("To enhance my professional skills")
    assert "C/O Prabhu Nath Singh" not in profile.summary
    assert "842001" not in profile.summary

    # Experience: only real jobs survive; "Social Media Campaigns" is NOT a job.
    exps = list(profile.experiences.all())
    assert {(e.company_name.lower(), e.designation.lower()) for e in exps} == {
        ("advertech solutions", "digital marketing executive"),
        ("brandworks", "marketing associate"),
    }

    # Skills remain intact and separate from the name.
    skill_names = {s.skill_name.lower() for s in profile.skills.all()}
    assert "google ads" in skill_names
    assert "seo" in skill_names
    assert "digital marketing" in skill_names

    # Education preserved.
    edus = list(profile.educations.all())
    assert len(edus) == 1
    assert edus[0].degree == "MBA"
    assert edus[0].institution == "Pune University"


def test_map_rejects_fake_job_and_bad_name_and_address():
    mapped = ParseoraService.map_response_to_talentvault(BAD_PARSEORA_JSON)

    # Name not the skill.
    assert mapped["personal_info"]["name"] == ""
    # Summary is the objective, not the address.
    assert mapped["summary"].startswith("To enhance my professional skills")
    # Fake job rejected.
    assert len(mapped["experience"]) == 2
    assert all("Social Media Campaigns" not in (e["company"], e["designation"]) for e in mapped["experience"])
    # Skills intact.
    skill_set = {s.lower() for s in mapped["skills"]}
    assert {"google ads", "seo", "digital marketing"}.issubset(skill_set)
