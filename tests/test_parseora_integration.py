import os
from unittest.mock import MagicMock, patch

import pytest

from apps.candidates.utils import parse_resume_via_parseora


PARSEORA_SAMPLE_RESPONSE = {
    "request_id": "req_parseora_001",
    "candidate": {
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "phone": "+91 98765 43210",
        "current_company": "Acme Corp",
        "current_designation": "Software Engineer",
        "current_ctc": "12 LPA",
        "expected_ctc": "18 LPA",
        "notice_period": "30 days",
        "summary": "Software engineer with experience building web platforms.",
        "current_location": "Bengaluru",
        "linkedin": "https://www.linkedin.com/in/janedoe",
        "date_of_birth": "1994-05-20",
        "gender": "Female"
    },
    "skills": {
        "technical_skills": ["Python", "Django", "SQL"],
        "soft_skills": ["Communication"]
    },
    "experience": [
        {
            "company_name": "Acme Corp",
            "job_title": "Software Engineer",
            "start_date": "2021-01-01",
            "end_date": "2022-01-01",
            "location": "Bengaluru",
            "responsibilities": ["Built REST APIs", "Reviewed pull requests"]
        }
    ],
    "education": [
        {
            "degree": "B.Tech",
            "college": "Example Institute",
            "field_of_study": "Computer Science",
            "end_year": "2016"
        }
    ],
    "projects": [{"title": "TalentVault", "description": "Recruitment platform"}],
    "certifications": [
        {
            "name": "AWS Certified Developer",
            "issuing_organization": "Amazon",
            "issue_date": "2022-01-10"
        }
    ],
    "languages": ["English"],
    "achievements": ["Employee of the Month"]
}


def test_parse_resume_via_parseora_uses_parseora_and_maps_candidate(monkeypatch):
    """Parseora (not OpenAI) is used for resume parsing and its structured JSON
    is mapped into TalentVault candidate fields via the existing mapper."""
    api_url_env = "https://parseora.example.test"
    api_key_env = "test-key-123"
    monkeypatch.setenv("PARSEORA_API_URL", api_url_env)
    monkeypatch.setenv("PARSEORA_API_KEY", api_key_env)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}
    mock_response.json.return_value = PARSEORA_SAMPLE_RESPONSE

    with patch("requests.post", return_value=mock_response) as mock_post:
        result = parse_resume_via_parseora(b"fake-resume-bytes", "jane_resume.pdf")

    # 1. The only API call goes to the Parseora endpoint with the Parseora key.
    args, kwargs = mock_post.call_args
    assert mock_post.call_count == 1
    assert args[0] == f"{api_url_env}/api/v1/parse"
    assert kwargs["headers"]["X-API-Key"] == api_key_env
    assert kwargs["files"]["file"][0] == "jane_resume.pdf"

    # 2. Parseora structured JSON is mapped to TalentVault candidate fields.
    personal = result["personal_info"]
    assert personal["name"] == "Jane Doe"
    assert personal["email"] == "jane.doe@example.com"
    assert personal["phone"] == "9876543210"
    assert personal["current_company"] == "Acme Corp"
    assert personal["current_designation"] == "Software Engineer"
    assert personal["total_experience"] == 1.0
    assert result["current_ctc"] == 1200000
    assert "Python" in result["skills"]
    assert result["experience"][0]["company"] == "Acme Corp"
    assert result["education"][0]["degree"] == "B.Tech"
    assert result["certifications"][0]["name"] == "AWS Certified Developer"
    assert result["metadata"]["parsed_by"] == "Parseora"
