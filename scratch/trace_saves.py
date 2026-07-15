import os
import sys
import django
import time
import traceback
from datetime import datetime

# Setup path and environment
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Load env variables
try:
    import dotenv
    dotenv.load_dotenv(os.path.join(project_root, '.env'))
except ImportError:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.files.storage import Storage
from django.db.models.fields.files import FieldFile
from apps.candidates.utils import process_resume_file

# Trace storage save
orig_storage_save = Storage.save
def custom_storage_save(self, name, content, max_length=None):
    size = content.size if hasattr(content, 'size') else len(content)
    print(f"\n[TRACE Storage.save] Called at {datetime.now()}")
    print(f"  Name: {name}")
    print(f"  Size: {size} bytes")
    print(f"  Storage class: {self.__class__.__name__}")
    print("  Stack trace:")
    traceback.print_stack(limit=5)
    return orig_storage_save(self, name, content, max_length)

# Trace FieldFile save
orig_fieldfile_save = FieldFile.save
def custom_fieldfile_save(self, name, content, save=True):
    size = content.size if hasattr(content, 'size') else len(content)
    print(f"\n[TRACE FieldFile.save] Called at {datetime.now()}")
    print(f"  Name: {name}")
    print(f"  Size: {size} bytes")
    print(f"  Field: {self.field.name}")
    print(f"  Save to DB flag: {save}")
    print("  Stack trace:")
    traceback.print_stack(limit=5)
    return orig_fieldfile_save(self, name, content, save)

# Apply monkey patching
Storage.save = custom_storage_save
FieldFile.save = custom_fieldfile_save

# S3Storage save overrides
try:
    from storages.backends.s3 import S3Storage
    orig_s3_save = S3Storage._save
    def custom_s3_save(self, name, content):
        size = content.size if hasattr(content, 'size') else len(content)
        print(f"\n[TRACE S3Storage._save] Called at {datetime.now()}")
        print(f"  Name: {name}")
        print(f"  Size: {size} bytes")
        print("  Stack trace:")
        traceback.print_stack(limit=5)
        return orig_s3_save(self, name, content)
    S3Storage._save = custom_s3_save
except Exception as e:
    print(f"Could not patch S3Storage: {e}")

def main():
    cache.clear()
    
    User = get_user_model()
    test_user, _ = User.objects.get_or_create(
        email="trace_test@example.com",
        defaults={"first_name": "Test", "last_name": "User"}
    )
    
    resume_path = "scratch/harneet_resume.pdf"
    print(f"Parsing and tracing saves for: {resume_path}")
    
    with open(resume_path, "rb") as f:
        profile, status = process_resume_file(
            file_obj=f,
            filename=os.path.basename(resume_path),
            overwrite=True,
            user=test_user
        )
        
    print(f"\nTrace completed. Parse Status: {status}")

if __name__ == "__main__":
    main()
