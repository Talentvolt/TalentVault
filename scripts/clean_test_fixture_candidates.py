import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.models import CandidateProfile
from apps.accounts.models import User

def cleanup_synthetic_test_data():
    print("=" * 80)
    print("CLEANING SYNTHETIC TEST FIXTURE RECORDS FROM DEV DB")
    print("=" * 80)
    
    # Identify candidates created by test scripts / test fixtures
    test_emails = [
        'cand.snehal@example.com',
        'cand.chhaya@example.com',
        'cand.rahul@example.com',
        'candidate_audit@talentvault.in',
        'candidate_local@talentvault.in',
        'candidate.test.auth@talentvault.ai',
        'new.candidate.auth@talentvault.ai',
        'logout.candidate@talentvault.ai',
        'candidate.google@talentvault.ai',
        'candidate.linkedin@talentvault.ai',
        'google_candidate@example.com',
        'google_user1@talentvault.in',
        'google_user2@talentvault.in',
        'google_user3@talentvault.in',
        'mock_docx_candidate@example.com',
        'null_test_user@example.com',
        'dyn1@example.com',
        'dyn2@example.com',
        'candidate@example.com',
    ]

    qs = CandidateProfile.objects.filter(user__email__in=test_emails)
    deleted_candidates_count = 0
    
    for c in list(qs):
        u = c.user
        name = c.full_name or u.get_full_name()
        c.delete()
        if u:
            u.delete()
        deleted_candidates_count += 1
        print(f"Cleaned test fixture row: '{name}' ({u.email if u else 'No User'})")

    print(f"\nRemoved {deleted_candidates_count} synthetic test fixture rows.")
    
    remaining = CandidateProfile.objects.all()
    print(f"REMAINING CANDIDATE PROFILES IN DB: {remaining.count()}")

if __name__ == '__main__':
    cleanup_synthetic_test_data()
