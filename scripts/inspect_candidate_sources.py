import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.models import CandidateProfile

def inspect_candidates():
    print("=" * 100)
    print("INSPECTING CANDIDATES:")
    print("=" * 100)
    
    for idx, c in enumerate(CandidateProfile.objects.all().order_by('-created_at'), 1):
        uploader = c.uploaded_by.get_full_name() if c.uploaded_by else "None"
        email = c.user.email if c.user else "No User"
        name = c.full_name or (c.user.get_full_name() if c.user else "No Name")
        has_res = c.has_resume
        orig_file = c.original_filename
        
        info = f"{idx:2d}. ID: {c.id} | Name: '{name}' | Email: '{email}' | HasResume: {has_res} | OrigFile: '{orig_file}' | UploadedBy: {uploader}"
        print(info.encode('ascii', errors='replace').decode('ascii'))

if __name__ == '__main__':
    inspect_candidates()
