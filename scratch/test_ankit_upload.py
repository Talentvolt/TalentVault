import os
import sys
import django
from django.core.files.uploadedfile import SimpleUploadedFile
from dotenv import load_dotenv

# Load env
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from apps.jobs.models import Job
from apps.candidates.utils import handle_resume_upload
from services.candidate_matching_service import CandidateMatchingService

test_email = "ankitkumarkh31@gmail.com"
User.objects.filter(email=test_email).delete()

pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Ankit_Web__development.pdf')
with open(pdf_path, 'rb') as f:
    pdf_bytes = f.read()

uploaded_file = SimpleUploadedFile("Ankit_Web__development.pdf", pdf_bytes, content_type="application/pdf")
print("Uploading resume...")
results = handle_resume_upload(uploaded_file, overwrite=True)

profile = CandidateProfile.objects.filter(user__email=test_email).first()
if not profile:
    print("Error: Candidate profile not created!")
    sys.exit(1)

print(f"Created candidate: {profile.full_name}")
print(f"Designation: {profile.current_designation}")
print(f"Parsed Skills: {list(profile.skills.values_list('skill_name', flat=True))}")

ai_job = Job.objects.filter(title__icontains="AI Engineer").first()
if ai_job:
    print(f"\nCalculating ATS score for {profile.full_name} against {ai_job.title}...")
    analysis = CandidateMatchingService.calculate_job_ats_score(profile, ai_job)
    for k, v in analysis.items():
        print(f"  {k}: {v}")
else:
    print("AI Engineer job not found!")
