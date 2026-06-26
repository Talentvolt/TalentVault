import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from services.resume_intelligence import ResumeIntelligenceService

def print_raw_text(pdf_path, filename):
    with open(pdf_path, 'rb') as f:
        file_bytes = f.read()
    ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, filename)
    print("=" * 60)
    print(f"RAW TEXT FOR: {filename}")
    print("=" * 60)
    print(ocr_result['text'])

if __name__ == '__main__':
    print_raw_text("scratch/shreya_chavda_Shreya_ZdEAJej.pdf", "shreya_chavda_Shreya_ZdEAJej.pdf")
