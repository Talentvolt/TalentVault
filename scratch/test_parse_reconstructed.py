import os
import sys
import django
import json
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env variables from .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from services.resume_intelligence import ResumeIntelligenceService

with open("scratch/harneet_layout_aware.txt", "r", encoding="utf-8") as f:
    # Wait, layout_aware is page-by-page. Let's read column_concatenated:
    pass

with open("scratch/harneet_column_concatenated.txt", "r", encoding="utf-8") as f:
    text = f.read()

parsed = ResumeIntelligenceService.parse_resume_nlp(text)
improved = ResumeIntelligenceService.ai_improve_resume_data(parsed)

print(f"EXPERIENCES COUNT: {len(improved['experience'])}")
for idx, exp in enumerate(improved['experience']):
    print(f"\n{idx+1}.")
    print(f"Designation: {exp['designation']}")
    print(f"Company: {exp['company']}")
    print(f"Dates: {exp['start_date']} to {exp['end_date']}")
    print(f"Duration: {exp.get('duration')}")
    print(f"Description:\n{exp['description']}")

print(f"\nEDUCATION COUNT: {len(improved['education'])}")
for idx, edu in enumerate(improved['education']):
    print(f"\n{idx+1}.")
    print(f"Degree: {edu['degree']}")
    print(f"Institution: {edu['institution']}")
    print(f"Dates: {edu['start_date']} to {edu['end_date']}")

print(f"\nSKILLS: {improved['skills']}")
print(f"\nPROJECTS: {improved['projects']}")
