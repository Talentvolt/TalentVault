import os
import sys
import django
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from services.resume_intelligence import ResumeIntelligenceService

def check_resume(pdf_path, filename, expected_name, email="", linkedin=""):
    if not os.path.exists(pdf_path):
        print(f"File {pdf_path} not found! Skipping...")
        return True
    with open(pdf_path, 'rb') as f:
        file_bytes = f.read()
    ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, filename)
    name = ResumeIntelligenceService.extract_candidate_name(
        ocr_result['text'],
        parsed_name=ocr_result.get("largest_bold_name"),
        email=email,
        linkedin=linkedin
    )
    print(f"File: {filename} -> Extracted Name: {name} | Expected: {expected_name}")
    assert name == expected_name, f"Expected {expected_name}, got {name}"
    return True

def run_tests():
    # 1. Rajeev Kumar mock test (using raw text + email/linkedin validation)
    rajeev_text = "Rajeev Kumar\nEmail: rajeevkumar9801456p@gmail.com\nLinkedIn: linkedin.com/in/rajeev98p/\nExtracurricular Activities\nVolunteer"
    name1 = ResumeIntelligenceService.extract_candidate_name(
        rajeev_text,
        email="rajeevkumar9801456p@gmail.com",
        linkedin="linkedin.com/in/rajeev98p/"
    )
    print(f"Rajeev Kumar (Mock text) -> Extracted Name: {name1}")
    assert name1 == "Rajeev Kumar"
    
    # 2. Harneet Singh Chhabra
    check_resume("scratch/harneet_resume.pdf", "harneet_resume.pdf", "Harneet Singh Chhabra", email="harneet@example.com")
    
    # 3. Shreya Chavda
    check_resume("scratch/shreya_chavda_Shreya_ZdEAJej.pdf", "shreya_chavda_Shreya_ZdEAJej.pdf", "Shreya Chavda", email="shreya.chavda1712@gmail.com")
    
    # 4. Vikke Gupta
    check_resume("scratch/vikke_gupta_Naukri_VikkeGupta16y_0m.pdf", "vikke_gupta_Naukri_VikkeGupta16y_0m.pdf", "Vikke Gupta", email="cavikkegupta@gmail.com")

    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    run_tests()
