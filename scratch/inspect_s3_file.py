import os
import sys
import boto3
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
bucket_name = os.environ.get("AWS_STORAGE_BUCKET_NAME")
region_name = os.environ.get("AWS_S3_REGION_NAME")

s3 = boto3.client(
    's3',
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name=region_name
)

keys = [
    "resumes/harneet_resume.pdf",
    "resumes/original/original_resume_secure.pdf",
    "resumes/1acd15e34cd642fdb74618ad3c3bd4d0.pdf",
    "resumes/generated/generated_resume.pdf"
]

for key in keys:
    try:
        response = s3.get_object(Bucket=bucket_name, Key=key)
        content = response['Body'].read()
        print(f"\nKey: {key}")
        print(f"Size: {len(content)} bytes")
        print(f"Content: {repr(content)}")
        print(f"Content as string: {content.decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"Error fetching {key}: {e}")
