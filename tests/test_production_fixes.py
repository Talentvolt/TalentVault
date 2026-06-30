import pytest
from decimal import Decimal
from django.urls import reverse
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from apps.candidates.models import CandidateProfile
from apps.candidates.forms import CandidateProfileForm
from apps.core.views import CandidateResumePreviewView, CandidateResumeDownloadView
from services.resume_intelligence import ResumeIntelligenceService
from unittest.mock import patch

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
    # --- Test 1: Plain paragraph lines are preserved in order as <p> tags ---
    desc_plain = (
        "Responsibilities:\n"
        "Managed a team of 5 sales engineers.\n"
        "Territory Coverage:\n"
        "North region and Delhi NCR.\n"
        "Achievements:\n"
        "Exceeded annual sales target by 25%."
    )
    html_plain = ResumeIntelligenceService.parse_experience_description_to_html(desc_plain)
    # All lines are plain text (no bullet chars) so they all become <p> elements
    assert '<p class="mb-1">Responsibilities:</p>' in html_plain
    assert '<p class="mb-1">Managed a team of 5 sales engineers.</p>' in html_plain
    assert '<p class="mb-1">Territory Coverage:</p>' in html_plain
    assert '<p class="mb-1">North region and Delhi NCR.</p>' in html_plain
    assert '<p class="mb-1">Achievements:</p>' in html_plain
    assert '<p class="mb-1">Exceeded annual sales target by 25%.</p>' in html_plain

    # --- Test 2: Bullet lines become <li> items inside <ul> ---
    desc_bullets = (
        "• Managed a team of 5 sales engineers.\n"
        "• Covered North region and Delhi NCR.\n"
        "• Exceeded annual sales target by 25%."
    )
    html_bullets = ResumeIntelligenceService.parse_experience_description_to_html(desc_bullets)
    assert "<ul class='resume-bullets'>" in html_bullets
    assert "<li>Managed a team of 5 sales engineers.</li>" in html_bullets
    assert "<li>Covered North region and Delhi NCR.</li>" in html_bullets
    assert "<li>Exceeded annual sales target by 25%.</li>" in html_bullets

    # --- Test 3: Mixed bullets and paragraphs maintain order and group correctly ---
    desc_mixed = (
        "Key Responsibilities:\n"
        "• Line one\n"
        "• Line two\n"
        "Summary note here."
    )
    html_mixed = ResumeIntelligenceService.parse_experience_description_to_html(desc_mixed)
    assert '<p class="mb-1">Key Responsibilities:</p>' in html_mixed
    assert "<li>Line one</li>" in html_mixed
    assert "<li>Line two</li>" in html_mixed
    assert '<p class="mb-1">Summary note here.</p>' in html_mixed

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


@pytest.mark.django_db
def test_original_resume_retention_and_preview():
    import io
    from django.core.files.base import ContentFile
    
    # 1. Create candidate
    user = User.objects.create_user(email="harneet_test@example.com", password="password123")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name="Harneet Singh Chhabra",
        location="Delhi"
    )
    
    fake_pdf_content = b"%PDF-1.4 ... fake pdf content ... %EOF"
    profile.resume.save("harneet_resume.pdf", ContentFile(fake_pdf_content), save=True)
    
    # Generate and save the generated resume separately
    generated_pdf_content = b"%PDF-1.4 ... generated ats content ... %EOF"
    profile.generated_resume.save("generated_resume.pdf", ContentFile(generated_pdf_content), save=True)
    
    # Verify both exist separately
    profile.refresh_from_db()
    assert "harneet_resume" in profile.resume.name
    assert "generated_resume" in profile.generated_resume.name
    assert profile.resume.name.endswith(".pdf")
    assert profile.generated_resume.name.endswith(".pdf")
    
    # 2. Test Preview View
    factory = RequestFactory()
    request = factory.get(reverse('frontend:candidate_resume_preview', kwargs={'pk': profile.pk}))
    request.user = user
    
    view = CandidateResumePreviewView.as_view()
    response = view(request, pk=profile.pk)
    
    assert response.status_code == 200
    # Should serve the original fake_pdf_content, NOT the generated_pdf_content
    response_content = b"".join(response.streaming_content)
    assert response_content == fake_pdf_content
    
    # 3. Test Download View
    request_dl = factory.get(reverse('frontend:candidate_resume_download', kwargs={'pk': profile.pk}))
    request_dl.user = user
    
    view_dl = CandidateResumeDownloadView.as_view()
    response_dl = view_dl(request_dl, pk=profile.pk)
    
    assert response_dl.status_code == 200
    response_dl_content = b"".join(response_dl.streaming_content)
    assert response_dl_content == fake_pdf_content


@pytest.mark.django_db
def test_candidate_delete_flow():
    from django.contrib.messages import get_messages
    from django.test import Client
    
    # 1. Create a candidate user and candidate profile
    candidate_user = User.objects.create_user(email="candidate_del@example.com", password="password123", role="CANDIDATE")
    profile = CandidateProfile.objects.create(
        user=candidate_user,
        full_name="To Be Deleted",
        location="Bangalore"
    )
    candidate_id = profile.id
    
    # Create recruiter user to perform the action (as CandidateDeleteView has LoginRequiredMixin)
    recruiter_user = User.objects.create_user(email="recruiter_del@example.com", password="password123", role="RECRUITER")
    
    client = Client()
    client.force_login(recruiter_user)
    
    # 2. Test deleting existing candidate
    delete_url = reverse('frontend:candidate_delete', kwargs={'id': candidate_id})
    response = client.post(delete_url)
    
    # Verify it returns HTTP 302 redirect
    assert response.status_code == 302
    assert response.url == reverse('frontend:candidate_search')
    
    # Verify the candidate and the user are deleted
    assert not CandidateProfile.objects.filter(id=candidate_id).exists()
    assert not User.objects.filter(id=candidate_user.id).exists()
    
    # Verify the Django success message
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) > 0
    assert any("Candidate deleted successfully." in str(msg) for msg in messages)
    
    # 3. Test already deleted candidate / duplicate POST / double-click / browser refresh
    response2 = client.post(delete_url)
    
    # Verify it returns HTTP 302 redirect instead of 404
    assert response2.status_code == 302
    assert response2.url == reverse('frontend:candidate_search')
    
    # Verify Django success/info message: "Candidate already deleted."
    messages2 = list(get_messages(response2.wsgi_request))
    assert len(messages2) > 0
    assert any("Candidate already deleted." in str(msg) for msg in messages2)


@pytest.mark.django_db
def test_ats_friendly_pdf_generation_with_malformed_html():
    from apps.candidates.models import CandidateProfile, Experience, Project, CandidateSkill
    from services.resume_intelligence import ResumeIntelligenceService
    import datetime

    user = User.objects.create_user(email="ats_test@example.com", password="password123")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name="Rajeev Kumar & Partners <br>",
        location="Delhi & NCR",
        linkedin_url="https://linkedin.com/in/rajeev?param1=val1&param2=val2",
        summary="Professional summary with unclosed <b>bold and <i>italic tags and raw & signs."
    )
    
    # 1. Experience with malformed HTML
    # Note: parse_experience_description_to_html produces HTML with style block and ul/li. Let's pass that directly as description.
    malformed_description = (
        "<style>\n.resume-bullets { list-style-type: disc !important; }\n</style>\n"
        "<ul class='resume-bullets'>\n"
        "  <li>Managed R&D team with <b>unclosed tag\n"
        "  <li>Worked on AT&T systems & Python\n"
        "</ul>"
    )
    Experience.objects.create(
        profile=profile,
        company_name="AT&T & Co.",
        designation="Senior R&D Lead <b>",
        start_date=datetime.date(2020, 1, 1),
        description=malformed_description
    )
    
    # 2. Project with raw & and unclosed tag in link and description
    Project.objects.create(
        profile=profile,
        title="Project A&B <font color='red'>",
        link="https://github.com/project?a=1&b=2",
        description="Developed custom widgets <p>with unclosed <p> tags"
    )
    
    # 3. Skills with raw & and <
    CandidateSkill.objects.create(profile=profile, skill_name="C++ & Java")
    CandidateSkill.objects.create(profile=profile, skill_name="HTML/CSS <tags>")
    
    # Generate ATS PDF
    pdf_bytes = ResumeIntelligenceService.generate_ats_friendly_pdf(profile)
    
    # Assertions
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_profile_photo_extraction_face_detection_and_heuristics():
    import numpy as np
    import cv2
    from unittest.mock import patch
    from apps.candidates.utils import select_best_profile_photo

    logo_img = np.ones((150, 150, 3), dtype=np.uint8) * 255
    cv2.putText(logo_img, "COMPANY LOGO", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    _, logo_bytes = cv2.imencode(".png", logo_img)
    logo_bytes = logo_bytes.tobytes()

    banner_img = np.ones((100, 500, 3), dtype=np.uint8) * 255
    cv2.putText(banner_img, "BANNER AD", (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 3)
    _, banner_bytes = cv2.imencode(".png", banner_img)
    banner_bytes = banner_bytes.tobytes()

    # Logo and banner have no faces, so select_best_profile_photo should reject them and return None, None
    best_data, best_ext = select_best_profile_photo([
        (banner_bytes, "png"),
        (logo_bytes, "png")
    ])
    assert best_data is None
    assert best_ext is None

    # Test empty list
    best_data_empty, best_ext_empty = select_best_profile_photo([])
    assert best_data_empty is None
    assert best_ext_empty is None


@pytest.mark.django_db
@patch('cv2.CascadeClassifier.detectMultiScale')
def test_profile_photo_extraction_with_mocked_face(mock_detect):
    import numpy as np
    import cv2
    from apps.candidates.utils import select_best_profile_photo

    # Mock frontal face detection to return exactly one face, and profile face to return empty
    mock_detect.side_effect = [
        np.array([[20, 20, 80, 80]]), # frontal faces
        []                            # profile faces
    ]

    # Create a 120x150 portrait image
    portrait_img = np.ones((150, 120, 3), dtype=np.uint8) * 200
    # Add texture/gradients so it's not mostly white
    portrait_img[10:140, 10:110] = 120
    _, portrait_bytes = cv2.imencode(".png", portrait_img)
    portrait_bytes = portrait_bytes.tobytes()

    best_data, best_ext = select_best_profile_photo([
        (portrait_bytes, "png")
    ])

    assert best_data == portrait_bytes
    assert best_ext == "png"


def test_education_date_parsing():
    from apps.candidates.utils import parse_education_date_to_date_obj
    import datetime

    # Test required cases
    d1 = parse_education_date_to_date_obj("May-2008")
    assert d1 == datetime.date(2008, 5, 1)

    d2 = parse_education_date_to_date_obj("May-2012")
    assert d2 == datetime.date(2012, 5, 1)

    d3 = parse_education_date_to_date_obj("May-2015")
    assert d3 == datetime.date(2015, 5, 1)

    # Test other common formats
    assert parse_education_date_to_date_obj("Apr-2010") == datetime.date(2010, 4, 1)
    assert parse_education_date_to_date_obj("June 2015") == datetime.date(2015, 6, 1)
    assert parse_education_date_to_date_obj("2015") == datetime.date(2015, 1, 1)
    assert parse_education_date_to_date_obj("05/2015") == datetime.date(2015, 5, 1)
    assert parse_education_date_to_date_obj("2015-05") == datetime.date(2015, 5, 1)
    assert parse_education_date_to_date_obj("Mar 2022") == datetime.date(2022, 3, 1)
    assert parse_education_date_to_date_obj("March-2022") == datetime.date(2022, 3, 1)


@pytest.mark.django_db
def test_save_llm_parsed_data_education_one_year():
    from apps.candidates.models import CandidateProfile
    from apps.accounts.models import User
    from services.parser.llm_extractor import save_llm_parsed_data_to_db
    import datetime

    user = User.objects.create_user(email="edu_test_one_year@example.com", password="password123")
    profile = CandidateProfile.objects.create(user=user)

    mock_validated_data = {
        "candidate_name": {"value": "Ramanjeet Maurya"},
        "education": {
            "value": [
                {
                    "degree": {"value": "B.Tech"},
                    "college": {"value": "IIT Delhi"},
                    "start_year": {"value": "May-2015"}, # Only start_year exists
                    "end_year": {"value": None}
                }
            ]
        }
    }

    save_llm_parsed_data_to_db(profile, mock_validated_data)
    profile.refresh_from_db()
    
    # Assert start_date and end_date
    assert profile.educations.count() == 1
    edu = profile.educations.first()
    assert edu.start_date is None
    # Requirement: "If only one completion year exists: store it as end_date."
    assert edu.end_date == datetime.date(2015, 5, 1)




