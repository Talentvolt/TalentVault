import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

import boto3
from django.conf import settings
from apps.candidates.models import CandidateProfile

def investigate():
    print("=" * 90)
    print("READ-ONLY CANDIDATE RESUME RECOVERY INVESTIGATION")
    print("=" * 90)

    bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'talentvault-files-india')
    region_name = getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')
    
    # Initialize boto3 S3 client safely
    s3_client = None
    s3_objects = {}
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            region_name=region_name
        )
        print(f"Connecting to AWS S3 bucket: '{bucket_name}' (region: {region_name})...")
        paginator = s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get('Contents', []):
                key = obj['Key']
                s3_objects[key] = {
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].strftime('%Y-%m-%d %H:%M:%S')
                }
        print(f"Successfully retrieved S3 index. Total S3 objects found: {len(s3_objects)}")
    except Exception as e:
        print(f"AWS S3 connection note/error: {e}")

    # Local Media Directory inspection
    media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))

    candidates = CandidateProfile.objects.exclude(resume='').exclude(resume__isnull=True).order_by('-created_at')
    
    total_with_resume_db = candidates.count()
    print(f"Total CandidateProfile records with resume field in DB: {total_with_resume_db}")
    print("=" * 90)

    count_s3_only = 0
    count_disk_only = 0
    count_both = 0
    count_not_found = 0
    count_ambiguous = 0

    results = []

    for c in candidates:
        candidate_name = c.full_name or (c.user.get_full_name() if c.user else "Unknown Name")
        resume_name = c.resume.name if c.resume else ""
        secure_filename = getattr(c, 'secure_filename', None)
        original_filename = getattr(c, 'original_filename', None)
        
        # Check S3
        s3_found = False
        s3_key_found = None
        s3_meta = None
        
        if resume_name in s3_objects:
            s3_found = True
            s3_key_found = resume_name
            s3_meta = s3_objects[resume_name]
        elif secure_filename and f"resumes/{secure_filename}" in s3_objects:
            s3_found = True
            s3_key_found = f"resumes/{secure_filename}"
            s3_meta = s3_objects[s3_key_found]
        else:
            # Check if basename exists anywhere in S3 index
            base_name = os.path.basename(resume_name) if resume_name else ""
            for k in s3_objects:
                if base_name and os.path.basename(k) == base_name:
                    s3_found = True
                    s3_key_found = k
                    s3_meta = s3_objects[k]
                    break

        # Check Local Disk
        disk_found = False
        disk_path_found = None
        disk_size = None
        
        if resume_name:
            local_path = os.path.join(media_root, resume_name.replace('/', os.sep))
            if os.path.isfile(local_path):
                disk_found = True
                disk_path_found = local_path
                disk_size = os.path.getsize(local_path)
            else:
                # Check directly under media/resumes/
                base_name = os.path.basename(resume_name)
                alt_local = os.path.join(media_root, 'resumes', base_name)
                if os.path.isfile(alt_local):
                    disk_found = True
                    disk_path_found = alt_local
                    disk_size = os.path.getsize(alt_local)

        # Classification
        if s3_found and disk_found:
            classification = "FOUND_IN_BOTH"
            count_both += 1
        elif s3_found:
            classification = "FOUND_IN_S3"
            count_s3_only += 1
        elif disk_found:
            classification = "FOUND_ON_RENDER_DISK"
            count_disk_only += 1
        else:
            classification = "NOT_FOUND"
            count_not_found += 1

        results.append({
            'id': str(c.id),
            'name': candidate_name,
            'email': c.user.email if c.user else 'No Email',
            'resume_name': resume_name,
            'original_filename': original_filename,
            'created_at': c.created_at.strftime('%Y-%m-%d %H:%M:%S') if c.created_at else 'Unknown',
            'classification': classification,
            's3_found': s3_found,
            's3_key': s3_key_found,
            's3_meta': s3_meta,
            'disk_found': disk_found,
            'disk_path': disk_path_found,
            'disk_size': disk_size,
        })

    # Summary Report Output
    print("\n" + "=" * 90)
    print("CLASSIFICATION SUMMARY REPORT (READ-ONLY)")
    print("=" * 90)
    print(f"TOTAL CANDIDATES WITH RESUMES IN DB: {total_with_resume_db}")
    print(f"FOUND IN S3:                         {count_s3_only}")
    print(f"FOUND ON RENDER/LOCAL DISK:          {count_disk_only}")
    print(f"FOUND IN BOTH:                       {count_both}")
    print(f"NOT FOUND:                           {count_not_found}")
    print(f"AMBIGUOUS:                           {count_ambiguous}")
    print("=" * 90)

    print("\nSUMMARY STATS RECORDED SUCCESSFULLY.")

if __name__ == '__main__':
    investigate()
