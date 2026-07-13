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

candidates = CandidateProfile.objects.all()
print(f"Total candidates: {candidates.count()}")
for c in candidates:
    name_clean = (c.full_name or "").encode('ascii', errors='ignore').decode('ascii')
    designation_clean = (c.current_designation or "").encode('ascii', errors='ignore').decode('ascii')
    print(f"Name: {name_clean} | Designation: {designation_clean} | Exp: {c.total_experience}")
