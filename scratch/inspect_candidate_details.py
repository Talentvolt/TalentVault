import os
import sys
import django
from dotenv import load_dotenv

# Load env
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.models import CandidateProfile

candidates = CandidateProfile.objects.filter(full_name__icontains="Chaudhary") | CandidateProfile.objects.filter(full_name__icontains="Govind")

for c in candidates:
    print(f"\n==========================================")
    print(f"Name: {c.full_name}")
    print(f"Designation: {c.current_designation}")
    print(f"Experience: {c.total_experience} years")
    print(f"Skills: {list(c.skills.values_list('skill_name', flat=True))}")
    print(f"Summary: {c.summary}")
