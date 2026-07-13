import os
import sys
import django
import hashlib
import boto3
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from dotenv import load_dotenv

# Load Django settings
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.utils import handle_resume_upload
from apps.candidates.models import CandidateProfile
from apps.accounts.models import User

# Path to the test PDF
pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Resume_Ramanjeet.pdf')
filename = "Resume_Ramanjeet.pdf"

# Clean up database first
test_email = "mauryaraman13@gmail.com"
User.objects.filter(email=test_email).delete()

# 1. Log original file stats
with open(pdf_path, 'rb') as f:
    orig_bytes = f.read()
orig_size = len(orig_bytes)
orig_sha = hashlib.sha256(orig_bytes).hexdigest()

print(f"--- Original File Info ---")
print(f"Original Filename: {filename}")
print(f"Original File Size: {orig_size} bytes")
print(f"Original SHA256: {orig_sha}")

# 2. Perform the upload
uploaded_file = SimpleUploadedFile(filename, orig_bytes, content_type="application/pdf")

# We will print values in handle_resume_upload flow
print("\n--- Running handle_resume_upload() ---")
results = handle_resume_upload(uploaded_file, overwrite=True)

# Find the profile created
profile = CandidateProfile.objects.filter(user__email=test_email).first()
if not profile:
    print("Error: Candidate profile not created!")
    sys.exit(1)

print("\n--- Upload Log Details ---")
# Get saved file details
saved_file = profile.resume
print(f"S3 Object Key: {saved_file.name}")
print(f"Returned URL: {saved_file.url}")

# Size according to Django/S3 Storage
s3_size = saved_file.size
print(f"Final S3 Object Size (reported by storage): {s3_size} bytes")

# 3. Download the object back from S3 using boto3
aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
bucket_name = os.environ.get("AWS_STORAGE_BUCKET_NAME")
region_name = os.environ.get("AWS_S3_REGION_NAME")

s3_client = boto3.client(
    's3',
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name=region_name
)

print("\n--- Downloading S3 Object for Verification ---")
response = s3_client.get_object(Bucket=bucket_name, Key=saved_file.name)
downloaded_bytes = response['Body'].read()
dl_size = len(downloaded_bytes)
dl_sha = hashlib.sha256(downloaded_bytes).hexdigest()

print(f"Downloaded Size: {dl_size} bytes")
print(f"Downloaded SHA256: {dl_sha}")

if orig_sha == dl_sha:
    print("\nSUCCESS: SHA256 hashes MATCH perfectly! The file was uploaded to S3 without any corruption.")
else:
    print("\nFAILURE: SHA256 hashes MISMATCH! The file became corrupted.")
