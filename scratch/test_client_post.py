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

from django.test import Client
from apps.accounts.models import User
from django.urls import reverse
from apps.candidates.models import CandidateProfile

test_email = "mauryaraman13@gmail.com"
User.objects.filter(email=test_email).delete()

# Create a recruiter user to authenticate the client
user = User.objects.filter(email="recruiter@example.com").first()
if not user:
    user = User.objects.create_user(email="recruiter@example.com", password="password123", role=User.Role.RECRUITER)

c = Client()
c.force_login(user)

pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Resume_Ramanjeet.pdf')
print("Uploading via Client from:", pdf_path)
with open(pdf_path, 'rb') as f:
    response = c.post(reverse('frontend:resume_parser'), {'resume': f})

print("Response status code:", response.status_code)
for chunk in response.streaming_content:
    chunk_str = chunk.decode('utf-8', errors='ignore').strip()
    if chunk_str:
        print("Progress Chunk:", chunk_str[:150])

profile = CandidateProfile.objects.filter(user__email=test_email).first()
if profile:
    print("Success! Profile created with ID:", profile.id)
    print("Resume filename on storage:", profile.resume.name)
    try:
        print("Resume size on storage:", profile.resume.size)
    except Exception as e:
        print("Error getting size:", e)
else:
    print("No profile created.")
