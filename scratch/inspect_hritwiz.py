import os
import sys
import django
import fitz
from dotenv import load_dotenv

# Load env
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.models import CandidateProfile

c = CandidateProfile.objects.filter(full_name__icontains="Hritwiz").first()
if c:
    print(f"Name: {c.full_name}")
    print(f"Designation: {c.current_designation}")
    print(f"Total Experience: {c.total_experience}")
    print(f"Skills: {list(c.skills.values_list('skill_name', flat=True))}")
    print(f"Summary: {c.summary}")
    print(f"Educations: {list(c.educations.values_list('degree', flat=True))}")
    if c.resume:
        try:
            with c.resume.open('rb') as f:
                doc = fitz.open(stream=f.read(), filetype="pdf")
                text = " ".join([page.get_text() for page in doc])
                print(f"Resume text (first 1000 chars): {text[:1000]}")
        except Exception as e:
            print("Error reading resume:", e)
else:
    print("Hritwiz not found")
