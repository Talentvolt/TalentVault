import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
import django; django.setup()
from services.resume_intelligence import ResumeIntelligenceService

f = open(os.path.join(os.path.dirname(__file__), 'harneet_resume.pdf'), 'rb')
ocr = ResumeIntelligenceService.run_ocr_pipeline(f.read(), 'harneet_resume.pdf')
text = ocr['text']

# Parse
parsed = ResumeIntelligenceService.parse_resume_nlp(text)

# Print experiences
for i, exp in enumerate(parsed['experience']):
    print(f"\n--- Experience {i+1} ---")
    print(f"  designation: {repr(exp['designation'])}")
    print(f"  company: {repr(exp['company'])}")
    print(f"  dates: {exp['start_date']} to {exp['end_date']}")

print(f"\n--- Education ---")
for i, edu in enumerate(parsed['education']):
    print(f"  {i+1}. degree={repr(edu['degree'])}, institution={repr(edu['institution'])}, score={repr(edu['score'])}")

print(f"\n--- Skills ---")
print(parsed['skills'])
