import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.candidates.models import CandidateProfile, Experience, Education, CandidateSkill
from apps.accounts.models import User

EXT_ORIGIN = "chrome-extension://hneceobjjiehhicimdfdeheodcoklgec"

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
    assert "Megatron-LM" in experiences[0].description

    assert experiences[1].company_name == "Google"
    assert experiences[1].designation == "Senior Staff Engineer - Cloud AI"
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
