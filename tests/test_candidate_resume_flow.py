import pytest
import io
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile, CandidateSkill, DuplicateResumeLog


@pytest.mark.django_db
def test_candidate_with_and_without_resume_tabs(client):
    """
    FLOW Requirement 1 & 2:
    - WITH RESUME tab only shows candidates with CV attached.
    - WITHOUT RESUME tab only shows candidates without CV attached.
    - WITHOUT RESUME candidate row clearly includes 'Upload CV' button.
    """
    recruiter = User.objects.create_user(
        email='recruiter_tab_test@company.com',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    client.force_login(recruiter)

    # 1. Create candidate WITH resume
    user_with = User.objects.create_user(email='with_cv@example.com', role=User.Role.CANDIDATE)
    cand_with = CandidateProfile.objects.create(
        user=user_with,
        full_name='Candidate With Resume',
        resume='resumes/sample_cv.pdf',
        uploaded_by=recruiter
    )

    # 2. Create candidate WITHOUT resume
    user_without = User.objects.create_user(email='without_cv@example.com', role=User.Role.CANDIDATE)
    cand_without = CandidateProfile.objects.create(
        user=user_without,
        full_name='Candidate Without Resume',
        resume=None,
        uploaded_by=recruiter
    )

    base_url = reverse('frontend:candidate_search')

    # Test WITH RESUME tab
    resp_with = client.get(f"{base_url}?tab=with_resume")
    assert resp_with.status_code == 200
    cands_with_ids = {c.id for c in resp_with.context['candidates']}
    assert cand_with.id in cands_with_ids
    assert cand_without.id not in cands_with_ids
    assert resp_with.context['current_tab'] == 'with_resume'

    # Test WITHOUT RESUME tab
    resp_without = client.get(f"{base_url}?tab=without_resume")
    assert resp_without.status_code == 200
    cands_without_ids = {c.id for c in resp_without.context['candidates']}
    assert cand_without.id in cands_without_ids
    assert cand_with.id not in cands_without_ids
    assert resp_without.context['current_tab'] == 'without_resume'

    # Verify "Upload CV" button is present in HTML for candidate without resume
    html_without = resp_without.content.decode('utf-8')
    assert "Upload CV" in html_without
    assert f"openUploadCVModal('{cand_without.id}'" in html_without


@pytest.mark.django_db
def test_upload_cv_updates_existing_candidate_and_moves_to_with_resume(client, monkeypatch):
    """
    FLOW Requirement 3, 4, 5, 6:
    - Existing candidate profile is updated (no duplicate created).
    - Uploaded CV attached to candidate.
    - Parsed data updates candidate profile.
    - Successful upload automatically moves candidate to WITH RESUME.
    - Recruiter ownership and duplicate log are preserved.
    """
    recruiter = User.objects.create_user(
        email='recruiter_upload_test@company.com',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    client.force_login(recruiter)

    # Candidate starts WITHOUT resume
    user = User.objects.create_user(email='initial_without@example.com', role=User.Role.CANDIDATE)
    cand = CandidateProfile.objects.create(
        user=user,
        full_name='Initial Candidate',
        location='Delhi',
        total_experience=2.0,
        uploaded_by=recruiter,
        created_by=recruiter
    )
    original_profile_id = cand.id
    original_user_id = user.id
    assert not cand.has_resume

    # Verify candidate starts in WITHOUT RESUME tab
    base_url = reverse('frontend:candidate_search')
    resp_before_with = client.get(f"{base_url}?tab=with_resume")
    assert original_profile_id not in {c.id for c in resp_before_with.context['candidates']}

    resp_before_without = client.get(f"{base_url}?tab=without_resume")
    assert original_profile_id in {c.id for c in resp_before_without.context['candidates']}

    # Mock parsing functions to avoid calling external OCR/Parseora network services in test
    fake_parsed_data = {
        "personal_info": {
            "name": "Updated Full Name",
            "email": "initial_without@example.com",
            "phone": "9876543210",
            "location": "Bengaluru",
            "current_company": "Acme Tech",
            "current_designation": "Senior Python Developer",
            "total_experience": 5.0,
            "relevant_experience": 4.0,
        },
        "skills": ["Python", "Django", "PostgreSQL", "Docker"],
        "summary": "Experienced Python Developer with 5 years experience.",
        "experience": [
            {
                "company": "Acme Tech",
                "designation": "Senior Python Developer",
                "start_date": "2021-01-01",
                "end_date": "",
                "is_current": True,
                "description": "Building scalable web services."
            }
        ],
        "education": [
            {
                "institution": "IIT Delhi",
                "degree": "B.Tech Computer Science",
                "field_of_study": "Computer Science",
                "start_date": "2016-08-01",
                "end_date": "2020-05-31"
            }
        ]
    }

    import utils.security
    monkeypatch.setattr(
        utils.security,
        "perform_all_security_validations",
        lambda file_bytes, filename: {"secure_filename": filename, "sha256": "fake_sha_123", "repaired_bytes": file_bytes}
    )
    import services.resume_intelligence
    monkeypatch.setattr(
        services.resume_intelligence.ResumeIntelligenceService,
        "run_ocr_pipeline",
        lambda file_bytes, filename: {"text": "dummy resume text", "largest_bold_name": "Updated Full Name"}
    )
    import apps.candidates.utils
    monkeypatch.setattr(
        apps.candidates.utils,
        "parse_resume_via_parseora",
        lambda file_bytes, filename: fake_parsed_data
    )
    monkeypatch.setattr(
        services.resume_intelligence.ResumeIntelligenceService,
        "ai_improve_resume_data",
        lambda parsed_data: parsed_data
    )
    import services.resume_storage_service
    monkeypatch.setattr(
        services.resume_storage_service,
        "upload_and_verify_resume",
        lambda file_bytes, filename: (f"resumes/{filename}", "fake_sha")
    )
    monkeypatch.setattr(
        services.resume_storage_service,
        "copy_and_verify_original_resume",
        lambda saved_key, filename: f"resumes/original/{filename}"
    )

    # Perform CV upload via merge_resume action
    pdf_content = b"%PDF-1.4 Mock PDF content for testing resume merge"
    test_file = SimpleUploadedFile("my_updated_resume.pdf", pdf_content, content_type="application/pdf")

    parser_url = reverse('frontend:resume_parser')
    response = client.post(
        parser_url,
        {
            'action': 'merge_resume',
            'candidate_id': str(original_profile_id),
            'resume': test_file
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['candidate_id'] == str(original_profile_id)

    # Verify existing profile was reused and NOT duplicated
    cand.refresh_from_db()
    assert cand.id == original_profile_id
    assert cand.user.id == original_user_id
    assert CandidateProfile.objects.filter(user=user).count() == 1

    # Verify resume is attached and has_resume is True
    assert cand.has_resume
    assert "my_updated_resume.pdf" in cand.resume.name

    # Verify parsed data updated existing profile
    assert cand.current_designation == "Senior Python Developer"
    assert cand.current_company == "Acme Tech"
    assert float(cand.total_experience) == 5.0
    assert cand.skills.filter(skill_name="Python").exists()
    assert cand.skills.filter(skill_name="Django").exists()
    assert cand.educations.filter(institution="IIT Delhi").exists()

    # Verify recruiter ownership is preserved
    assert cand.uploaded_by == recruiter
    assert cand.created_by == recruiter

    # Verify duplicate log is recorded
    assert DuplicateResumeLog.objects.filter(
        email=user.email,
        action_taken='MERGED'
    ).exists()

    # Verify candidate automatically moved to WITH RESUME tab and is NO LONGER in WITHOUT RESUME
    resp_after_with = client.get(f"{base_url}?tab=with_resume")
    assert original_profile_id in {c.id for c in resp_after_with.context['candidates']}

    resp_after_without = client.get(f"{base_url}?tab=without_resume")
    assert original_profile_id not in {c.id for c in resp_after_without.context['candidates']}


@pytest.mark.django_db
def test_candidate_detail_upload_cv_button(client):
    """
    FLOW Requirement 2:
    - Candidate detail profile clearly shows 'Upload CV' button when resume is not attached.
    """
    recruiter = User.objects.create_user(
        email='recruiter_detail_test@company.com',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    client.force_login(recruiter)

    # 1. Candidate without resume
    user_no = User.objects.create_user(email='no_resume_detail@example.com', role=User.Role.CANDIDATE)
    cand_no = CandidateProfile.objects.create(
        user=user_no,
        full_name='No Resume Detail',
        uploaded_by=recruiter,
        created_by=recruiter
    )

    detail_url = reverse('frontend:candidate_detail', kwargs={'pk': cand_no.id})
    resp = client.get(detail_url)
    assert resp.status_code == 200
    html = resp.content.decode('utf-8')

    # Both header action button and empty state upload button should be present
    assert "Upload CV" in html
    assert f"openUploadCVModal('{cand_no.id}'" in html
    assert "uploadCVModal" in html
