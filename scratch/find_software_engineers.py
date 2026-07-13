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
dev_keywords = ['developer', 'engineer', 'programmer', 'software', 'php', 'laravel', 'python', 'django', 'react', 'javascript', 'node', 'full stack']

for c in candidates:
    candidate_text = f"{(c.full_name or '')} {(c.summary or '')} {(c.current_designation or '')}".lower()
    for skill in c.skills.values_list('skill_name', flat=True):
        candidate_text += f" {skill.lower()}"
        
    matched = [w for w in dev_keywords if w in candidate_text]
    if matched:
        name_clean = (c.full_name or "").encode('ascii', errors='ignore').decode('ascii')
        print(f"Candidate: {name_clean} | Email: {c.user.email} | Designation: {c.current_designation} | Matches: {matched}")
