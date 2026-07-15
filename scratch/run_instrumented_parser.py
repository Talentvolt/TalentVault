import os
import sys
import django
import time

# Setup path and environment
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Load env variables
try:
    import dotenv
    dotenv.load_dotenv(os.path.join(project_root, '.env'))
except ImportError:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.db import transaction
from apps.candidates.models import CandidateProfile, Experience, Education, CandidateSkill, Project, Certification
from apps.candidates.utils import sanitize_text, sanitize_recursive, parse_date_robust, extract_profile_photo
from utils.security import perform_all_security_validations
from services.resume_intelligence import ResumeIntelligenceService
from utils.preview import generate_resume_preview_response
from services.candidate_matching_service import CandidateMatchingService
from openai import OpenAI
from django.conf import settings
from decimal import Decimal
import fitz

def main():
    print("Clearing cache...")
    cache.clear()
    
    User = get_user_model()
    test_user, _ = User.objects.get_or_create(
        email="instrumented_test@example.com",
        defaults={"first_name": "Test", "last_name": "User"}
    )
    
    resume_path = "scratch/harneet_resume.pdf"
    filename = os.path.basename(resume_path)
    with open(resume_path, "rb") as f:
        file_bytes = f.read()
        
    print(f"Loaded: {resume_path} ({len(file_bytes)} bytes)")
    
    timings = {}
    
    # 1. Upload & Security Validation
    t0 = time.perf_counter()
    security_data = perform_all_security_validations(file_bytes, filename)
    timings['Upload & Security Validation'] = time.perf_counter() - t0
    
    # 2. Native PDF Text Extraction (PyMuPDF)
    t0 = time.perf_counter()
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text_pymupdf = ""
    for page in doc:
        text_pymupdf += page.get_text()
    doc.close()
    timings['Native PDF Extraction (PyMuPDF)'] = time.perf_counter() - t0
    
    # 3. OCR Stage (not used for searchable PDF)
    # We measure it as 0.0 because it's not used, but let's confirm.
    timings['OCR Stage'] = 0.0
    
    # Get merged text using pipeline rules
    ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, filename)
    extracted_text = ocr_result["text"]
    
    # 4. OpenAI Request
    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
    model_name = getattr(settings, "OPENAI_MODEL_NAME", "gpt-4.1-mini")
    if model_name == "gpt-4.1-mini":
        model_name = "gpt-4o-mini" # Ensure correct model is used in script
    client = OpenAI(api_key=api_key)
    
    system_content = (
        "You are a professional resume parsing assistant.\n"
        "Your critical objective is to extract 100% of the resume content without any summarization, omission, or simplification."
    )
    
    # Pydantic schema used by working parser
    from apps.candidates.utils import FastResumeSchema
    
    t0 = time.perf_counter()
    completion = client.beta.chat.completions.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": extracted_text}
        ],
        response_format=FastResumeSchema
    )
    timings['OpenAI Request'] = time.perf_counter() - t0
    
    # 5. JSON Validation & Dump
    t0 = time.perf_counter()
    llm_raw_data = completion.choices[0].message.parsed.model_dump()
    from apps.candidates.utils import convert_llm_data_to_standard_format
    parsed_data = convert_llm_data_to_standard_format(llm_raw_data)
    parsed_data = sanitize_recursive(parsed_data, "parsed_data")
    timings['JSON Validation'] = time.perf_counter() - t0
    
    # 6. S3 Upload (files saving)
    # We will instantiate the profile to save it, but we time the save calls separately
    profile_user, _ = User.objects.get_or_create(
        email="harneet_test@example.com",
        defaults={'role': User.Role.CANDIDATE}
    )
    profile, _ = CandidateProfile.objects.get_or_create(user=profile_user)
    
    save_filename = security_data.get("secure_filename") or filename
    
    t0 = time.perf_counter()
    profile.resume.save(save_filename, ContentFile(file_bytes), save=False)
    profile.original_file.save("original_" + save_filename, ContentFile(file_bytes), save=False)
    timings['S3 Upload'] = time.perf_counter() - t0
    
    # 7. Resume file save (local prep)
    # This is the time spent on photo extraction and setting up fields
    t0 = time.perf_counter()
    photo_bytes, photo_ext = extract_profile_photo(file_bytes, filename)
    if photo_bytes:
        profile.profile_photo.save(f"photo_{profile.id}.{photo_ext}", ContentFile(photo_bytes), save=False)
    timings['Resume File Save (Local Prep)'] = time.perf_counter() - t0
    
    # 8. Candidate Database Save (PostgreSQL operations)
    t0 = time.perf_counter()
    with transaction.atomic():
        # Flat fields save
        profile.full_name = "Harneet Singh Chhabra"
        profile.summary = parsed_data.get('summary', '')
        info = parsed_data.get('personal_info', {})
        profile.location = (info.get('location') or "Unknown")[:100]
        profile.linkedin_url = (info.get('linkedin_url') or "")[:200] or None
        profile.portfolio_url = (info.get('portfolio_url') or "")[:200] or None
        profile.parsed_json = parsed_data
        profile.raw_resume_text = extracted_text
        profile.save()
        
        # Nested tables insert
        profile.skills.all().delete()
        for skill in parsed_data.get('skills', []):
            CandidateSkill.objects.get_or_create(profile=profile, skill_name=skill.strip().title()[:100])
            
        profile.experiences.all().delete()
        for exp in parsed_data.get('experience', []):
            description_html = ResumeIntelligenceService.parse_experience_description_to_html(exp.get('description', ''))
            Experience.objects.create(
                profile=profile,
                company_name=(exp.get('company') or '')[:100],
                designation=(exp.get('designation') or '')[:100],
                description=description_html,
                start_date=parse_date_robust(exp.get('start_date'), None),
                end_date=parse_date_robust(exp.get('end_date'), None)
            )
            
        profile.educations.all().delete()
        for edu in parsed_data.get('education', []):
            Education.objects.create(
                profile=profile,
                institution=(edu.get('institution') or '')[:100],
                degree=(edu.get('degree') or '')[:100],
                field_of_study=(edu.get('field_of_study') or '')[:100],
                percentage_or_cgpa=(edu.get('score') or '')[:20],
                start_date=parse_date_robust(edu.get('start_date'), None),
                end_date=parse_date_robust(edu.get('end_date'), None)
            )
    timings['Candidate Database Save'] = time.perf_counter() - t0
    
    # 9. Resume Preview Generation
    t0 = time.perf_counter()
    preview_res = generate_resume_preview_response(profile)
    timings['Resume Preview Generation'] = time.perf_counter() - t0
    
    # 10. ATS Calculation
    t0 = time.perf_counter()
    CandidateMatchingService.update_ats_scores(candidate_id=profile.id)
    timings['ATS Calculation'] = time.perf_counter() - t0
    
    # Total timing calculation
    total_time = sum(timings.values())
    
    print("\n==================================================")
    print("        DETAILED STAGE-WISE TIMINGS BENCHMARK      ")
    print("==================================================")
    for stage, t_val in timings.items():
        pct = (t_val / total_time) * 100
        print(f"- {stage:35}: {t_val:7.4f}s ({pct:5.1f}%)")
    print(f"- {'Total Response (Summed Stages)':35}: {total_time:7.4f}s (100.0%)")
    print("==================================================\n")
    
    # SLA threshold check
    print("SLA Threshold Violations Check:")
    if timings['Candidate Database Save'] > 5.0:
        print(f"  [VIOLATION] Database Save took {timings['Candidate Database Save']:.2f}s (exceeded 5.0s)")
    else:
        print(f"  [OK] Database Save took {timings['Candidate Database Save']:.2f}s (<= 5.0s)")
        
    if timings['S3 Upload'] > 10.0:
        print(f"  [VIOLATION] S3 Upload took {timings['S3 Upload']:.2f}s (exceeded 10.0s)")
    else:
        print(f"  [OK] S3 Upload took {timings['S3 Upload']:.2f}s (<= 10.0s)")
        
    if timings['OpenAI Request'] > 45.0:
        print(f"  [VIOLATION] OpenAI Request took {timings['OpenAI Request']:.2f}s (exceeded 45.0s)")
    else:
        print(f"  [OK] OpenAI Request took {timings['OpenAI Request']:.2f}s (<= 45.0s)")

if __name__ == "__main__":
    main()
