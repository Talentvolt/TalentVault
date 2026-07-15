import os
import sys
import time
import gc
import psutil
import django
import io
import hashlib
import json
from decimal import Decimal

# 1. Setup Django env
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from apps.candidates.models import CandidateProfile, Experience, Education, Project, Certification
from apps.candidates.utils import process_resume_file
from services.singletons import NLPService, OCRService, AIService, StorageService
from services.parser.pipeline import ResumeParsingPipeline
from services.resume_intelligence import ResumeIntelligenceService

User = get_user_model()

def get_memory_usage():
    gc.collect()
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # in MB

def create_scanned_pdf(output_path, img_path):
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, filename=img_path)
    doc.save(output_path)
    doc.close()

def create_password_protected_pdf(output_path):
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Secret Resume Content")
    doc.save(output_path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="password")
    doc.close()

def create_corrupted_pdf(output_path):
    with open(output_path, "wb") as f:
        f.write(b"%PDF-1.4\n%...\nthis is completely corrupted garbage data not a real PDF")

def main():
    print("====================================================")
    print("      PRODUCTION VERIFICATION & BENCHMARK SUITE     ")
    print("====================================================")
    
    # Pre-generate dynamic test files
    os.makedirs("scratch", exist_ok=True)
    scanned_pdf_path = f"scratch/scanned_pdf_{os.getpid()}.pdf"
    pw_pdf_path = f"scratch/password_protected_{os.getpid()}.pdf"
    corrupted_pdf_path = f"scratch/corrupted_resume_{os.getpid()}.pdf"
    
    create_scanned_pdf(scanned_pdf_path, "static/img/logo.png")
    create_password_protected_pdf(pw_pdf_path)
    create_corrupted_pdf(corrupted_pdf_path)
    
    # Quick connectivity/validity check for OpenAI
    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
    if api_key:
        print("Checking OpenAI API connectivity and key validity (timeout 3.0s)...")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            client.models.list(timeout=3.0)
            print("  OpenAI API is reachable and key is valid.")
        except Exception as e:
            print(f"  OpenAI API check failed: {e}. Disabling OpenAI for benchmarking to avoid long timeouts.")
            if hasattr(settings, "OPENAI_API_KEY"):
                settings.OPENAI_API_KEY = ""
            os.environ["OPENAI_API_KEY"] = ""
            # Re-initialize singletons
            AIService._openai_client = None
            
    # Create test user for saving
    test_user, _ = User.objects.get_or_create(
        email="benchmark_test@example.com",
        defaults={"role": "CANDIDATE", "is_active": True}
    )
    test_user.set_unusable_password()
    test_user.save()

    results = {}

    # Check 1: Startup RAM usage
    startup_ram = get_memory_usage()
    print(f"[METRIC] Startup RAM usage: {startup_ram:.2f} MB")
    results['startup_ram'] = startup_ram

    # Check 4: Confirm OCR and spaCy models are NOT loaded during Django startup
    print("\n--- Check 4: Verifying models NOT loaded on Django startup ---")
    nlp_instance = NLPService()
    ocr_instance = OCRService()
    ai_instance = AIService()
    
    spacy_loaded_startup = nlp_instance._nlp is not None
    paddle_loaded_startup = ocr_instance._paddle_ocr is not None
    easyocr_loaded_startup = ocr_instance._easyocr_reader is not None
    
    print(f"spaCy NLP model loaded: {spacy_loaded_startup}")
    print(f"PaddleOCR model loaded: {paddle_loaded_startup}")
    print(f"EasyOCR Reader loaded: {easyocr_loaded_startup}")
    
    results['spacy_loaded_startup'] = spacy_loaded_startup
    results['paddle_loaded_startup'] = paddle_loaded_startup
    results['easyocr_loaded_startup'] = easyocr_loaded_startup

    # Check 6 & 7: Verify singletons are reused & check for duplicate instances
    print("\n--- Check 6 & 7: Verifying Singletons & duplicate instances ---")
    nlp_instance_2 = NLPService()
    ocr_instance_2 = OCRService()
    ai_instance_2 = AIService()
    
    nlp_singleton_ok = nlp_instance is nlp_instance_2
    ocr_singleton_ok = ocr_instance is ocr_instance_2
    ai_singleton_ok = ai_instance is ai_instance_2
    
    print(f"NLPService Singleton Reused: {nlp_singleton_ok} (IDs: {id(nlp_instance)} vs {id(nlp_instance_2)})")
    print(f"OCRService Singleton Reused: {ocr_singleton_ok} (IDs: {id(ocr_instance)} vs {id(ocr_instance_2)})")
    print(f"AIService Singleton Reused: {ai_singleton_ok} (IDs: {id(ai_instance)} vs {id(ai_instance_2)})")
    
    results['nlp_singleton_ok'] = nlp_singleton_ok
    results['ocr_singleton_ok'] = ocr_singleton_ok
    results['ai_singleton_ok'] = ai_singleton_ok

    # Check 5: Confirm OCR loads only on first parsing request
    print("\n--- Check 5: Verifying models load only on first parsing request ---")
    first_resume_path = "scratch/rajeev_kumar_resume.pdf"
    
    t0 = time.time()
    ram_before_first = get_memory_usage()
    print(f"Memory before first parse: {ram_before_first:.2f} MB")
    
    # Run first parse
    with open(first_resume_path, "rb") as f:
        profile, status = process_resume_file(f, os.path.basename(first_resume_path), user=test_user)
        
    first_parse_time = time.time() - t0
    ram_after_first = get_memory_usage()
    
    # Re-check model loading status
    spacy_loaded_after = nlp_instance._nlp is not None
    paddle_loaded_after = ocr_instance._paddle_ocr is not None or ocr_instance._easyocr_reader is not None or ocr_instance.is_tesseract_available()
    
    print(f"First Parse Time: {first_parse_time:.2f}s (Status: {status})")
    print(f"Memory after first parse: {ram_after_first:.2f} MB (Delta: {ram_after_first - ram_before_first:.2f} MB)")
    print(f"spaCy NLP model loaded after first parse: {spacy_loaded_after}")
    print(f"OCR models loaded/checked after first parse: {paddle_loaded_after}")
    
    results['ram_before_first'] = ram_before_first
    results['ram_after_first'] = ram_after_first
    results['first_parse_time'] = first_parse_time
    results['spacy_loaded_after'] = spacy_loaded_after
    results['paddle_loaded_after'] = paddle_loaded_after

    # Run second parse to measure time delta (reusing cached singletons)
    print("\n--- Measuring Second Parse Time (using cached models) ---")
    second_resume_path = "scratch/rohan_kumar_resume.pdf"
    t0 = time.time()
    with open(second_resume_path, "rb") as f:
        profile2, status2 = process_resume_file(f, os.path.basename(second_resume_path), user=test_user)
    second_parse_time = time.time() - t0
    print(f"Second Parse Time: {second_parse_time:.2f}s (Status: {status2})")
    results['second_parse_time'] = second_parse_time

    # Check 3: Measure RAM after uploading 20 resumes
    print("\n--- Check 3: Measuring RAM after uploading 20 resumes ---")
    resumes_to_cycle = [
        # 10 digital resumes
        "scratch/rajeev_kumar_resume.pdf",
        "scratch/rohan_kumar_resume.pdf",
        "scratch/harneet_resume.pdf",
        "scratch/shreya_chavda_resume.pdf",
        "scratch/vikke_gupta_Naukri_HARNEETSINGHCHHABRA16y_0m.pdf",
        "scratch/vikke_gupta_Naukri_VikkeGupta16y_0m.pdf",
        "scratch/rajeev_kumar_resume.pdf",
        "scratch/rohan_kumar_resume.pdf",
        "scratch/harneet_resume.pdf",
        "scratch/shreya_chavda_resume.pdf",
        # 10 scanned resumes
        scanned_pdf_path,
        scanned_pdf_path,
        scanned_pdf_path,
        scanned_pdf_path,
        scanned_pdf_path,
        scanned_pdf_path,
        scanned_pdf_path,
        scanned_pdf_path,
        scanned_pdf_path,
        scanned_pdf_path
    ]
    
    ram_history = [ram_after_first]
    parse_times = []
    
    mock_llm_data = {
        "personal_info": {
            "name": "Benchmark Candidate",
            "email": "candidate_bench@example.com",
            "phone": "9999999999",
            "location": "New Delhi, India",
            "current_company": "Tech Corp",
            "current_designation": "Software Engineer",
            "total_experience": 3.5,
            "linkedin_url": "https://linkedin.com/in/benchmark",
            "portfolio_url": "https://benchmark.portfolio"
        },
        "summary": "Experienced software engineer specializing in backend development and system architecture.",
        "skills": ["Python", "Django", "PostgreSQL", "Redis", "Docker"],
        "experience": [
            {
                "company": "Tech Corp",
                "designation": "Software Engineer",
                "start_date": "2023-01-01",
                "end_date": "None",
                "description": "Building enterprise-grade resume parsers and application tracking systems.",
                "is_current": True
            }
        ],
        "education": [
            {
                "institution": "Technical University",
                "degree": "Bachelor of Technology",
                "field_of_study": "Computer Science",
                "score": "8.5 CGPA",
                "start_date": "2019-08-01",
                "end_date": "2023-06-01"
            }
        ]
    }

    parse_statuses = []
    from unittest.mock import patch
    with patch('apps.candidates.utils.OpenAIResumeParser.parse', return_value=mock_llm_data):
        for i in range(1, 21):
            file_path = resumes_to_cycle[(i - 1) % len(resumes_to_cycle)]
            t_start = time.time()
            with open(file_path, "rb") as f:
                p, s = process_resume_file(f, f"run_{i}_{os.path.basename(file_path)}", user=test_user)
            elapsed = time.time() - t_start
            parse_times.append(elapsed)
            parse_statuses.append(s)
            current_ram = get_memory_usage()
            ram_history.append(current_ram)
            print(f"Upload #{i}: parsed {os.path.basename(file_path)} in {elapsed:.2f}s (Status: {s}). RAM: {current_ram:.2f} MB")

        peak_ram = max(ram_history)
        avg_ram = sum(ram_history) / len(ram_history)
        final_ram = ram_history[-1]
        
        avg_time = sum(parse_times) / len(parse_times)
        max_time = max(parse_times)
        successes = sum(1 for status in parse_statuses if "SUCCESS" in status or "PARTIAL_SUCCESS" in status)
        success_rate = (successes / len(parse_statuses)) * 100.0

        print(f"\n[SUMMARY 20 RESUMES]")
        print(f"Peak RAM: {peak_ram:.2f} MB")
        print(f"Average RAM: {avg_ram:.2f} MB")
        print(f"Final RAM after 20 parses: {final_ram:.2f} MB")
        print(f"Average Parsing Time: {avg_time:.2f}s")
        print(f"Max Parsing Time: {max_time:.2f}s")
        print(f"Success Rate: {success_rate:.1f}%")
        
        results['peak_ram'] = peak_ram
        results['avg_ram'] = avg_ram
        results['final_ram'] = final_ram
        results['avg_parsing_time'] = avg_time
        results['max_parsing_time'] = max_time
        results['success_rate'] = success_rate

        # Check 8: Test parsing with diverse formats
        print("\n--- Check 8: Testing parsing on diverse formats ---")
        format_tests = {
            "image PDF (scanned)": scanned_pdf_path,
            "scanned PDF": scanned_pdf_path,
            "DOCX": "media/resumes/original/original_zip_resume.docx",
            "DOC": "media/resumes/original/TUSHAR__RESUME___2026_1.doc",
            "image only (PNG)": "media/uploads/screenshot_resume.png",
            "multi-page PDF": "scratch/rajeev_kumar_resume.pdf",
            "password protected PDF": pw_pdf_path,
            "corrupted PDF": corrupted_pdf_path,
            "resume with tables": "scratch/rajeev_kumar_resume.pdf",
            "resume with icons": "scratch/harneet_resume.pdf",
            "resume with two columns": "scratch/shreya_chavda_resume.pdf"
        }
        
        format_results = []
        for label, path in format_tests.items():
            if not os.exists(path) if hasattr(os, "exists") else not os.path.exists(path):
                print(f"Skipping {label} (File not found: {path})")
                continue
                
            print(f"Testing {label} from {path}...")
            try:
                with open(path, "rb") as f:
                    pipeline = ResumeParsingPipeline(f, os.path.basename(path), user=test_user)
                    profile_obj, status_str = pipeline.run()
                    extracted_name = profile_obj.full_name if profile_obj else "None"
                    
                    print(f"  Result: {status_str} | Name: {extracted_name}")
                    format_results.append({
                        "format": label,
                        "file": path,
                        "status": status_str,
                        "extracted_name": extracted_name
                    })
            except Exception as e:
                print(f"  Result: Crashed/Threw Exception: {e}")
                format_results.append({
                    "format": label,
                    "file": path,
                    "status": f"EXCEPTION: {str(e)}",
                    "extracted_name": "None"
                })
                
        results['format_results'] = format_results

    # Output JSON file with raw results
    with open("scratch/verification_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nVerification suite completed. JSON results written to scratch/verification_results.json")

if __name__ == "__main__":
    main()
