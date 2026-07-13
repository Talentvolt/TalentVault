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

candidates = CandidateProfile.objects.filter(ats_score__gte=10, ats_score__lte=15)
print(f"Candidates with ATS score between 10 and 15: {candidates.count()}")
for c in candidates:
    name_clean = (c.full_name or "").encode('ascii', errors='ignore').decode('ascii')
    email_clean = (c.user.email or "").encode('ascii', errors='ignore').decode('ascii')
    print(f"Name: {name_clean} | Email: {email_clean} | ATS Score: {c.ats_score}")
