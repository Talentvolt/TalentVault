"""
End-to-end regression tests for the TalentVault <- Parseora ingestion pipeline.

These tests lock in the permanent fixes:

* Parseora structured output is the PRIMARY source of truth.
* A failure inside ai_improve_resume_data() must never discard the successful
  Parseora result nor trigger the destructive legacy parser fallback.
* Raw bytes (photo/image/PDF) must never break JSON serialization.
* Names/contacts/summary/experience/education/skills/photo map 1:1 into the
  correct TalentVault CRM fields without cross-contamination or fabrication.
"""

import base64
import io
import json
import os
import tempfile
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.accounts.models import User
from apps.candidates.models import (
    CandidateProfile,
    CandidateSkill,
    Education,
    Experience,
)
from apps.candidates.utils import process_resume_file
from services.parseora_service import ParseoraService
from services.resume_intelligence import ResumeIntelligenceService, make_json_safe

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
PHOTO_FIXTURE = os.path.join(FIXTURES_DIR, "parseora_candidate_with_photo.json")
NO_PHOTO_FIXTURE = os.path.join(FIXTURES_DIR, "sreeharsha_parseora.json")


def _load_fixture(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _security_data(seed):
    return {
        "sanitized_filename": f"{seed}.pdf",
        "secure_filename": f"{seed}_secure.pdf",
        "sha256": seed.ljust(64, "0")[:64],
        "mime_type": "application/pdf",
        "scan_status": "PASSED",
        "scan_timestamp": None,
    }


@pytest.fixture
def local_media(settings):
    media_root = tempfile.mkdtemp(prefix="tv_media_")
    settings.MEDIA_ROOT = media_root
    settings.DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    return media_root


def _run_pipeline(seed, mapped_or_none, photo_fixture_bytes=None, ai_improve=None):
    """Run process_resume_file with Parseora + OCR + storage + side effects mocked."""
    ocr_result = {
        "text": "",
        "engine": "test",
        "confidence": 99.0,
        "resume_type": "EDITABLE_PDF",
        "largest_bold_name": None,
    }
    with patch(
        "services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline",
        return_value=ocr_result,
    ), patch(
        "apps.candidates.utils.parse_resume_via_parseora",
        return_value=mapped_or_none,
    ), patch(
        "apps.candidates.utils.extract_profile_photo",
        return_value=(photo_fixture_bytes, "png") if photo_fixture_bytes else (None, None),
    ), patch(
        "services.resume_storage_service.upload_and_verify_resume",
        return_value=(f"resumes/{seed}.pdf", b"x"),
    ), patch(
        "services.resume_storage_service.copy_and_verify_original_resume",
        return_value=f"resumes/original/{seed}.pdf",
    ), patch(
        "services.candidate_matching_service.CandidateMatchingService.update_ats_scores",
        return_value=None,
    ), patch(
        "services.candidate_tagging_service.CandidateTaggingService.tag_candidate_profile",
        return_value=None,
    ):
        if ai_improve is not None:
            with patch.object(
                ResumeIntelligenceService, "ai_improve_resume_data", ai_improve
            ):
                return process_resume_file(
                    io.BytesIO(b"%PDF-1.4 test"),
                    f"{seed}.pdf",
                    security_data=_security_data(seed),
                )
        return process_resume_file(
            io.BytesIO(b"%PDF-1.4 test"),
            f"{seed}.pdf",
            security_data=_security_data(seed),
        )


# --------------------------------------------------------------------------- #
# A. Safe JSON / bytes handling
# --------------------------------------------------------------------------- #

def test_make_json_safe_never_returns_raw_bytes():
    payload = {
        "personal_info": {"name": "Jane Doe"},
        "photo_bytes": b"\x89PNG\r\n\x1a\n\x00\x01\x02",
        "nested": [{"image_bytes": bytearray(b"binary"), "label": "x"}],
    }
    safe = make_json_safe(payload)
    # Must be JSON serializable (no bytes anywhere).
    serialized = json.dumps(safe)
    assert "photo_bytes" in serialized
    assert isinstance(safe["photo_bytes"], dict)
    assert safe["photo_bytes"]["serialized"] is False
    assert safe["photo_bytes"]["byte_length"] == len(b"\x89PNG\r\n\x1a\n\x00\x01\x02")
    assert safe["nested"][0]["image_bytes"]["serialized"] is False


def test_ai_improve_resume_data_handles_photo_bytes():
    data = {
        "personal_info": {"name": "jane doe", "email": "jane@mailhost.test"},
        "summary": "Analyst with experience.",
        "skills": ["python", "Python", "sql"],
        "experience": [],
        "education": [],
        "photo_bytes": b"\xff\xd8\xff\xe0raw-jpeg-bytes",
        "photo_info": {"available": True, "page": 1, "source": "parseora"},
    }
    improved = ResumeIntelligenceService.ai_improve_resume_data(data)
    assert improved["personal_info"]["name"] == "Jane Doe"
    assert improved["skills"] == ["Python", "Sql"]
    # Source summary preserved (not regenerated).
    assert improved["summary"] == "Analyst with experience."


def test_ai_improve_does_not_fabricate_summary():
    data = {
        "personal_info": {"name": "Jane Doe", "total_experience": 3},
        "summary": "",
        "skills": ["Python"],
        "experience": [],
        "education": [],
    }
    improved = ResumeIntelligenceService.ai_improve_resume_data(data)
    assert improved["summary"] == ""


# --------------------------------------------------------------------------- #
# K/O. End-to-end contract: Parseora -> TalentVault -> DB
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_parseora_structured_result_maps_to_database_fields(local_media):
    res_json = _load_fixture(PHOTO_FIXTURE)
    mapped = ParseoraService.map_response_to_talentvault(res_json)

    profile, status = _run_pipeline("contract001", mapped)
    assert status == "SUCCESS"

    # Name / contact
    assert profile.full_name == "Priya Nair"
    assert profile.user.email == "priya.nair@mailhost.test"
    assert profile.user.phone_number == "9012345678"

    # Summary only from the source summary
    assert profile.summary.startswith("Data analyst with 4 years")
    assert "@" not in profile.summary

    # Experience
    exps = list(profile.experiences.all())
    pairs = {(e.company_name, e.designation) for e in exps}
    assert ("Northwind Analytics Pvt Ltd", "Data Analyst") in pairs
    assert ("Bluepeak Services", "Junior Analyst") in pairs
    for e in exps:
        assert "@" not in e.company_name
        assert "@" not in e.designation

    # Education
    edus = list(profile.educations.all())
    assert len(edus) == 1
    assert edus[0].degree == "B.Sc"
    assert edus[0].institution == "Savitribai Phule University"
    assert edus[0].field_of_study == "Statistics"
    assert "@" not in edus[0].institution

    # Skills
    skill_names = {s.skill_name.lower() for s in profile.skills.all()}
    assert {"sql", "python", "power bi"}.issubset(skill_names)
    assert all("." not in s for s in skill_names)

    # Photo persisted to CandidateProfile.profile_photo
    assert profile.has_profile_photo is True
    assert profile.profile_photo and profile.profile_photo.name


@pytest.mark.django_db
def test_no_field_crosses_into_unrelated_crm_field(local_media):
    res_json = _load_fixture(PHOTO_FIXTURE)
    mapped = ParseoraService.map_response_to_talentvault(res_json)
    profile, status = _run_pipeline("contract002", mapped)
    assert status == "SUCCESS"

    # Contact data must not leak into experience/education/skills.
    for e in profile.experiences.all():
        blob = f"{e.company_name} {e.designation} {e.description}"
        assert "priya.nair@mailhost.test" not in blob
        assert "9012345678" not in blob
    for ed in profile.educations.all():
        blob = f"{ed.institution} {ed.degree} {ed.field_of_study or ''}"
        assert "@" not in blob
        assert "Northwind" not in blob
    for sk in profile.skills.all():
        assert len(sk.skill_name.split()) <= 6


# --------------------------------------------------------------------------- #
# L. Failure safety: ai_improve raises -> Parseora result preserved
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_ai_improve_failure_keeps_parseora_result(local_media):
    res_json = _load_fixture(PHOTO_FIXTURE)
    mapped = ParseoraService.map_response_to_talentvault(res_json)

    def _boom(*args, **kwargs):
        raise TypeError("Object of type bytes is not JSON serializable")

    profile, status = _run_pipeline("failure001", mapped, ai_improve=_boom)
    assert status == "SUCCESS"

    # Name, contact, summary, experience, education, skills all preserved.
    assert profile.full_name == "Priya Nair"
    assert profile.user.email == "priya.nair@mailhost.test"
    assert profile.user.phone_number == "9012345678"
    assert profile.summary.startswith("Data analyst with 4 years")
    assert profile.experiences.count() == 2
    assert profile.educations.count() == 1
    assert profile.skills.count() >= 4
    # Photo survives the AI-improvement failure.
    assert profile.has_profile_photo is True


@pytest.mark.django_db
def test_ai_improve_failure_does_not_invoke_legacy_parser(local_media):
    res_json = _load_fixture(PHOTO_FIXTURE)
    mapped = ParseoraService.map_response_to_talentvault(res_json)

    def _boom(*args, **kwargs):
        raise RuntimeError("ai improve exploded")

    with patch(
        "services.resume_intelligence.ResumeIntelligenceService.parse_resume_nlp"
    ) as legacy_parser:
        profile, status = _run_pipeline("failure002", mapped, ai_improve=_boom)
        assert status == "SUCCESS"
        legacy_parser.assert_not_called()
    assert profile.full_name == "Priya Nair"


# --------------------------------------------------------------------------- #
# M. Photo tests
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_cv_with_genuine_photo_populates_profile_photo(local_media):
    res_json = _load_fixture(PHOTO_FIXTURE)
    mapped = ParseoraService.map_response_to_talentvault(res_json)
    assert mapped["photo_bytes"], "fixture must provide a genuine photo"

    profile, status = _run_pipeline("photo_yes", mapped)
    assert status == "SUCCESS"
    assert profile.profile_photo and profile.profile_photo.name
    assert profile.has_profile_photo is True


@pytest.mark.django_db
def test_cv_without_photo_keeps_profile_photo_null(local_media):
    res_json = _load_fixture(NO_PHOTO_FIXTURE)
    mapped = ParseoraService.map_response_to_talentvault(res_json)
    assert not mapped.get("photo_bytes")

    profile, status = _run_pipeline("photo_no", mapped)
    assert status == "SUCCESS"
    assert not profile.profile_photo
    assert profile.has_profile_photo is False


# --------------------------------------------------------------------------- #
# D. No synthetic contacts
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_missing_contact_is_not_fabricated(local_media):
    res_json = {
        "request_id": "req_no_contact",
        "candidate": {
            "name": "Rahul Verma",
            "summary": "Backend engineer.",
        },
        "skills": {"technical_skills": ["Java"]},
        "experience": [],
        "education": [],
    }
    mapped = ParseoraService.map_response_to_talentvault(res_json)

    profile, status = _run_pipeline("nocontact", mapped)
    assert status == "SUCCESS"
    assert profile.full_name == "Rahul Verma"
    # The candidate contact email must not be a fabricated placeholder...
    assert profile.contact_email == ""
    # ...and the persisted payload must reflect the empty contact.
    assert profile.parsed_json["personal_info"]["email"] == ""
    # The internal login identifier is never surfaced as contact.
    assert profile.user.email != ""
    assert profile.contact_email != profile.user.email


# --------------------------------------------------------------------------- #
# C. Placeholder / garbage names are rejected
# --------------------------------------------------------------------------- #

def test_district_label_is_not_a_valid_name():
    res_json = {
        "request_id": "req_bad_name",
        "candidate": {
            "name": "District -",
            "email": "someone@mailhost.test",
        },
        "skills": {},
        "experience": [],
        "education": [],
    }
    mapped = ParseoraService.map_response_to_talentvault(res_json)
    # The mapper must not silently keep an address label as the candidate name.
    assert mapped["personal_info"]["name"] == ""


def test_parseora_missing_name_is_empty_not_placeholder():
    res_json = {
        "request_id": "req_missing_name",
        "candidate": {"email": "someone@mailhost.test"},
        "skills": {},
        "experience": [],
        "education": [],
    }
    mapped = ParseoraService.map_response_to_talentvault(res_json)
    assert mapped["personal_info"]["name"] == ""


# --------------------------------------------------------------------------- #
# O. Candidate detail UI reflects the persisted structured values
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_candidate_detail_ui_matches_persisted_values(local_media):
    from django.test import Client
    from django.urls import reverse

    res_json = _load_fixture(PHOTO_FIXTURE)
    mapped = ParseoraService.map_response_to_talentvault(res_json)
    profile, status = _run_pipeline("ui001", mapped)
    assert status == "SUCCESS"

    admin = User.objects.create_superuser(
        email="pipeline_admin@talentvault.in",
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

    # Name, contact, summary, experience, education, skills, photo all rendered.
    assert "Priya Nair" in html
    assert "priya.nair@mailhost.test" in html
    assert "Data analyst with 4 years" in html
    assert "Northwind Analytics Pvt Ltd" in html
    assert "Bluepeak Services" in html
    assert "Savitribai Phule University" in html
    assert "SQL" in html
    assert profile.profile_photo.name in html
    # Internal login placeholders are never rendered as contact.
    assert "no-email.talentvault.internal" not in html


@pytest.mark.django_db
def test_candidate_detail_hides_internal_placeholder_email(local_media):
    from django.test import Client
    from django.urls import reverse

    res_json = {
        "request_id": "req_ui_no_contact",
        "candidate": {"name": "Rahul Verma", "summary": "Backend engineer."},
        "skills": {"technical_skills": ["Java"]},
        "experience": [],
        "education": [],
    }
    mapped = ParseoraService.map_response_to_talentvault(res_json)
    profile, status = _run_pipeline("ui002", mapped)
    assert status == "SUCCESS"

    admin = User.objects.create_superuser(
        email="pipeline_admin2@talentvault.in",
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
    assert "no-email.talentvault.internal" not in html
    assert "Rahul Verma" in html
