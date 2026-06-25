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

def test_profile_photo_extraction_graceful_fallback():
    from apps.candidates.utils import extract_profile_photo
    # Test that invalid files do not raise an exception and return (None, None)
    img_data, ext = extract_profile_photo(b"invalid data", "test.pdf")
    assert img_data is None
    assert ext is None

    img_data, ext = extract_profile_photo(b"invalid data", "test.docx")
    assert img_data is None
    assert ext is None

@pytest.mark.django_db
def test_has_profile_photo_property():
    user = User.objects.create_user(email="testcandidatephoto@example.com", password="password123")
    profile = CandidateProfile.objects.create(user=user, full_name="Photo Test")
    
    # 1. No photo
    assert profile.has_profile_photo is False
    
    # 2. Photo set but missing on disk
    profile.profile_photo = "candidate_photos/nonexistent.png"
    profile.save()
    assert profile.has_profile_photo is False

def test_parse_experience_description_to_html():
    desc = (
        "Responsibilities:\n"
        "Managed a team of 5 sales engineers.\n"
        "Territory Coverage:\n"
        "North region and Delhi NCR.\n"
        "Achievements:\n"
        "Exceeded annual sales target by 25%."
    )
    html = ResumeIntelligenceService.parse_experience_description_to_html(desc)
    assert "<strong>Responsibilities</strong>" in html
    assert "<li>Managed a team of 5 sales engineers.</li>" in html
    assert "<strong>Territory Coverage</strong>" in html
    assert "<li>North region and Delhi NCR.</li>" in html
    assert "<strong>Achievements</strong>" in html
    assert "<li>Exceeded annual sales target by 25%.</li>" in html

@pytest.mark.django_db
def test_json_edit_view_salary_sync():
    user = User.objects.create_user(email="jsonctctest@example.com", password="password123")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name="CTC Test",
        current_salary=Decimal("500000.00"),
        expected_salary=Decimal("800000.00")
    )
    
    # Simulated JSON Edit Payload (Structured Resume Editor save)
    data = {
        "personal_info": {
            "name": "CTC Test Updated",
            "current_salary": 7.5, # 7.5 LPA
            "expected_salary": 10.0, # 10 LPA
            "total_experience": 3.5,
            "location": "Bangalore"
        },
        "summary": "Updated summary test",
        "skills": ["Python", "Django"],
        "experience": []
    }
    
    # Post to view
    factory = RequestFactory()
    from apps.core.views import CandidateJSONEditView
    import json
    request = factory.post(
        reverse('frontend:candidate_edit_json', kwargs={'pk': profile.pk}),
        data=json.dumps(data),
        content_type='application/json'
    )
    request.user = user
    
    view = CandidateJSONEditView.as_view()
    response = view(request, pk=profile.pk)
    assert response.status_code == 200
    
    # Refresh from database
    profile.refresh_from_db()
    assert profile.current_salary == Decimal("750000.00")
    assert profile.expected_salary == Decimal("1000000.00")
    assert profile.current_salary_lpa == "7.5 LPA"
    assert profile.expected_salary_lpa == "10 LPA"
