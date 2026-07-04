import os
import io
import zipfile
import pytest
from unittest.mock import patch, MagicMock
from utils.security import (
    sanitize_filename,
    generate_secure_filename,
    SecurityValidationError,
    perform_all_security_validations,
    validate_zip_archive,
    detect_password_protection,
    scan_office_security,
    scan_pdf_security,
    log_upload_attempt
)
from apps.candidates.models import CandidateProfile
from django.utils import timezone
from apps.candidates.utils import handle_resume_upload, process_resume_file
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

User = get_user_model()

def test_sanitize_filename():
    assert sanitize_filename("../../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename("my resume file.docx") == "my_resume_file.docx"
    assert sanitize_filename("a" * 300 + ".txt") == "a" * 251 + ".txt"

def test_generate_secure_filename():
    fn = generate_secure_filename("test.pdf")
    assert fn.endswith(".pdf")
    assert len(fn) > 30

@patch('magic.from_buffer', return_value="application/pdf")
@patch('utils.security.scan_bytes_with_clamd')
def test_virus_detection(mock_scan, mock_magic):
    mock_scan.return_value = ("INFECTED", "Eicar-Test-Signature")
    
    with pytest.raises(SecurityValidationError) as excinfo:
        perform_all_security_validations(b"%PDF-1.4\n", "resume.pdf")
    assert "Virus detected." in str(excinfo.value)

def test_password_protection_pdf():
    with patch('fitz.open') as mock_fitz:
        mock_doc = MagicMock()
        mock_doc.is_encrypted = True
        mock_fitz.return_value = mock_doc
        
        assert detect_password_protection(b"%PDF-1.4\n", "pdf") is True

def test_zip_bomb_detection_file_count():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        for i in range(55):  # Limit is 50
            zf.writestr(f"file_{i}.txt", "test")
            
    with pytest.raises(SecurityValidationError) as excinfo:
        validate_zip_archive(zip_buffer.getvalue())
    assert "ZIP Bomb detected." in str(excinfo.value)
    assert excinfo.value.code == "MAX_FILES"

def test_zip_bomb_detection_nested_depth():
    depth3 = io.BytesIO()
    with zipfile.ZipFile(depth3, 'w') as z:
        z.writestr("test.txt", "test")
        
    depth2 = io.BytesIO()
    with zipfile.ZipFile(depth2, 'w') as z:
        z.writestr("nested.zip", depth3.getvalue())
        
    depth1 = io.BytesIO()
    with zipfile.ZipFile(depth1, 'w') as z:
        z.writestr("nested2.zip", depth2.getvalue())
        
    with pytest.raises(SecurityValidationError) as excinfo:
        validate_zip_archive(depth1.getvalue())
    assert "ZIP Bomb detected." in str(excinfo.value)
    assert excinfo.value.code == "NESTED_ZIP_DEPTH"

def test_zip_dangerous_extension():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr("malicious.exe", "test")
        
    with pytest.raises(SecurityValidationError) as excinfo:
        validate_zip_archive(zip_buffer.getvalue())
    assert "Executable found inside ZIP." in str(excinfo.value)

@patch('magic.from_buffer', return_value="application/pdf")
def test_pdf_active_content_js(mock_magic):
    pdf_bytes = b"%PDF-1.4 ... /JavaScript ... /JS"
    with pytest.raises(SecurityValidationError) as excinfo:
        perform_all_security_validations(pdf_bytes, "resume.pdf")
    assert "Suspicious PDF content detected." in str(excinfo.value)

@patch('magic.from_buffer', return_value="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
def test_docx_office_macro_detection(mock_magic):
    with patch('oletools.olevba.VBA_Parser.detect_vba_macros', return_value=True):
        with pytest.raises(SecurityValidationError) as excinfo:
            perform_all_security_validations(b"PK\x03\x04dummy_bytes", "resume.docx")
        assert "Office macro detected." in str(excinfo.value)

@pytest.mark.django_db
@patch('utils.security.scan_pdf_security', return_value=True)
@patch('magic.from_buffer', return_value="application/pdf")
@patch('utils.security.scan_bytes_with_clamd')
@patch('services.resume_intelligence.ResumeIntelligenceService.run_ocr_pipeline')
def test_successful_validation_and_database_store(mock_ocr, mock_scan, mock_magic, mock_pdf):
    mock_scan.return_value = ("CLEAN", None)
    mock_ocr.return_value = {
        "text": "John Doe Resume. Email: john@example.com. Phone: 1234567890",
        "engine": "test-mock",
        "confidence": 98.0,
        "resume_type": "PDF"
    }

    user = User.objects.create_user(email="john@example.com", password="password123")
    
    # PDF Header bytes
    pdf_bytes = b"%PDF-1.4\n%...\n"
    
    file_obj = io.BytesIO(pdf_bytes)
    uploaded_file = SimpleUploadedFile("resume.pdf", pdf_bytes, content_type="application/pdf")
    
    results = handle_resume_upload(uploaded_file, overwrite=True, user=user)
    
    assert len(results['created']) == 1
    profile = results['created'][0]
    
    assert profile.original_filename == "resume.pdf"
    assert profile.secure_filename is not None
    assert profile.sha256 is not None
    assert profile.mime_type == "application/pdf"
    assert profile.scan_status == "PASSED"
    assert profile.scan_timestamp is not None
    assert profile.parser_status == "SUCCESS"
    assert profile.preview_status == "READY"

def test_fallback_validation_no_magic():
    from utils.security import get_mime_type
    with patch('utils.security.HAS_MAGIC', False):
        # 1. Test get_mime_type fallback
        mime = get_mime_type(b"%PDF-1.4\n", "my_resume.pdf", "pdf")
        assert mime == "application/pdf"
        
        # 2. Test validating pdf file content
        from utils.security import validate_single_file_content
        # Mock scan_pdf_security to avoid parsing invalid pdf bytes
        with patch('utils.security.scan_pdf_security', return_value=True):
            assert validate_single_file_content(b"%PDF-1.4\n", "my_resume.pdf", "pdf") is True
