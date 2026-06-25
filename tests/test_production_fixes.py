import pytest
from decimal import Decimal
from django.urls import reverse
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from apps.candidates.models import CandidateProfile
from apps.candidates.forms import CandidateProfileForm
from apps.core.views import CandidateResumePreviewView, CandidateResumeDownloadView
from services.resume_intelligence import ResumeIntelligenceService

User = get_user_model()

@pytest.mark.django_db
def test_salary_form_and_sync():
    # 1. Create a candidate
    user = User.objects.create_user(email="testcandidate@example.com", password="password123")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name="John Doe",
        current_salary=Decimal("800000.00"),
        expected_salary=Decimal("1200000.00")
    )
    assert profile.current_salary_lpa == "8 LPA"
    assert profile.expected_salary_lpa == "12 LPA"

    # 2. Test Form Initialization (should convert raw numbers to LPA)
    form = CandidateProfileForm(instance=profile)
    assert form.initial['current_salary'] == 8.0
    assert form.initial['expected_salary'] == 12.0

    # 3. Test Form Save (should convert LPA input back to raw values)
    form_data = {
        'full_name': 'John Doe Updated',
        'summary': 'Some summary',
        'location': 'New Delhi',
        'total_experience': 5.5,
        'current_company': 'Google',
        'current_designation': 'Software Engineer',
        'current_salary': 10.5, # LPA
        'expected_salary': 15.0, # LPA
        'notice_period': 30
    }
    form = CandidateProfileForm(data=form_data, instance=profile)
    assert form.is_valid(), form.errors
    saved_profile = form.save()
    
    assert saved_profile.current_salary == Decimal("1050000.00")
    assert saved_profile.expected_salary == Decimal("1500000.00")
    assert saved_profile.current_salary_lpa == "10.5 LPA"
    assert saved_profile.expected_salary_lpa == "15 LPA"

@pytest.mark.django_db
def test_resume_versions_sync():
    user = User.objects.create_user(email="testcandidate2@example.com", password="password123")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name="Jane Doe",
        current_version=1,
        resume_versions={
            "1": {
                "version": 1,
                "data": {
                    "personal_info": {
                        "name": "Jane Doe",
                        "location": "Old Location"
                    },
                    "summary": "Old Summary"
                }
            }
        }
    )

    # Modify fields on profile directly and save
    profile.full_name = "Jane Doe Updated"
    profile.location = "New Location"
    profile.summary = "New Summary"
    profile.save()

    # Verify that resume_versions active version data got updated
    active_version_data = profile.resume_versions["1"]["data"]
    assert active_version_data["personal_info"]["name"] == "Jane Doe Updated"
    assert active_version_data["personal_info"]["location"] == "New Location"
    assert active_version_data["summary"] == "New Summary"

def test_ocr_heading_detection_length():
    # Test text block matching a heading
    text = "WORK EXPERIENCE\n"
    res = ResumeIntelligenceService.parse_resume_nlp(text)
    # The heading is short, so it switches section to WORK, leaving experiences list empty but work_lines populated
    
    # Test a long sentence containing "experience" (like a profile summary statement)
    long_summary_sentence = "John Doe\nCertified Project Manager with 15 years of Customer Service People Management experience"
    res_long = ResumeIntelligenceService.parse_resume_nlp(long_summary_sentence)
    # Because of length filter, it shouldn't switch current_section to WORK, and should be parsed as summary fallback instead
    assert "Certified Project Manager" in res_long["summary"]
