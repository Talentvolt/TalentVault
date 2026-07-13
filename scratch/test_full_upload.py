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

from apps.candidates.utils import handle_resume_upload
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from django.core.files.uploadedfile import SimpleUploadedFile

test_email = "mauryaraman13@gmail.com"
User.objects.filter(email=test_email).delete()

pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Resume_Ramanjeet.pdf')
print("Testing full upload with file:", pdf_path)

with open(pdf_path, 'rb') as f:
    file_bytes = f.read()

uploaded_file = SimpleUploadedFile('Resume_Ramanjeet.pdf', file_bytes, content_type='application/pdf')

results = handle_resume_upload(uploaded_file, overwrite=True)
print("Upload results:", results)

if results['created']:
    profile = results['created'][0]
    print(f"Profile created: {profile.id}")
    print(f"Resume size on storage: {profile.resume.size}")
else:
    print("Failed to create profile")
