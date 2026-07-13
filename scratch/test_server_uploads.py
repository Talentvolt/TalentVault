import os
import sys
import requests
import hashlib
import boto3
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load env variables from .env
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

LOCAL_URL = "http://127.0.0.1:8000"
EMAIL = "growfluencestudio@gmail.com"
PASSWORD = "TalentVault2026!"

session = requests.Session()

# 1. Log in
login_url = f"{LOCAL_URL}/accounts/login/"
print(f"GET {login_url}")
resp = session.get(login_url)
soup = BeautifulSoup(resp.text, 'html.parser')
csrf_token = soup.find('input', {'name': 'csrfmiddlewaretoken'})['value']

print(f"Post Login with {EMAIL}...")
login_data = {
    'email': EMAIL,
    'password': PASSWORD,
    'csrfmiddlewaretoken': csrf_token
}
resp_login = session.post(login_url, data=login_data, headers={'Referer': login_url})
if "dashboard" not in resp_login.url:
    print("Login to local server failed!")
    sys.exit(1)
print("Logged in successfully.")

# Initialize Django to delete the existing candidate records so they are not detected as duplicates
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile

test_emails = ["mauryaraman13@gmail.com", "harneet.singh@example.com", "harneetchhabra19@gmail.com"]
for test_email in test_emails:
    User.objects.filter(email__icontains=test_email.split('@')[0]).delete()

# 2. Upload two resumes
resumes_to_upload = [
    {
        "filename": "Resume_Ramanjeet.pdf",
        "path": os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Resume_Ramanjeet.pdf')
    },
    {
        "filename": "harneet_resume.pdf",
        "path": os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'harneet_resume.pdf')
    }
]

for item in resumes_to_upload:
    path = item["path"]
    filename = item["filename"]
    print(f"\n--- Uploading: {filename} ---")
    
    # Read original file stats
    with open(path, 'rb') as f:
        orig_bytes = f.read()
    orig_size = len(orig_bytes)
    orig_sha = hashlib.sha256(orig_bytes).hexdigest()
    print(f"Original size: {orig_size} bytes | SHA256: {orig_sha}")
    
    # Get CSRF for resume parser
    parser_page = session.get(f"{LOCAL_URL}/resume-parser/")
    parser_soup = BeautifulSoup(parser_page.text, 'html.parser')
    parser_csrf = parser_soup.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    
    # Post upload
    files = {'resume': (filename, open(path, 'rb'), 'application/pdf')}
    data = {'csrfmiddlewaretoken': parser_csrf}
    
    upload_resp = session.post(f"{LOCAL_URL}/resume-parser/", data=data, files=files)
    print("Upload POST Response code:", upload_resp.status_code)
    
    candidate_id = None
    for line in upload_resp.iter_lines():
        if line:
            line_str = line.decode('utf-8').strip()
            print("  Progress:", line_str[:150])
            if '"stage": "completed"' in line_str:
                import json
                try:
                    res_json = json.loads(line_str)
                    candidate_id = res_json.get("candidate_id")
                except Exception:
                    pass
                    
    if not candidate_id:
        print(f"ERROR: Upload/parsing for {filename} did not complete successfully.")
        continue
        
    print(f"Candidate created with ID: {candidate_id}")
    
    # Verify S3 details
    profile = CandidateProfile.objects.get(id=candidate_id)
    saved_file = profile.resume
    print(f"S3 Object Key: {saved_file.name}")
    print(f"S3 URL: {saved_file.url}")
    print(f"S3 reported size: {saved_file.size} bytes")
    
    # Download and compare
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
    
    response = s3_client.get_object(Bucket=bucket_name, Key=saved_file.name)
    downloaded_bytes = response['Body'].read()
    dl_size = len(downloaded_bytes)
    dl_sha = hashlib.sha256(downloaded_bytes).hexdigest()
    
    print(f"Downloaded Size: {dl_size} bytes | Downloaded SHA256: {dl_sha}")
    if orig_sha == dl_sha:
        print(f"SUCCESS: {filename} uploaded to S3 and verified perfectly!")
    else:
        print(f"CORRUPTION DETECTED for {filename}!")
