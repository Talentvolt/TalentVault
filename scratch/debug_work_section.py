import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from services.resume_intelligence import ResumeIntelligenceService

pdf_path = "scratch/harneet_resume.pdf"
with open(pdf_path, 'rb') as f:
    file_bytes = f.read()

ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, "harneet_resume.pdf")
print("--- EXTRACTED TEXT ---")
print(ocr_result["text"][:3000])
