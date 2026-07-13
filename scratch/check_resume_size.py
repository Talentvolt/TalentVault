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

from django.core.files.storage import storages
storage = storages['default']
print("Storage backend:", type(storage))
if hasattr(storage, 'bucket_name'):
    print("Bucket name:", storage.bucket_name)
