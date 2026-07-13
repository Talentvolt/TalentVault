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
laravel_job = Job.objects.filter(title__icontains="Laravel").first()

if not laravel_job:
    print("Laravel Expert job not found!")
    sys.exit(1)

print(f"JOB: {laravel_job.title}")
print(f"Required Skills: {list(laravel_job.skills.values_list('skill_name', flat=True))}")
print(f"Min Experience: {laravel_job.min_experience}")
print(f"Location: {laravel_job.location} | Remote: {laravel_job.is_remote}")

for c in candidates:
    analysis = CandidateMatchingService.calculate_job_ats_score(c, laravel_job)
    score = analysis['total_score']
    name_clean = (c.full_name or "").encode('ascii', errors='ignore').decode('ascii')
    print(f"Candidate: {name_clean} | Score: {score}% | Skills Score: {analysis['skills_score']} (Ratio: {analysis['skills_ratio']}) | Exp: {analysis['experience_score']} | Edu: {analysis['education_score']} | Keyword: {analysis['keyword_score']} (Ratio: {analysis['keyword_ratio']}) | Loc: {analysis['location_score']} | Cert: {analysis['certifications_score']} | Comp: {analysis['completeness_score']}")
