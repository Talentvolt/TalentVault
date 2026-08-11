import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.models import CandidateProfile

def inspect_candidates():
    candidates = CandidateProfile.objects.all().order_by('-created_at')
    print("=" * 100)
    print(f"TOTAL CANDIDATE PROFILE ROWS IN DB: {candidates.count()}")
    print("=" * 100)
    
    for idx, c in enumerate(candidates[:30], 1):
        uploader = c.uploaded_by.get_full_name() if c.uploaded_by else "None"
        uploader_email = c.uploaded_by.email if c.uploaded_by else "None"
        user_email = c.user.email if c.user else "No User"
        user_name = c.user.get_full_name() if c.user else "No User"
        resume_name = c.resume.name if c.resume else "None"
        orig_file = c.original_filename or "None"
        
        info = f"{idx:2d}. ID: {c.id}\n" \
               f"    Full Name: '{c.full_name}' | User Name: '{user_name}'\n" \
               f"    User Email: '{user_email}' | Uploader: {uploader} ({uploader_email})\n" \
               f"    Resume: '{resume_name}' | Original Filename: '{orig_file}'\n" \
               f"    Created At: {c.created_at}"
        print(info.encode('ascii', errors='replace').decode('ascii'))
        print("-" * 100)

if __name__ == '__main__':
    inspect_candidates()
