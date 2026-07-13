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

try:
    print(f"Listing all files in bucket '{bucket_name}' under 'resumes/':")
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix="resumes/")
    
    count = 0
    small_count = 0
    large_count = 0
    
    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                count += 1
                key = obj['Key']
                size = obj['Size']
                if size < 1000:
                    small_count += 1
                    print(f"  [SMALL] Key: {key} | Size: {size} bytes")
                else:
                    large_count += 1
                    print(f"  [LARGE] Key: {key} | Size: {size} bytes")
        else:
            print("No files found under resumes/")
            
    print(f"\nSummary: {count} total files. {small_count} small files (<1KB), {large_count} large files (>=1KB).")
except Exception as e:
    print("Error listing objects:", e)
