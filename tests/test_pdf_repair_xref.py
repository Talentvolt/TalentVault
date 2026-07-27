import pytest
import io
import fitz  # PyMuPDF
from utils.security import perform_all_security_validations, scan_pdf_security, repair_pdf_bytes, SecurityValidationError
from apps.accounts.models import User
from apps.candidates.utils import process_resume_file

@pytest.mark.django_db
def test_xref_corrupted_pdf_security_validation_passes():
    """
    Test that PyMuPDF xref errors (e.g. 'cannot find object in xref' or 'code=7')
    are NOT classified as malware and DO NOT fail security validation.
    """
    # Create a valid PDF first
    pdf_doc = fitz.open()
    page = pdf_doc.new_page(width=600, height=800)
    page.insert_text((50, 100), "Rahul Sharma Resume. Email: rahul@example.com")
    valid_pdf_bytes = pdf_doc.tobytes()
    pdf_doc.close()

    # Corrupt xref start offset to simulate CamScanner/mobile scanner corrupt xref
    corrupted_pdf_bytes = valid_pdf_bytes.replace(b"startxref", b"startxref 99999999\n%EOF\n")
    
    # 1. Verify scan_pdf_security does NOT raise SecurityValidationError for structural xref issue
    assert scan_pdf_security(corrupted_pdf_bytes) is True

    # 2. Verify perform_all_security_validations passes for structural xref issues
    security_res = perform_all_security_validations(corrupted_pdf_bytes, "Rahul_Resume.pdf")
    assert security_res["scan_status"] == "PASSED"

    # 3. Test repair_pdf_bytes directly returns warning 'PDF repaired automatically.'
    repaired, strat, msg = repair_pdf_bytes(corrupted_pdf_bytes, "Rahul_Resume.pdf")
    assert repaired is not None
    assert msg == "PDF repaired automatically."

@pytest.mark.django_db
def test_xref_corrupted_pdf_resume_parsing_success():
    """
    Test that an xref corrupted PDF processes and creates a candidate profile cleanly.
    """
    recruiter = User.objects.create_user(
        email="recruiter.repair@example.com",
        password="TestPassword123!",
        role=User.Role.RECRUITER
    )

    pdf_doc = fitz.open()
    page = pdf_doc.new_page(width=600, height=800)
    page.insert_text((50, 100), "Amit Kumar")
    page.insert_text((50, 150), "Email: amit.kumar@example.com")
    page.insert_text((50, 200), "Phone: +919876543210")
    page.insert_text((50, 250), "Location: New Delhi")
    valid_bytes = pdf_doc.tobytes()
    pdf_doc.close()

    # Introduce xref/trailer corruption
    corrupt_bytes = valid_bytes.replace(b"startxref", b"startxref 99999999\n%EOF\n")

    pdf_file_obj = io.BytesIO(corrupt_bytes)
    profile, status = process_resume_file(
        file_obj=pdf_file_obj,
        filename="Amit_Kumar_Corrupt_Xref.pdf",
        user=recruiter
    )

    assert status == "SUCCESS"
    assert profile is not None
    assert profile.full_name != "Unknown Candidate"
    assert "Amit" in profile.full_name or "Kumar" in profile.full_name
    assert profile.user.email == "amit.kumar@example.com"

@pytest.mark.django_db
def test_real_malware_js_pdf_rejected():
    """
    Ensure active malware with embedded JavaScript is STILL rejected by security validation.
    """
    pdf_bytes_with_js = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R /JS (app.alert('Malware')) >>\nendobj\n"
    
    with pytest.raises(SecurityValidationError) as excinfo:
        perform_all_security_validations(pdf_bytes_with_js, "malicious.pdf")
    
    assert "Suspicious PDF content detected." in str(excinfo.value)
