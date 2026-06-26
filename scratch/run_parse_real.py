import os
import sys
import json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from services.resume_intelligence import ResumeIntelligenceService
from apps.candidates.utils import extract_profile_photo

def test_resume(pdf_path, filename):
    print("=" * 60)
    print(f"TESTING FILE: {pdf_path}")
    print("=" * 60)
    
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found!")
        return
        
    with open(pdf_path, 'rb') as f:
        file_bytes = f.read()
        
    ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, filename)
    print(f"OCR Engine used: {ocr_result['engine']}")
    print(f"OCR Confidence: {ocr_result['confidence']}%")
    print(f"Largest bold name: {ocr_result.get('largest_bold_name')}")
    
    parsed = ResumeIntelligenceService.parse_resume_nlp(ocr_result['text'], parsed_name=ocr_result.get('largest_bold_name'))
    improved = ResumeIntelligenceService.ai_improve_resume_data(parsed)
    
    print("\n--- PARSED INFO ---")
    print(f"Candidate Name:       {improved['personal_info']['name']}")
    print(f"Current Designation:  {improved['personal_info']['current_designation']}")
    print(f"Current Company:      {improved['personal_info']['current_company']}")
    print(f"Total Experience:     {improved['personal_info']['total_experience']} years")
    print(f"Email:                {improved['personal_info']['email']}")
    print(f"Phone:                {improved['personal_info']['phone']}")
    print(f"Location:             {improved['personal_info']['location']}")
    
    print("\n--- EXPERIENCES ---")
    for idx, exp in enumerate(improved['experience']):
        print(f"{idx+1}. {exp['designation']} at {exp['company']} ({exp['start_date']} to {exp['end_date']}) - {exp['duration']}")
        
    print("\n--- EDUCATION ---")
    for idx, edu in enumerate(improved['education']):
        print(f"{idx+1}. {edu['degree']} from {edu['institution']} ({edu['start_date']} to {edu['end_date']})")
        
    photo_bytes, photo_ext = extract_profile_photo(file_bytes, filename)
    if photo_bytes:
        print(f"\nProfile Photo: EXTRACTED SUCCESSFULLY! Ext: {photo_ext}, Size: {len(photo_bytes)} bytes")
    else:
        print("\nProfile Photo: NOT EXTRACTED.")

if __name__ == '__main__':
    test_resume("scratch/shreya_chavda_Shreya_ZdEAJej.pdf", "shreya_chavda_Shreya_ZdEAJej.pdf")
    test_resume("scratch/vikke_gupta_Naukri_VikkeGupta16y_0m.pdf", "vikke_gupta_Naukri_VikkeGupta16y_0m.pdf")
