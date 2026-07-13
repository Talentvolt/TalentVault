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
from apps.applications.models import Application
from services.candidate_matching_service import CandidateMatchingService

profile = CandidateProfile.objects.filter(user__email="ankitkumarkh31@gmail.com").first()
ai_job = Job.objects.filter(title__icontains="AI Engineer").first()

if not profile or not ai_job:
    print("Error: Candidate or Job not found!")
    sys.exit(1)

# Clean existing applications for this candidate to start fresh
Application.objects.filter(candidate=profile).delete()

# Create Application record
app = Application.objects.create(
    candidate=profile,
    job=ai_job,
    stage='OPEN',
    is_active=True
)
print(f"Created application: {app.id}")

# Run update_ats_scores
print("Running update_ats_scores...")
CandidateMatchingService.update_ats_scores(candidate_id=profile.id, job_id=ai_job.id)

# Fetch from DB and verify
app.refresh_from_db()
profile.refresh_from_db()

print(f"\n--- DATABASE VERIFICATION ---")
print(f"Application Match Score in DB: {app.match_score}%")
print(f"Candidate Profile ATS Score in DB: {profile.ats_score}%")

assert int(app.match_score) == 68, f"Expected 68%, got {app.match_score}%"
assert profile.ats_score == 68, f"Expected 68%, got {profile.ats_score}%"
print("\nSUCCESS: All database fields verified successfully!")
