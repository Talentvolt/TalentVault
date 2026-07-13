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

from apps.candidates.models import CandidateProfile

profiles = CandidateProfile.objects.all()
print(f"Total candidate profiles in DB: {profiles.count()}")

for p in profiles:
    if p.resume:
        try:
            size = p.resume.size
            if size < 1000:
                print(f"Candidate: {p.full_name} ({p.user.email}) | Resume: {p.resume.name} | Size: {size} bytes")
                # Let's read the first 100 bytes of the file to see what it is
                with p.resume.open('rb') as f:
                    content = f.read()
                    print(f"  Content ({len(content)} bytes): {repr(content[:200])}")
        except Exception as e:
            print(f"Error checking size for candidate {p.full_name}: {e}")
