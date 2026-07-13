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

candidates = CandidateProfile.objects.filter(
    user__email__in=[
        "ankitkumarkh31@gmail.com",
        "vishantch6@gmail.com",
        "govindchavan0610@gmail.com",
        "mauryaraman13@gmail.com",
        "tushsharma201995@gmail.com"
    ]
)

jobs = Job.objects.filter(title__icontains="AI Engineer") | Job.objects.filter(title__icontains="Laravel")

for j in jobs:
    print(f"\n==================================================")
    print(f"JOB: {j.title}")
    print(f"==================================================")
    for c in candidates:
        analysis = CandidateMatchingService.calculate_job_ats_score(c, j)
        name_clean = (c.full_name or "").encode('ascii', errors='ignore').decode('ascii')
        print(f"Candidate: {name_clean} | Score: {analysis['total_score']}%")
        print(f"  Skills: {analysis['skills_score']} (Ratio: {analysis['skills_ratio']})")
        print(f"  Exp: {analysis['experience_score']} | Edu: {analysis['education_score']} | Keyword: {analysis['keyword_score']} (Ratio: {analysis['keyword_ratio']})")
        print(f"  Loc: {analysis['location_score']} | Certs: {analysis['certifications_score']} | Comp: {analysis['completeness_score']}")
        print(f"  Title Score: {analysis['title_score']} | AI Semantic Score: {analysis['ai_semantic_score']}")
