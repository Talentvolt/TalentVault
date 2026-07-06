import os
import sys
import django
import traceback
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env variables from .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.utils import process_resume_file
from apps.candidates.models import CandidateProfile
from apps.accounts.models import User

def main():
    resumes_dir = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes')
    files = [f for f in os.listdir(resumes_dir) if f.endswith(('.pdf', '.docx', '.doc'))]
    
    # Sort files to check real files (not uuid hash named files)
    real_files = [f for f in files if not (f[0].isdigit() or f[0].islower() and len(f) == 36)]
    all_files = real_files + [f for f in files if f not in real_files]
    
    print(f"Found {len(all_files)} total files to test.")
    
    for filename in all_files:
        filepath = os.path.join(resumes_dir, filename)
        if filename.startswith(('original_', 'photo_')) or len(filename) < 5:
            continue
            
        print(f"\n---> Testing {filename}...")
        try:
            with open(filepath, 'rb') as f:
                profile, status = process_resume_file(f, filename, overwrite=True)
                print(f"Status: {status}")
                if status == "SAVE_FAILED":
                    print(f"SAVE_FAILED triggered for {filename}")
        except Exception as e:
            print(f"Direct Exception for {filename}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()
