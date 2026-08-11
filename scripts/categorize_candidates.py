import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.models import CandidateProfile

def categorize():
    candidates = CandidateProfile.objects.all().order_by('-created_at')
    total_count = candidates.count()
    
    test_synthetic_candidates = []
    real_candidates = []
    
    for c in candidates:
        email = (c.user.email if c.user else "").lower()
        full_name = (c.full_name or "").lower()
        orig_file = (c.original_filename or "").lower()
        resume_name = (c.resume.name if c.resume else "").lower()

        # Identify synthetic test records created by test scripts / pytest runs on dev DB
        is_test = False
        if any(term in email for term in [
            'example.com', '@talentvault.ai', 'test', 'mock', 'audit', 'demo', 'logout', 'sample'
        ]):
            is_test = True
        elif any(term in full_name for term in [
            'test user', 'candidate test', 'audit user', 'google user', 'linkedin user', 'test candidate'
        ]):
            is_test = True
        
        # Real uploaded resumes (e.g. Hamza Patel, Anoop Singh, etc.)
        if is_test:
            test_synthetic_candidates.append(c)
        else:
            real_candidates.append(c)

    print("=" * 100)
    print(f"DATABASE CANDIDATES ANALYSIS")
    print("=" * 100)
    print(f"Total Rows in DB: {total_count}")
    print(f"Synthetic Test Rows (created by pytest / test scripts): {len(test_synthetic_candidates)}")
    print(f"Real / Uploaded Candidate Rows: {len(real_candidates)}")
    print("=" * 100)

    print("\nSAMPLE REAL CANDIDATES (Top 10):")
    for c in real_candidates[:10]:
        uploader = c.uploaded_by.get_full_name() if c.uploaded_by else "Direct / Application"
        print(f"- Name: {c.full_name:<30} | Email: {c.user.email:<35} | Uploader: {uploader}")

    print("\nSAMPLE SYNTHETIC TEST CANDIDATES (Top 10):")
    for c in test_synthetic_candidates[:10]:
        print(f"- Name: {c.full_name:<30} | Email: {c.user.email:<35}")

if __name__ == '__main__':
    categorize()
