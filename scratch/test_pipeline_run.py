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

test_email = "mauryaraman13@gmail.com"
User.objects.filter(email=test_email).delete()

pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Resume_Ramanjeet.pdf')
print("Testing with file:", pdf_path)

with open(pdf_path, 'rb') as f:
    profile, status = process_resume_file(f, 'Resume_Ramanjeet.pdf', overwrite=False)
    
print("Result Status:", status)
if profile:
    print(f"Success! Profile ID: {profile.id}")
    print(f"Full Name: {profile.full_name}")
    print(f"Email: {profile.user.email}")
    print(f"Phone: {profile.user.phone_number}")
    print("\n--- DATABASE EXPERIENCE ENTRIES ---")
    for exp in profile.experiences.all().order_by('-start_date'):
         print(f"Role: {exp.designation} | Company: {exp.company_name}")
         print(f"Period: {exp.start_date} to {exp.end_date}")
         print(f"Description length: {len(exp.description)} chars")
         print("-" * 40)
else:
    print("Failed to create profile.")
