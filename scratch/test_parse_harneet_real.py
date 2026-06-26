import os
import sys
import django
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env variables from .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.utils import process_resume_file
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile

test_email = "harneet001.2009@gmail.com"
User.objects.filter(email=test_email).delete()

pdf_path = os.path.join(os.path.dirname(__file__), 'harneet_resume.pdf')
print("Testing with file:", pdf_path)

with open(pdf_path, 'rb') as f:
    profile, status = process_resume_file(f, 'harneet_resume.pdf', overwrite=True)
    
print("Result Status:", status)
if profile:
    print(f"Success! Profile ID: {profile.id}")
    print(f"Full Name: {profile.full_name}")
    print(f"Email: {profile.user.email}")
    print(f"Phone: {profile.user.phone_number}")
    print(f"Skills: {[s.skill_name for s in profile.skills.all()]}")
    print("\n--- DATABASE EXPERIENCE ENTRIES ---")
    for exp in profile.experiences.all().order_by('-start_date'):
         print(f"Role: {exp.designation} | Company: {exp.company_name}")
         print(f"Period: {exp.start_date} to {exp.end_date}")
         print(f"Description:\n{exp.description}")
         print("-" * 40)
    print("\n--- DATABASE EDUCATION ENTRIES ---")
    for edu in profile.educations.all().order_by('-start_date'):
         print(f"Degree: {edu.degree} | Inst: {edu.institution}")
         print(f"Period: {edu.start_date} to {edu.end_date}")
         print("-" * 40)
    print("\n--- DATABASE PROJECTS ENTRIES ---")
    for proj in profile.projects.all():
         print(f"Title: {proj.title}")
         print(f"Desc: {proj.description}")
         print("-" * 40)
else:
    print("Failed to create profile.")
