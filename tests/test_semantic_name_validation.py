"""
Semantic name validation regression tests.

Locks in that skills / technologies / companies / marketing terms / section
headings can never become the candidate name, while genuine human names pass.
Covers the reported "Google Ads became the candidate name" bug end-to-end.
"""

from services.parseora_service import ParseoraService
from services.resume_intelligence import ResumeIntelligenceService


def test_google_ads_is_rejected_as_name():
    assert ResumeIntelligenceService.is_non_person_name("Google Ads") is True
    assert ResumeIntelligenceService.is_valid_name("Google Ads") is False
    assert ParseoraService._is_plausible_person_name("Google Ads") is False


def test_digital_marketing_is_rejected_as_name():
    assert ResumeIntelligenceService.is_non_person_name("Digital Marketing") is True
    assert ResumeIntelligenceService.is_valid_name("Digital Marketing") is False


def test_marketing_and_tech_terms_rejected():
    for bad in ["Google Ads", "Digital Marketing", "Meta Ads", "Software Engineer",
                "Senior Developer", "Java Developer", "Data Science", "Machine Learning",
                "Social Media", "SEO Executive", "Technical Skills", "Professional Summary"]:
        assert ResumeIntelligenceService.is_valid_name(bad) is False, bad


def test_genuine_human_names_are_accepted():
    for good in ["Parul Rai", "Amit Sharma", "Ram Kakade", "Priya Nair",
                 "Rahul Verma", "Sreeharsha G R"]:
        assert ResumeIntelligenceService.is_valid_name(good) is True, good


def test_section_headings_still_rejected():
    for heading in ["Professional Experience", "Employment History", "Career History",
                    "Education", "Projects", "Skills", "Objective", "Career Objective",
                    "Technical Skills", "Personal Details"]:
        assert ResumeIntelligenceService.is_valid_name(heading) is False, heading


def test_heading_synonyms_detected():
    assert ResumeIntelligenceService.detect_heading_type("Employment History") == "WORK"
    assert ResumeIntelligenceService.detect_heading_type("Career History") == "WORK"
    assert ResumeIntelligenceService.detect_heading_type("Professional Background") == "WORK"
    assert ResumeIntelligenceService.detect_heading_type("Career Summary") == "SUMMARY"
    assert ResumeIntelligenceService.detect_heading_type("Professional Profile") == "SUMMARY"
    assert ResumeIntelligenceService.detect_heading_type("Professional Objective") == "SUMMARY"
    assert ResumeIntelligenceService.detect_heading_type("Address") == "PERSONAL"
    assert ResumeIntelligenceService.detect_heading_type("Contact Details") == "PERSONAL"


def test_parseora_google_ads_not_mapped_as_name():
    res = {
        "candidate": {
            "name": "Google Ads",
            "email": "parul.rai@example.com",
            "phone": "+91 98765 43210",
            "summary": "Digital marketing professional.",
        },
        "skills": {"technical_skills": ["Google Ads", "SEO", "Analytics"]},
        "experience": [],
        "education": [],
    }
    mapped = ParseoraService.map_response_to_talentvault(res)
    # "Google Ads" must never become the candidate name.
    assert mapped["personal_info"]["name"] == ""
    assert "Google Ads" not in mapped["personal_info"]["name"]
    # Skills remain separate and intact.
    assert mapped["skills"]
