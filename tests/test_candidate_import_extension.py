import pytest
import base64
from decimal import Decimal
from unittest.mock import patch
from django.urls import reverse
from django.core.files.storage import InMemoryStorage
from rest_framework import status
from rest_framework.test import APIClient
from apps.candidates.models import CandidateProfile, Experience, Education, CandidateSkill, Project, Certification
from apps.accounts.models import User

EXT_ORIGIN = "chrome-extension://egcfpgbhoklbacaijdachfbemffnfejp"

@pytest.mark.django_db
def test_import_assigns_uploaded_by_from_email():
    client = APIClient()
    url = reverse('api_candidate_import')

    recruiter = User.objects.create_user(
        email='recruiter@example.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        first_name='Anamika',
        last_name='Shukla',
    )

    payload = {
        "full_name": "Uploader Candidate",
        "location": "Pune",
        "source": "naukri",
        "uploaded_by_email": "recruiter@example.com",
    }

    resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert resp.status_code == status.HTTP_201_CREATED

    profile = CandidateProfile.objects.get(full_name="Uploader Candidate")
    assert profile.uploaded_by_id == recruiter.id
    assert profile.uploaded_by.email == "recruiter@example.com"
    assert profile.uploader_name == "Anamika Shukla"


@pytest.mark.django_db
def test_import_without_uploaded_by_email_leaves_uploader_none():
    client = APIClient()
    url = reverse('api_candidate_import')

    payload = {
        "full_name": "Unattributed Candidate",
        "location": "Mumbai",
        "source": "naukri",
    }

    resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert resp.status_code == status.HTTP_201_CREATED

    profile = CandidateProfile.objects.get(full_name="Unattributed Candidate")
    assert profile.uploaded_by is None


@pytest.mark.django_db
def test_full_linkedin_candidate_import_pipeline():
    client = APIClient()
    url = reverse('api_candidate_import')

    payload = {
        "name": "Ananya Deshmukh",
        "headline": "Principal AI Architect | LLM Systems & Infrastructure Lead",
        "current_company": "NVIDIA",
        "location": "Bengaluru, Karnataka, India",
        "summary": "14+ years of experience building massive-scale AI infrastructure, distributed GPU training clusters, and LLM inference engines. Leading NVIDIA AI Platforms division in APAC.",
        "profile_url": "https://www.linkedin.com/in/ananya-deshmukh-ai/",
        "source": "linkedin",
        "total_experience": 14.0,
        "current_salary": 45.0,
        "expected_salary": 60.0,
        "notice_period": 30,
        "skills": [
            "Artificial Intelligence",
            "PyTorch",
            "CUDA",
            "Distributed Systems",
            "LLMs",
            "Python",
            "C++"
        ],
        "experience": [
            {
                "company_name": "NVIDIA",
                "designation": "Principal AI Architect",
                "duration": "Jan 2022 - Present",
                "location": "Bengaluru, Karnataka, India",
                "description": "Directing APAC AI Systems engineering group. Optimized Megatron-LM tensor parallel performance by 35% on H100 clusters."
            },
            {
                "company_name": "Google",
                "designation": "Senior Staff Engineer - Cloud AI",
                "duration": "Mar 2017 - Dec 2021 · 4 yrs 10 mos",
                "location": "Bengaluru, India",
                "description": "Architected Cloud TPU v3/v4 pod training pipeline for Vertex AI."
            },
            {
                "company_name": "Microsoft",
                "designation": "Senior Software Engineer",
                "duration": "Jun 2012 - Feb 2017 · 4 yrs 9 mos",
                "location": "Hyderabad, India",
                "description": "Developed Azure AI Search indexing pipeline."
            }
        ],
        "education": [
            {
                "institution": "Indian Institute of Science (IISc), Bangalore",
                "degree": "Ph.D., Computer Science & AI",
                "field_of_study": "Computer Science & AI",
                "dates": "2008 - 2012"
            },
            {
                "institution": "IIT Madras",
                "degree": "B.Tech, Computer Science and Engineering",
                "field_of_study": "Computer Science and Engineering",
                "dates": "2004 - 2008"
            }
        ]
    }

    response = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "created"

    candidate_id = data["candidate_id"]
    profile = CandidateProfile.objects.get(id=candidate_id)

    # Verify all fields saved on CandidateProfile
    assert profile.full_name == "Ananya Deshmukh"
    assert profile.current_designation == "Principal AI Architect | LLM Systems & Infrastructure Lead"
    assert profile.current_company == "NVIDIA"
    assert profile.location == "Bengaluru, Karnataka, India"
    assert "14+ years of experience" in profile.summary
    assert profile.linkedin_url == "https://www.linkedin.com/in/ananya-deshmukh-ai/"
    assert profile.source == "linkedin"

    # Verify CTC & Notice Period
    assert profile.total_experience == Decimal("14.0")
    assert profile.current_salary == Decimal("4500000.00")
    assert profile.expected_salary == Decimal("6000000.00")
    assert profile.notice_period == 30

    # Verify ALL Experience entries saved completely without description truncation
    experiences = list(profile.experiences.order_by('-start_date'))
    assert len(experiences) == 3
    assert experiences[0].company_name == "NVIDIA"
    assert experiences[0].designation == "Principal AI Architect"
    assert experiences[0].is_current is True
    assert experiences[0].location == "Bengaluru, Karnataka, India"
    assert "Megatron-LM" in experiences[0].description

    assert experiences[1].company_name == "Google"
    assert experiences[1].designation == "Senior Staff Engineer - Cloud AI"
    assert experiences[1].location == "Bengaluru, India"
    assert "Cloud TPU" in experiences[1].description

    # Verify ALL Education entries saved completely
    educations = list(profile.educations.all())
    assert len(educations) == 2
    assert educations[0].institution == "Indian Institute of Science (IISc), Bangalore"
    assert educations[0].degree == "Ph.D., Computer Science & AI"
    assert educations[1].institution == "IIT Madras"

    # Verify ALL Skills saved
    skills = [s.skill_name for s in profile.skills.all()]
    assert len(skills) == 7
    assert "PyTorch" in skills
    assert "CUDA" in skills
    assert "LLMs" in skills

    # Test Duplicate handling
    dup_response = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert dup_response.status_code == status.HTTP_200_OK
    dup_data = dup_response.json()
    assert dup_data["action"] == "updated"
    assert dup_data["candidate_id"] == candidate_id

@pytest.mark.django_db
def test_manual_mode_candidate_import_pipeline():
    client = APIClient()
    url = reverse('api_candidate_import')

    payload = {
        "full_name": "Rohan Sharma",
        "current_designation": "Staff Frontend Engineer",
        "current_company": "Atlassian",
        "location": "Bengaluru, India",
        "summary": "Full stack engineer specializing in React, TypeScript and Micro-frontends.",
        "linkedin_url": "https://www.linkedin.com/in/rohan-sharma-dev/",
        "source": "manual",
        "total_experience": "8.5",
        "current_salary": "28.0",
        "expected_salary": "36.0",
        "notice_period": "15",
        "is_immediate_joiner": False,
        "skills": ["React", "TypeScript", "Next.js", "Redux"],
        "experience": [
            {
                "company_name": "Atlassian",
                "designation": "Staff Frontend Engineer",
                "duration": "Jan 2021 - Present",
                "location": "Bengaluru, India",
                "description": "Leading Jira frontend performance optimization team."
            },
            {
                "company_name": "Flipkart",
                "designation": "Senior UI Engineer",
                "duration": "Jul 2016 - Dec 2020",
                "location": "Bengaluru, India",
                "description": "Built Mobile Web PWA serving 50M+ monthly active users."
            }
        ],
        "education": [
            {
                "institution": "BITS Pilani",
                "degree": "B.E., Computer Science",
                "field_of_study": "Computer Science",
                "dates": "2012 - 2016"
            }
        ]
    }

    response = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "created"

    candidate_id = data["candidate_id"]
    profile = CandidateProfile.objects.get(id=candidate_id)

    assert profile.full_name == "Rohan Sharma"
    assert profile.current_designation == "Staff Frontend Engineer"
    assert profile.current_company == "Atlassian"
    assert profile.location == "Bengaluru, India"
    assert profile.total_experience == Decimal("8.5")
    assert profile.current_salary == Decimal("2800000.00")
    assert profile.expected_salary == Decimal("3600000.00")
    assert profile.notice_period == 15
    assert profile.source == "manual"

    # Verify Experience and Education counts
    assert profile.experiences.count() == 2
    assert profile.educations.count() == 1
    assert profile.skills.count() == 4

@pytest.mark.django_db
def test_chrome_extension_origin_csrf_and_get_endpoint():
    client = APIClient()
    url = reverse('api_candidate_import')

    # 1. Test GET endpoint returns CSRF token
    get_res = client.get(url, HTTP_ORIGIN=EXT_ORIGIN)
    assert get_res.status_code == status.HTTP_200_OK
    get_data = get_res.json()
    assert get_data["status"] == "ok"
    assert "csrfToken" in get_data

    # 2. Test POST with exact chrome-extension origin
    payload = {
        "full_name": "Test Origin Candidate",
        "current_designation": "QA Automation Lead",
        "current_company": "Tech Corp",
        "location": "Hyderabad",
        "source": "linkedin"
    }

    post_res = client.post(
        url,
        payload,
        format='json',
        HTTP_ORIGIN=EXT_ORIGIN
    )
    assert post_res.status_code == status.HTTP_201_CREATED
    data = post_res.json()
    assert data["status"] == "success"


@pytest.mark.django_db
def test_naukri_candidates_do_not_collide_on_shared_preview_path():
    """
    Two different Naukri candidates share the same path
    (https://resdex.naukri.com/v3/preview) and differ only by the ?profileId
    query param. The duplicate detector must match the FULL canonical URL so the
    second candidate is created (201), not wrongly "updated" onto the first.
    """
    client = APIClient()
    url = reverse('api_candidate_import')

    def payload(name, profile_id):
        return {
            "full_name": name,
            "location": "Delhi",
            "source": "naukri",
            "profile_url": f"https://resdex.naukri.com/v3/preview?profileId={profile_id}",
        }

    first = client.post(url, payload("Varun Dubey", "111"), format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert first.status_code == status.HTTP_201_CREATED
    assert first.json()["action"] == "created"

    second = client.post(url, payload("Rohan Sharma", "222"), format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert second.status_code == status.HTTP_201_CREATED
    assert second.json()["action"] == "created"

    assert CandidateProfile.objects.filter(full_name="Varun Dubey").exists()
    assert CandidateProfile.objects.filter(full_name="Rohan Sharma").exists()


@pytest.mark.django_db
def test_import_maps_experience_fields_without_not_specified():
    client = APIClient()
    url = reverse('api_candidate_import')

    payload = {
        "full_name": "Mapping Candidate",
        "location": "Pune",
        "source": "linkedin",
        "experience": [
            {
                "company_name": "Google",
                "designation": "Senior Engineer",
                "employment_type": "Full-time",
                "location": "Bengaluru, India",
                "duration": "Mar 2018 - Present · 5 yrs 9 mos",
                "description": "Led search infrastructure.",
            },
            {
                "company_name": "Google",
                "designation": "Software Engineer",
                "employment_type": "Full-time",
                "duration": "Jan 2015 - Feb 2018",
            },
        ],
        "education": [
            {"institution": "IIT Bombay", "degree": "B.Tech", "field_of_study": "CS", "dates": "2011 - 2015"},
        ],
    }

    resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert resp.status_code == status.HTTP_201_CREATED

    profile = CandidateProfile.objects.get(full_name="Mapping Candidate")
    experiences = list(profile.experiences.all())

    # Two roles at the same company stay separate.
    assert len(experiences) == 2
    first = experiences[0]
    assert first.company_name == "Google"
    assert first.designation == "Senior Engineer"
    assert first.employment_type == "Full-time"
    assert first.location == "Bengaluru, India"
    assert first.is_current is True
    assert "search infrastructure" in first.description

    second = experiences[1]
    assert second.company_name == "Google"
    assert second.designation == "Software Engineer"
    assert second.is_current is False

    # No "Not Specified" placeholder is ever stored.
    for exp in experiences:
        assert exp.company_name != "Not Specified"
        assert exp.designation != "Not Specified"

    edu = profile.educations.first()
    assert edu.institution == "IIT Bombay"
    assert edu.degree == "B.Tech"


@pytest.mark.django_db
def test_import_rejects_pdf_filename_with_non_pdf_bytes():
    client = APIClient()
    url = reverse('api_candidate_import')

    # A .pdf filename whose bytes are NOT a real PDF must not be attached.
    payload = {
        "full_name": "Fake PDF Candidate",
        "location": "Pune",
        "source": "naukri",
        "resume": {
            "filename": "candidate.pdf",
            "data_base64": base64.b64encode(b"this is not a pdf at all").decode("ascii"),
            "mime_type": "application/pdf",
        },
    }

    with patch("services.resume_storage_service.get_active_resume_storage", return_value=InMemoryStorage()):
        resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["resume_attached"] is False
        assert "Invalid PDF content" in resp.json()["resume_message"]

        profile = CandidateProfile.objects.get(full_name="Fake PDF Candidate")
        assert profile.has_resume is False


@pytest.mark.django_db
def test_import_rejects_empty_resume_bytes():
    client = APIClient()
    url = reverse('api_candidate_import')

    payload = {
        "full_name": "Empty Resume Candidate",
        "location": "Pune",
        "source": "naukri",
        "resume": {
            "filename": "candidate.pdf",
            "data_base64": base64.b64encode(b"").decode("ascii"),
            "mime_type": "application/pdf",
        },
    }

    with patch("services.resume_storage_service.get_active_resume_storage", return_value=InMemoryStorage()):
        resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["resume_attached"] is False

        profile = CandidateProfile.objects.get(full_name="Empty Resume Candidate")
        assert profile.has_resume is False


@pytest.mark.django_db
def test_import_attaches_manual_resume_base64_over_source_url():
    client = APIClient()
    url = reverse('api_candidate_import')

    pdf_bytes = b"%PDF-1.4 Manual resume content"
    resume_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    payload = {
        "full_name": "Manual Resume Candidate",
        "location": "Pune",
        "source": "naukri",
        "resume": {
            "filename": "manual_cv.pdf",
            "resume_base64": resume_b64,
            "mime_type": "application/pdf",
            "resume_url": "https://resdex.naukri.com/v3/simcv?s=1",
        },
    }

    with patch("services.resume_storage_service.get_active_resume_storage", return_value=InMemoryStorage()):
        resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["resume_attached"] is True

        profile = CandidateProfile.objects.get(full_name="Manual Resume Candidate")
        # The manual Base64 file must be saved (priority over source URL).
        assert profile.has_resume is True
        assert profile.original_filename == "manual_cv.pdf"
        assert not profile.source_resume_url


@pytest.mark.django_db
def test_import_attaches_resume_without_overwriting():
    client = APIClient()
    url = reverse('api_candidate_import')

    pdf_bytes = b"%PDF-1.4 TalentVault fake resume content"
    resume_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    payload = {
        "full_name": "Resume Candidate",
        "location": "Delhi",
        "source": "naukri",
        "profile_url": "https://www.naukri.com/mnjuser/profile?id=9999",
        "resume": {
            "filename": "candidate.pdf",
            "data_base64": resume_b64,
            "mime_type": "application/pdf",
        },
    }

    with patch("services.resume_storage_service.get_active_resume_storage", return_value=InMemoryStorage()):
        resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["resume_attached"] is True

        profile = CandidateProfile.objects.get(full_name="Resume Candidate")
        assert profile.has_resume is True
        original_name = profile.original_filename
        assert original_name == "candidate.pdf"

        # Re-import with a different resume must NOT overwrite the existing one.
        payload["resume"]["filename"] = "replacement.pdf"
        payload["resume"]["data_base64"] = base64.b64encode(b"%PDF-1.4 different").decode("ascii")
        resp2 = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
        assert resp2.status_code == status.HTTP_200_OK
        assert resp2.json()["resume_attached"] is False

        profile.refresh_from_db()
        assert profile.original_filename == "candidate.pdf"


@pytest.mark.django_db
def test_import_skips_unsupported_resume_and_still_saves():
    client = APIClient()
    url = reverse('api_candidate_import')

    payload = {
        "full_name": "Unsupported Resume Candidate",
        "location": "Mumbai",
        "source": "naukri",
        "resume": {
            "filename": "malware.exe",
            "data_base64": base64.b64encode(b"not a resume").decode("ascii"),
        },
    }

    resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.json()["resume_attached"] is False

    profile = CandidateProfile.objects.get(full_name="Unsupported Resume Candidate")
    assert profile.has_resume is False


@pytest.mark.django_db
def test_import_stores_resume_url_when_no_bytes():
    client = APIClient()
    url = reverse('api_candidate_import')

    # Long Naukri resume/blob URL must be stored intact (TextField, no truncation).
    resume_url = (
        "https://resdex.naukri.com/resume/view?sid=1234&token="
        + ("x" * 300)
        + "&download=true"
    )

    payload = {
        "full_name": "URL Resume Candidate",
        "location": "Pune",
        "source": "naukri",
        "resume": {
            "filename": "Candidate_Resume.pdf",
            "resume_url": resume_url,
        },
    }

    resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.json()["resume_attached"] is True
    assert "link" in resp.json()["resume_message"]

    profile = CandidateProfile.objects.get(full_name="URL Resume Candidate")
    assert profile.has_resume is False
    assert profile.source_resume_url == resume_url


@pytest.mark.django_db
def test_import_with_structured_resume_format_and_projects_certifications():
    client = APIClient()
    url = reverse('api_candidate_import')

    payload = {
        "personal_info": {
            "name": "Kavita Raman",
            "email": "kavita.raman@example.com",
            "phone": "+91 98765 43210",
            "location": "Bengaluru, Karnataka",
            "current_company": "Razorpay",
            "current_designation": "Staff Engineer - Payments Platform",
            "total_experience": 10.5,
            "current_salary": 42.0,
            "expected_salary": 55.0,
            "notice_period": 15,
            "profile_url": "https://www.linkedin.com/in/kavita-raman-payments/",
        },
        "summary": "10+ years engineering high-availability payment gateways and distributed ledger systems.",
        "skills": ["Distributed Systems", "Go", "PostgreSQL", "Kafka", "AWS"],
        "experience": [
            {
                "company": "Razorpay",
                "designation": "Staff Engineer",
                "employment_type": "Full-time",
                "start_date": "2021-06-01",
                "end_date": "Present",
                "duration": "Jun 2021 - Present",
                "location": "Bengaluru, India",
                "description": "Architected next-gen checkout routing pipeline handling 10k TPS."
            }
        ],
        "education": [
            {
                "institution": "BITS Pilani",
                "degree": "B.E. (Hons)",
                "field_of_study": "Computer Science",
                "start_date": "2010-08-01",
                "end_date": "2014-05-31",
                "dates": "2010 - 2014"
            }
        ],
        "projects": [
            {
                "title": "UltraCheckout SDK",
                "description": "Sub-second 1-click checkout platform for merchant integrations.",
                "role": "Lead Architect",
                "link": "https://github.com/example/ultracheckout",
                "start_date": "2022-01-01",
                "end_date": "2023-01-01"
            },
            {
                "title": "LedgerZero",
                "description": "High throughput double-entry immutable financial ledger.",
                "link": "https://github.com/example/ledgerzero"
            }
        ],
        "certifications": [
            {
                "name": "AWS Certified Solutions Architect - Professional",
                "issuing_organization": "Amazon Web Services (AWS)",
                "issue_date": "2023-03-15"
            },
            {
                "name": "Certified Kubernetes Administrator (CKA)",
                "issuing_organization": "Cloud Native Computing Foundation (CNCF)",
                "issue_date": "2022-11-20"
            }
        ],
        "source": "linkedin"
    }

    resp = client.post(url, payload, format='json', HTTP_ORIGIN=EXT_ORIGIN)
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["status"] == "success"
    assert data["action"] == "created"
    assert data["candidate"]["projects_count"] == 2
    assert data["candidate"]["certifications_count"] == 2

    profile = CandidateProfile.objects.get(id=data["candidate_id"])
    assert profile.full_name == "Kavita Raman"
    assert profile.current_company == "Razorpay"
    assert profile.current_designation == "Staff Engineer - Payments Platform"
    assert profile.total_experience == Decimal("10.5")
    assert profile.current_salary == Decimal("4200000.00")
    assert profile.expected_salary == Decimal("5500000.00")
    assert profile.notice_period == 15

    # Check Projects persisted
    projects = profile.projects.order_by("title")
    assert projects.count() == 2
    p1 = projects.filter(title="UltraCheckout SDK").first()
    assert p1 is not None
    assert "Lead Architect" in p1.description
    assert p1.link == "https://github.com/example/ultracheckout"

    p2 = projects.filter(title="LedgerZero").first()
    assert p2 is not None
    assert p2.link == "https://github.com/example/ledgerzero"

    # Check Certifications persisted
    certs = profile.certifications.order_by("name")
    assert certs.count() == 2
    c1 = certs.filter(name="AWS Certified Solutions Architect - Professional").first()
    assert c1 is not None
    assert c1.issuing_organization == "Amazon Web Services (AWS)"
    assert str(c1.issue_date) == "2023-03-15"

    # Verify canonical parsed_json matches Structured Resume Editor format
    parsed = profile.parsed_json
    assert isinstance(parsed, dict)
    assert "personal_info" in parsed
    assert parsed["personal_info"]["name"] == "Kavita Raman"
    assert parsed["personal_info"]["email"] == "kavita.raman@example.com"
    assert parsed["personal_info"]["current_company"] == "Razorpay"
    assert parsed["personal_info"]["current_salary"] == 42.0
    assert parsed["personal_info"]["expected_salary"] == 55.0
    assert parsed["personal_info"]["notice_period"] == 15
    assert len(parsed["experience"]) == 1
    assert len(parsed["education"]) == 1
    assert len(parsed["projects"]) == 2
    assert len(parsed["certifications"]) == 2
