import os
import sys
import json
import time
import requests
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from services.parseora_service import ParseoraService


def run_verification():
    print("=" * 80)
    print("TALENTVAULT -> PARSEORA INTEGRATION VERIFICATION")
    print("=" * 80)

    # 1. Check Configuration
    print("\n[1] CONFIGURATION VERIFICATION:")
    api_url = ParseoraService.get_api_url()
    api_key = ParseoraService.get_api_key()
    print(f"  - Parseora API URL: {api_url}")
    print(f"  - Parseora API Key Configured: {bool(api_key)}")
    print(f"  - Parseora Timeout: {ParseoraService.get_timeout()}s")
    assert api_url == "http://127.0.0.1:8001", f"Expected URL http://127.0.0.1:8001, got {api_url}"
    assert api_key, "PARSEORA_API_KEY is empty!"
    print("  [PASS] Configuration OK")

    # 2. Live Direct API Call to Parseora
    print("\n[2] DIRECT PARSEORA API CALL:")
    filename = "MADHANKUMAR_M_Simple_Parser_Ready.pdf"
    with open(filename, "rb") as f:
        cv_bytes = f.read()

    pf_resp = ParseoraService.parse_resume(cv_bytes, filename)
    req_id = pf_resp.get("request_id")
    doc_type = pf_resp.get("document_type")
    conf = pf_resp.get("classification_confidence")
    print(f"  - Parseora Request ID: {req_id}")
    print(f"  - Document Type: {doc_type}")
    print(f"  - Classification Confidence: {conf}%")
    assert doc_type == "resume", f"Expected resume, got {doc_type}"
    print("  [PASS] Direct Parseora call OK")

    # 3. Mapping Test
    print("\n[3] DATA MAPPING VERIFICATION:")
    mapped = ParseoraService.map_response_to_talentvault(pf_resp)
    p_info = mapped["personal_info"]
    print(f"  - Mapped Name: {p_info['name']}")
    print(f"  - Mapped Email: {p_info['email']}")
    print(f"  - Mapped Phone: {p_info['phone']}")
    print(f"  - Mapped Total Exp: {p_info['total_experience']} years")
    print(f"  - Mapped Skills Count: {len(mapped['skills'])}")
    print(f"  - Mapped Educations Count: {len(mapped['education'])}")
    print(f"  - Mapped Experiences Count: {len(mapped['experience'])}")
    assert p_info["email"], "Email must be mapped"
    assert p_info["name"], "Name must be mapped"
    assert len(mapped["skills"]) > 0, "Skills must be mapped"
    print("  [PASS] Mapping OK")

    # 4. TalentVault UI /resume-parser/ Endpoint Upload Test
    print("\n[4] TALENTVAULT ENDPOINT UPLOAD TEST (/resume-parser/):")
    recruiter = User.objects.filter(is_superuser=True).first()
    if not recruiter:
        recruiter = User.objects.filter(role=User.Role.SUPER_ADMIN).first()
    if not recruiter:
        recruiter = User.objects.filter(role=User.Role.RECRUITER, recruiter_status='ACTIVE').first()

    client = Client()
    client.force_login(recruiter)

    upload_file = SimpleUploadedFile(filename, cv_bytes, content_type="application/pdf")
    resp = client.post(reverse('frontend:resume_parser'), {
        'resume': upload_file,
        'overwrite': 'on'
    })
    print(f"  - HTTP Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    completed_event = None
    if hasattr(resp, 'streaming_content'):
        for chunk in resp.streaming_content:
            for line in chunk.decode('utf-8', errors='ignore').split('\n'):
                line = line.strip()
                if line:
                    try:
                        ev = json.loads(line)
                        if ev.get('stage') == 'completed':
                            completed_event = ev
                    except Exception:
                        pass

    assert completed_event is not None, "Did not receive completed stage from upload stream!"
    print(f"  - Stream Completed: candidate_id={completed_event.get('candidate_id')}, name={completed_event.get('name')}")
    print("  [PASS] TalentVault endpoint upload OK")

    # 5. Verify Parseora Request Logs
    print("\n[5] PARSEORA REQUEST LOGS VERIFICATION:")
    usage_res = requests.get(f"{api_url}/api/v1/usage", headers={'X-API-Key': api_key})
    assert usage_res.status_code == 200, f"Failed to fetch usage: {usage_res.status_code}"
    records = usage_res.json().get('usage_records', [])
    assert len(records) > 0, "No usage records found!"
    latest_log = records[0]
    print(f"  - Latest Log Request ID: {latest_log.get('request_id')}")
    print(f"  - Document Type: {latest_log.get('document_type')}")
    print(f"  - File Name: {latest_log.get('file_name')}")
    print(f"  - Status: {latest_log.get('status')}")
    print(f"  - Timestamp: {latest_log.get('timestamp')}")
    assert latest_log.get('status') == 'success', f"Expected success status, got {latest_log.get('status')}"
    assert latest_log.get('document_type') == 'resume', f"Expected resume, got {latest_log.get('document_type')}"
    print("  [PASS] Parseora Request Logs verified")

    # 6. Verify TalentVault Database Persistence
    print("\n[6] DATABASE CANDIDATE PROFILE VERIFICATION:")
    cand_id = completed_event.get('candidate_id')
    profile = CandidateProfile.objects.get(id=cand_id)
    print(f"  - Candidate ID: {profile.id}")
    print(f"  - Full Name: {profile.full_name}")
    print(f"  - Email: {profile.user.email}")
    print(f"  - Phone: {profile.user.phone_number}")
    print(f"  - Location: {profile.location}")
    print(f"  - Current Designation: {profile.current_designation}")
    print(f"  - Current Company: {profile.current_company}")
    print(f"  - Total Experience: {profile.total_experience}")
    print(f"  - Skills Count in DB: {profile.skills.count()}")
    print(f"  - Experiences Count in DB: {profile.experiences.count()}")
    print(f"  - Educations Count in DB: {profile.educations.count()}")
    print(f"  - OCR Engine: {profile.ocr_engine}")
    print(f"  - OCR Confidence: {profile.ocr_confidence}")
    print(f"  - Parsed JSON Parsed By: {profile.parsed_json.get('metadata', {}).get('parsed_by')}")
    print(f"  - Parsed JSON Request ID: {profile.parsed_json.get('metadata', {}).get('request_id')}")
    assert profile.ocr_engine == 'Parseora', f"Expected OCR Engine Parseora, got {profile.ocr_engine}"
    assert profile.parsed_json.get('metadata', {}).get('parsed_by') == 'Parseora'
    print("  [PASS] Candidate saved and verified in DB")

    print("\n" + "=" * 80)
    print("ALL INTEGRATION AND VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == '__main__':
    run_verification()
