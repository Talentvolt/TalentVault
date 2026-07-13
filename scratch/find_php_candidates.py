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

candidates = CandidateProfile.objects.all()

for c in candidates:
    # Read text from resume if possible
    text = ""
    if c.resume:
        try:
            with c.resume.open('rb') as f:
                doc = fitz.open(stream=f.read(), filetype="pdf")
                text = " ".join([page.get_text() for page in doc]).lower()
        except Exception:
            pass
            
    cand_text = f"{(c.full_name or '')} {(c.summary or '')} {(c.current_designation or '')} {text}".lower()
    if 'laravel' in cand_text or 'php' in cand_text:
        name_clean = (c.full_name or "").encode('ascii', errors='ignore').decode('ascii')
        print(f"\n==========================================")
        print(f"Name: {name_clean} | Email: {c.user.email}")
        print(f"Designation: {c.current_designation}")
        print(f"Skills: {list(c.skills.values_list('skill_name', flat=True))}")
        print(f"Laravel in text: {'laravel' in cand_text} | PHP in text: {'php' in cand_text}")
