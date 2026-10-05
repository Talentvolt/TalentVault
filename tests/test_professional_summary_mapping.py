"""
Regression tests for Candidate Professional Summary mapping.

The Professional Summary must come from a genuine career objective /
professional summary field -- NEVER from address, location, phone, email or
contact fields. These tests lock in:

  A) career objective / professional summary is displayed as the summary
  B) an address is never displayed as the summary
  C) fallback works when career objective is absent (summary / objective /
     generated-from-professional-data)
  D) existing candidate detail pages continue working
"""

import io
import json
import os
import tempfile
from unittest.mock import patch

import pytest

from apps.candidates.utils import process_resume_file
from services.parseora_service import ParseoraService

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

CAREER_OBJECTIVE = (
    "Experienced sales professional with strong exposure to two-wheeler "
    "aftermarket and light-item sales across Bihar, Nepal and Uttar Pradesh. "
    "Seeking a Regional Sales Manager / Area Sales Manager role."
)
ADDRESS = "C/O Prabhu Nath Singh, Balughat, Muzaffarpur, 842001 (Bihar)"


def _res(candidate_extra=None, **kwargs):
    candidate = {
        "name": "Ravi Kumar",
        "email": "ravi.kumar@example.com",
        "phone": "+91 90123 45678",
        "current_designation": "Regional Sales Manager",
        "current_company": "TechCorp",
        "total_experience_years": 8.0,
        "address": ADDRESS,
        "summary": {"value": ADDRESS},
        "objective": {"value": ""},
    }
    if candidate_extra:
        candidate.update(candidate_extra)
    payload = {
        "candidate": candidate,
        "skills": {"technical_skills": ["Sales", "Distribution", "Negotiation"]},
        "experience": [
            {"company_name": "TechCorp", "job_title": "Regional Sales Manager",
             "start_date": "2019-01-01", "end_date": "Present"},
        ],
        "education": [
            {"degree": "B.Com", "college": "Delhi University",
             "field_of_study": "Commerce", "end_year": "2010"},
        ],
    }
    payload.update(kwargs)
    return payload


# --------------------------------------------------------------------------- #
# A) career objective is displayed as Professional Summary
# --------------------------------------------------------------------------- #

def test_career_objective_wins_over_address_summary():
    res = _res(candidate_extra={"career_objective": {"value": CAREER_OBJECTIVE}})
    mapped = ParseoraService.map_response_to_talentvault(res)
    assert mapped["summary"] == CAREER_OBJECTIVE
    assert "C/O" not in mapped["summary"]


def test_professional_summary_field_wins_over_address_summary():
    res = _res(candidate_extra={"professional_summary": {"value": CAREER_OBJECTIVE}})
    mapped = ParseoraService.map_response_to_talentvault(res)
    assert mapped["summary"] == CAREER_OBJECTIVE


def test_raw_parsed_data_career_objective_used():
    res = _res()
    res["raw_parsed_data"] = {"career_objective": CAREER_OBJECTIVE}
    mapped = ParseoraService.map_response_to_talentvault(res)
    assert mapped["summary"] == CAREER_OBJECTIVE


def test_raw_parsed_data_summary_used():
    res = _res(candidate_extra={"summary": {"value": ADDRESS}})
    res["raw_parsed_data"] = {"summary": CAREER_OBJECTIVE}
    mapped = ParseoraService.map_response_to_talentvault(res)
    assert mapped["summary"] == CAREER_OBJECTIVE


# --------------------------------------------------------------------------- #
# B) address is NOT displayed as Professional Summary
# --------------------------------------------------------------------------- #

def test_address_only_is_rejected_as_summary():
    res = _res()  # summary == ADDRESS, no career objective
    mapped = ParseoraService.map_response_to_talentvault(res)
    assert "C/O" not in mapped["summary"]
    assert "842001" not in mapped["summary"]
    assert "Muzaffarpur" not in mapped["summary"]


# --------------------------------------------------------------------------- #
# C) fallback works when career objective is absent
# --------------------------------------------------------------------------- #

def test_summary_field_used_when_no_objective():
    res = _res(candidate_extra={"summary": {"value": "A genuine summary text."},
                                "objective": {"value": ""}})
    mapped = ParseoraService.map_response_to_talentvault(res)
    assert mapped["summary"] == "A genuine summary text."


def test_objective_field_used_when_summary_absent():
    res = _res(candidate_extra={"summary": {"value": ""},
                                "objective": {"value": "To grow in a sales role."}})
    mapped = ParseoraService.map_response_to_talentvault(res)
    assert mapped["summary"] == "To grow in a sales role."


def test_no_summary_is_not_fabricated():
    res = _res(candidate_extra={"summary": {"value": ""}, "objective": {"value": ""}})
    mapped = ParseoraService.map_response_to_talentvault(res)
    # Missing summary stays empty (NULL), never invented from professional data.
    assert mapped["summary"] == ""


# --------------------------------------------------------------------------- #
# D) existing candidate pages continue working
# --------------------------------------------------------------------------- #

@pytest.fixture
def local_media(settings):
    media_root = tempfile.mkdtemp(prefix="tv_summary_media_")
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
def test_candidate_detail_renders_objective_not_address(local_media):
    from django.test import Client
    from django.urls import reverse

    from apps.accounts.models import User

    res = _res(candidate_extra={"career_objective": {"value": CAREER_OBJECTIVE}})

    with patch("services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline",
               return_value={"text": CAREER_OBJECTIVE, "engine": "test",
                             "confidence": 99.0, "resume_type": "EDITABLE_PDF",
                             "largest_bold_name": None}), patch(
        "apps.candidates.utils.parse_resume_via_parseora",
        return_value=ParseoraService.map_response_to_talentvault(res),
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
            io.BytesIO(b"%PDF-1.4 test"),
            "ravi_resume.pdf",
            security_data=_security_data("summary_regression"),
        )

    assert status == "SUCCESS"
    assert profile is not None
    assert profile.summary == CAREER_OBJECTIVE
    assert "C/O" not in profile.summary

    admin = User.objects.create_superuser(
        email="summary_admin@talentvault.in",
        password="Password123!",
        role=User.Role.SUPER_ADMIN,
    )
    client = Client()
    client.force_login(admin)
    response = client.get(
        reverse("frontend:candidate_detail", kwargs={"pk": profile.pk})
    )
    assert response.status_code == 200
    html = response.content.decode("utf-8")

    # Isolate the Professional Summary card (unique header icon -> next card).
    start = html.index("bi-file-text")
    end = html.index("Work Experience Card")
    summary_section = html[start:end]

    # The real objective is displayed as the Professional Summary.
    assert "Experienced sales professional" in summary_section
    # The postal address is never shown inside the Professional Summary card.
    assert "C/O Prabhu Nath Singh" not in summary_section
