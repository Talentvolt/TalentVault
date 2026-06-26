import pytest
import io
import re
from unittest.mock import patch, MagicMock
from services.resume_intelligence import ResumeIntelligenceService
from apps.candidates.utils import process_resume_file
from apps.candidates.models import CandidateProfile
from apps.accounts.models import User

# --- Helper Tests for validator ---

def test_is_valid_name_valid_cases():
    assert ResumeIntelligenceService.is_valid_name("John Doe") is True
    assert ResumeIntelligenceService.is_valid_name("Laxmi Sudharshan") is True
    assert ResumeIntelligenceService.is_valid_name("Sunil Gupta") is True
    assert ResumeIntelligenceService.is_valid_name("A. P. J. Abdul Kalam") is True

def test_is_valid_name_invalid_cases():
    # Phone numbers
    assert ResumeIntelligenceService.is_valid_name("(+91) 9953699195") is False
    assert ResumeIntelligenceService.is_valid_name("+91 99536 99195") is False
    assert ResumeIntelligenceService.is_valid_name("9953699195") is False
    assert ResumeIntelligenceService.is_valid_name("99536991") is False # 8 digits
    # Emails
    assert ResumeIntelligenceService.is_valid_name("john.doe@example.com") is False
    assert ResumeIntelligenceService.is_valid_name("candidate@example.co.in") is False
    # URLs
    assert ResumeIntelligenceService.is_valid_name("http://example.com") is False
    assert ResumeIntelligenceService.is_valid_name("https://github.com/profile") is False
    assert ResumeIntelligenceService.is_valid_name("www.linkedin.com/in/user") is False
    # Numeric/Symbols
    assert ResumeIntelligenceService.is_valid_name("123456789") is False
    assert ResumeIntelligenceService.is_valid_name("12345") is False
    assert ResumeIntelligenceService.is_valid_name("---") is False

# --- Helper Tests for extraction priorities ---

def test_priority_1_parsed_json_name():
    # Priority 1: parsed_name is valid
    text = "John Doe\n+91 99536 99195\njohn@example.com"
    name = ResumeIntelligenceService.extract_candidate_name(text, parsed_name="John Doe")
    assert name == "John Doe"

def test_priority_2_nlp_person_entity():
    # Priority 2: parsed_name is invalid (phone number), so it falls back to NLP PERSON entity (heuristic)
    text = "(+91) 9953699195\njohn@example.com\nAnkit Kumar\nSoftware Engineer"
    name = ResumeIntelligenceService.extract_candidate_name(text, parsed_name="(+91) 9953699195")
    assert name == "Ankit Kumar"

def test_priority_3_first_valid_text_line():
    # Priority 3: No valid PERSON entity, so first text line excluding phone/email/etc.
    text = "(+91) 9953699195\njohn@example.com\nAlex Smith\nGoogle"
    name = ResumeIntelligenceService.extract_candidate_name(text, parsed_name="(+91) 9953699195")
    assert name == "Alex Smith"

def test_priority_4_ocr_layout_heading():
    # Priority 4: If first line is valid, but doesn't pass priority 3 due to some reason, wait, first line is OCR Layout heading.
    # Actually, if the first line is valid, Priority 3 will return it anyway. But what if Priority 3 line is checked:
    # First text line that is valid according to our validator.
    text = "My Heading\n+919953699195"
    name = ResumeIntelligenceService.extract_candidate_name(text)
    assert name == "My Heading"

def test_priority_5_fallback_unknown():
    # Priority 5: Everything is invalid
    text = "(+91) 9953699195\njohn@example.com\nhttp://myportfolio.com"
    name = ResumeIntelligenceService.extract_candidate_name(text)
    assert name == "Unknown Candidate"


# --- End to End process_resume_file Tests ---

@pytest.mark.django_db
@patch('services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline')
def test_process_resume_proper_name(mock_ocr):
    # Setup mock OCR output with a proper name at the beginning
    mock_ocr.return_value = {
        "text": "Laxmi Sudharshan\nlaxmi@example.com\n+91 98765 43211\nExperience: Python Developer",
        "engine": "pdfplumber",
        "confidence": 98.0,
        "resume_type": "EDITABLE_PDF"
    }

    file_obj = io.BytesIO(b"dummy pdf content")
    profile, status = process_resume_file(file_obj, "resume.pdf")

    assert status == "SUCCESS"
    assert profile is not None
    assert profile.full_name == "Laxmi Sudharshan"
    assert profile.user.email == "laxmi@example.com"
    assert profile.user.phone_number == "9876543211"

@pytest.mark.django_db
@patch('services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline')
def test_process_resume_only_phone_number(mock_ocr):
    # Setup mock OCR output with only phone number and email as first lines, followed by non-PERSON lines
    mock_ocr.return_value = {
        "text": "(+91) 9953699195\nrecruit@example.com\nhttp://linkedin.com/in/fake\nAlex Smith",
        "engine": "PaddleOCR",
        "confidence": 95.0,
        "resume_type": "SCANNED_IMAGE"
    }

    file_obj = io.BytesIO(b"dummy image content")
    profile, status = process_resume_file(file_obj, "scanned_resume.png")

    assert status == "SUCCESS"
    assert profile is not None
    # Phone number is skipped as name. "Alex Smith" matches priority 3 (first valid line).
    assert profile.full_name == "Alex Smith"
    assert profile.user.email == "recruit@example.com"

@pytest.mark.django_db
@patch('services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline')
def test_process_resume_scanned_ocr_fallback(mock_ocr):
    # Setup mock OCR output with completely invalid header lines
    mock_ocr.return_value = {
        "text": "(+91) 9953699195\nadmin@example.com",
        "engine": "Tesseract",
        "confidence": 90.0,
        "resume_type": "SCANNED_PDF"
    }

    file_obj = io.BytesIO(b"dummy scanned pdf")
    profile, status = process_resume_file(file_obj, "scanned_only.pdf")

    assert status == "SUCCESS"
    assert profile is not None
    # Fallback name "Unknown Candidate" is used because all lines are invalid
    assert profile.full_name == "Unknown Candidate"


# --- Regression Tests for Major Headings ---

def test_first_heading_work_experience():
    text = "WORK EXPERIENCE\nJohn Doe\nEmail: john@example.com\nExperience: 5 years"
    name = ResumeIntelligenceService.extract_candidate_name(text, email="john@example.com")
    assert name == "John Doe"

def test_first_heading_curriculum_vitae():
    text = "CURRICULUM VITAE\nJane Smith\nEmail: jane.smith@example.com\nEducation: B.Tech"
    name = ResumeIntelligenceService.extract_candidate_name(text, email="jane.smith@example.com")
    assert name == "Jane Smith"

def test_first_heading_resume():
    text = "RESUME\nRobert Johnson\nEmail: robert@example.com\nSkills: Python, Django"
    name = ResumeIntelligenceService.extract_candidate_name(text, email="robert@example.com")
    assert name == "Robert Johnson"


# --- Company vs Person Entity Regression Tests ---

def test_regression_shreya_chavda_company():
    text = "SHREYA CHAVDA\nAnant Zaveri Pvt Ltd.\nEmail: shreya.chavda1712@gmail.com"
    name = ResumeIntelligenceService.extract_candidate_name(text, email="shreya.chavda1712@gmail.com")
    assert name == "Shreya Chavda"

def test_regression_rohan_kumar_company():
    text = "ROHAN KUMAR\nChampion Semiconductor LLP\nEmail: rohan@example.com"
    name = ResumeIntelligenceService.extract_candidate_name(text, email="rohan@example.com")
    assert name == "Rohan Kumar"

def test_regression_harneet_singh_chhabra_company():
    text = "HARNEET SINGH CHHABRA\nHero MotoCorp\nEmail: harneet@example.com"
    name = ResumeIntelligenceService.extract_candidate_name(text, email="harneet@example.com")
    assert name == "Harneet Singh Chhabra"


# --- Cross-contamination regression tests (Bug: hardcoded overrides were causing wrong names) ---

def test_no_cross_contamination_rohan_kumar_not_rajeev():
    """
    CRITICAL: Rohan Kumar's resume text contains 'kumar' which also appears in 'Rajeev Kumar'.
    The old hardcoded override returned 'Rajeev Kumar' when the word 'rajeev' appeared anywhere in
    the full OCR text (e.g., referrer header, system context, or any mention).
    This test simulates a Rohan Kumar resume where the text also mentions 'rajeev' somewhere
    (e.g. a reference contact or footer) and asserts the name is correctly 'Rohan Kumar'.
    """
    text = (
        "ROHAN KUMAR\n"
        "Software Engineer\n"
        "Email: rohankumar@example.com\n"
        "Phone: 9876500001\n"
        "Reference contact: Rajeev Kumar, HR Manager\n"  # 'rajeev' present in text
        "Work Experience\n"
        "Tata Consultancy Services\n"
        "Software Engineer | Jan 2021 - Present\n"
        "• Developed microservices using Python and Django\n"
        "• Led a team of 5 engineers"
    )
    name = ResumeIntelligenceService.extract_candidate_name(
        text, email="rohankumar@example.com"
    )
    # Must be Rohan Kumar — NOT Rajeev Kumar, even though 'rajeev' + 'kumar' both appear in text
    assert name == "Rohan Kumar", f"Expected 'Rohan Kumar' but got '{name}'"

def test_rajeev_kumar_own_resume_correct():
    """Rajeev Kumar's own resume must return 'Rajeev Kumar' via layout scoring, not hardcoded override."""
    text = (
        "RAJEEV KUMAR\n"
        "Email: rajeevkumar9801456p@gmail.com\n"
        "LinkedIn: linkedin.com/in/rajeev98p/\n"
        "Work Experience\n"
        "Some Company\n"
        "Software Engineer | 2020 - 2023"
    )
    name = ResumeIntelligenceService.extract_candidate_name(
        text,
        email="rajeevkumar9801456p@gmail.com",
        linkedin="linkedin.com/in/rajeev98p/"
    )
    assert name == "Rajeev Kumar", f"Expected 'Rajeev Kumar' but got '{name}'"

def test_vikke_gupta_correct_name():
    """Vikke Gupta's resume must return 'Vikke Gupta' via layout scoring."""
    text = (
        "VIKKE GUPTA\n"
        "Email: vikke.gupta@example.com\n"
        "Sales Executive\n"
        "Work Experience\n"
        "ABC Ltd\n"
        "Sales Executive | 2019 - 2022"
    )
    name = ResumeIntelligenceService.extract_candidate_name(
        text, email="vikke.gupta@example.com"
    )
    assert name == "Vikke Gupta", f"Expected 'Vikke Gupta' but got '{name}'"

def test_no_cross_contamination_unrelated_resume():
    """An unrelated resume whose text contains a name from validation set must still return its own name."""
    text = (
        "PRIYA SHARMA\n"
        "Data Analyst\n"
        "Email: priya.sharma@example.com\n"
        "Skills: Python, SQL\n"
        "Harneet mentioned in reference section\n"  # other name present
    )
    name = ResumeIntelligenceService.extract_candidate_name(
        text, email="priya.sharma@example.com"
    )
    assert name == "Priya Sharma", f"Expected 'Priya Sharma' but got '{name}'"
