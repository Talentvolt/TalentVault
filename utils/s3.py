import os
import logging
import mimetypes
from django.conf import settings

logger = logging.getLogger(__name__)

def get_s3_client():
    """
    Returns an authenticated boto3 S3 client configured for the project bucket.
    """
    import boto3
    from botocore.client import Config
    
    region = getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1') or 'ap-south-1'
    sig_ver = getattr(settings, 'AWS_S3_SIGNATURE_VERSION', 's3v4') or 's3v4'
    
    kwargs = {
        'region_name': region,
        'config': Config(signature_version=sig_ver),
    }
    access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
    secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
    if access_key and secret_key:
        kwargs['aws_access_key_id'] = access_key
        kwargs['aws_secret_access_key'] = secret_key
    return boto3.client('s3', **kwargs)


def get_presigned_url(file_field_or_key, expires_in=3600, as_attachment=False, filename=None, content_type=None):
    """
    Generates a secure temporary presigned URL for an S3 object.
    Supports FieldFile or string S3 key.
    Falls back gracefully to file.url if S3 is not configured or if presigning fails.
    
    :param file_field_or_key: FieldFile instance (e.g. job.jd_file) or string key (e.g. 'jd_files/sample.pdf')
    :param expires_in: Expiry duration in seconds (default: 3600 = 1 hour)
    :param as_attachment: True for download, False for inline preview
    :param filename: Friendly filename for Content-Disposition
    :param content_type: Explicit MIME content type
    :return: Signed URL string or fallback URL
    """
    if not file_field_or_key:
        return ""

    key = file_field_or_key.name if hasattr(file_field_or_key, 'name') else str(file_field_or_key)
    if not key:
        return ""

    # Strip any leading slashes or media prefixes
    clean_key = key.lstrip('/')

    if not filename:
        filename = os.path.basename(clean_key)

    if not content_type:
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = 'application/pdf' if clean_key.lower().endswith('.pdf') else 'application/octet-stream'

    # If running in local storage mode
    if getattr(settings, 'USE_LOCAL_STORAGE', '0') == '1':
        if hasattr(file_field_or_key, 'url'):
            try:
                return file_field_or_key.url
            except Exception:
                pass
        return f"{getattr(settings, 'MEDIA_URL', '/media/')}{clean_key}"

    # Generate presigned S3 URL
    try:
        bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'talentvault-files-india')
        s3 = get_s3_client()
        
        disposition_type = 'attachment' if as_attachment else 'inline'
        safe_filename = filename.replace('"', '\\"')
        disposition = f'{disposition_type}; filename="{safe_filename}"'

        params = {
            'Bucket': bucket_name,
            'Key': clean_key,
            'ResponseContentDisposition': disposition,
            'ResponseContentType': content_type,
        }
        return s3.generate_presigned_url('get_object', Params=params, ExpiresIn=expires_in)
    except Exception as e:
        logger.error(f"Failed to generate presigned S3 URL for {clean_key}: {e}")
        if hasattr(file_field_or_key, 'url'):
            try:
                return file_field_or_key.url
            except Exception:
                pass
        return ""
