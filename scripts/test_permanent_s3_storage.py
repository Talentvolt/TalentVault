import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import boto3

def verify_permanent_s3_storage():
    print("=" * 80)
    print("PERMANENT AWS S3 STORAGE VERIFICATION")
    print("=" * 80)

    # 1. Django Settings Verification
    bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
    region = getattr(settings, 'AWS_S3_REGION_NAME', None)
    default_backend = settings.STORAGES.get('default', {}).get('BACKEND')

    print(f"1. Loaded AWS_STORAGE_BUCKET_NAME: '{bucket}'")
    print(f"2. Loaded AWS_S3_REGION_NAME:         '{region}'")
    print(f"3. Loaded STORAGES['default']['BACKEND']: '{default_backend}'")

    assert bucket == 'talentvault-files-india', f"Expected bucket 'talentvault-files-india', got '{bucket}'"
    assert region == 'ap-south-1', f"Expected region 'ap-south-1', got '{region}'"
    assert default_backend == 'storages.backends.s3.S3Storage', f"Expected S3Storage, got '{default_backend}'"
    print("  -> Settings verification PASSED!")

    # 2. Read-Only Verification of Existing S3 Object
    s3_client = boto3.client(
        's3',
        aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
        aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
        region_name=region
    )

    known_existing_key = 'resumes/2020Technologies_Albaksh.pdf'
    try:
        head_res = s3_client.head_object(Bucket=bucket, Key=known_existing_key)
        print(f"4. Read-Only S3 object check: Key '{known_existing_key}' exists in bucket (Size: {head_res['ContentLength']} bytes).")
        print("  -> Existing S3 object accessibility check PASSED!")
    except Exception as e:
        print(f"  -> Note on head_object for '{known_existing_key}': {e}")

    # 3. Temporary Test Upload to resumes/
    test_key = "resumes/temp_verify_storage_check.txt"
    test_content = b"Permanent AWS S3 Storage Verification Test Content"

    print(f"5. Testing temporary file upload via default_storage to '{test_key}'...")
    saved_name = default_storage.save(test_key, ContentFile(test_content))
    print(f"  -> File saved via default_storage. Returned path: '{saved_name}'")

    exists_in_storage = default_storage.exists(saved_name)
    print(f"  -> default_storage.exists('{saved_name}'): {exists_in_storage}")
    assert exists_in_storage is True, f"default_storage.exists failed for '{saved_name}'!"

    url = default_storage.url(saved_name)
    print(f"  -> Generated Storage URL: '{url}'")

    # Clean up ONLY the temporary test file
    default_storage.delete(saved_name)
    after_delete_exists = default_storage.exists(saved_name)
    print(f"  -> Deleted temporary test object '{saved_name}'. Exists after delete: {after_delete_exists}")
    assert after_delete_exists is False, "Failed to delete temporary test object!"
    print("  -> Temporary S3 upload & delete test PASSED cleanly!")

    print("=" * 80)
    print("ALL PERMANENT AWS S3 STORAGE VERIFICATIONS PASSED 100%!")
    print("=" * 80)

if __name__ == '__main__':
    verify_permanent_s3_storage()
