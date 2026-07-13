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
from apps.jobs.models import Job
from services.candidate_matching_service import CandidateMatchingService

candidates = CandidateProfile.objects.all()
jobs = Job.objects.all()

print(f"Candidates: {candidates.count()}, Jobs: {jobs.count()}")

for j in jobs:
    print(f"\n==================================================")
    print(f"JOB: {j.title} (ID: {j.id})")
    print(f"Skills: {list(j.skills.values_list('skill_name', flat=True))}")
    print(f"==================================================")
    for c in candidates:
        analysis = CandidateMatchingService.calculate_job_ats_score(c, j)
        score = analysis['total_score']
        if score > 0:
            name_clean = (c.full_name or "").encode('ascii', errors='ignore').decode('ascii')
            email_clean = (c.user.email or "").encode('ascii', errors='ignore').decode('ascii')
            print(f"Candidate: {name_clean} ({email_clean}) | Score: {score}%")
            print(f"  Breakdown: Skills={analysis['skills_score']} (Ratio: {analysis['skills_ratio']}), Exp={analysis['experience_score']}, Edu={analysis['education_score']}, Keyword={analysis['keyword_score']} (Ratio: {analysis['keyword_ratio']}), Loc={analysis['location_score']}, Certs={analysis['certifications_score']}, Comp={analysis['completeness_score']}")
