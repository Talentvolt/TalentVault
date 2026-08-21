import os
import logging
import mimetypes
from django.conf import settings

logger = logging.getLogger(__name__)

MIME_MAP = {
    'pdf': 'application/pdf',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'rtf': 'application/rtf',
    'txt': 'text/plain',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
}

def get_content_type(filename_or_key: str) -> str:
    """
    Resolves the exact MIME Content-Type for documents and resumes.
    """
    if not filename_or_key:
        return 'application/octet-stream'
    ext = os.path.splitext(str(filename_or_key))[1].lower().lstrip('.')
    if ext in MIME_MAP:
        return MIME_MAP[ext]
    guessed, _ = mimetypes.guess_type(str(filename_or_key))
    return guessed or 'application/octet-stream'

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


def get_presigned_url(file_field_or_key, expires_in=900, as_attachment=False, filename=None, content_type=None):
    """
    Generates a secure temporary presigned GET URL for an S3 object.
    Supports FieldFile or string S3 key.
    Falls back gracefully to file.url if S3 is not configured or if presigning fails.
    
    :param file_field_or_key: FieldFile instance (e.g. candidate.resume) or string key (e.g. 'resumes/sample.doc')
    :param expires_in: Expiry duration in seconds (default: 900 = 15 minutes)
    :param as_attachment: True for download, False for inline preview
    :param filename: Friendly filename for Content-Disposition
    :param content_type: Explicit MIME content type (e.g. application/pdf, application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document)
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
        content_type = get_content_type(filename or clean_key)

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
