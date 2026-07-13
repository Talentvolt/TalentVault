import os
import django

# Force tests to use local FileSystemStorage instead of AWS S3
os.environ.pop('AWS_STORAGE_BUCKET_NAME', None)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()
