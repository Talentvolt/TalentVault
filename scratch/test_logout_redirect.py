import os
import sys
import django
from django.test import Client
from django.urls import reverse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User

def verify_logout_redirects():
    print("Verifying role-specific logout redirection flows...")
    
    # 1. Candidate
    client_cand = Client()
    cand_email = "logout.candidate@talentvault.ai"
    User.objects.filter(email=cand_email).delete()
    candidate = User.objects.create(
        email=cand_email,
        first_name="Logout",
        last_name="Candidate",
        role=User.Role.CANDIDATE,
        is_active=True,
        is_verified=True
    )
    client_cand.force_login(candidate)
    
    response = client_cand.post(reverse('account_logout'))
    print(f"Candidate Logout Status: {response.status_code}, Location: {response.url}")
    assert response.status_code == 302
    assert response.url == '/accounts/login/candidate/'

    # 2. Recruiter
    client_rec = Client()
    rec_email = "logout.recruiter@talentvault.ai"
    User.objects.filter(email=rec_email).delete()
    recruiter = User.objects.create(
        email=rec_email,
        first_name="Logout",
        last_name="Recruiter",
        role=User.Role.RECRUITER,
        is_active=True,
        is_verified=True
    )
    client_rec.force_login(recruiter)
    
    response = client_rec.post(reverse('account_logout'))
    print(f"Recruiter Logout Status: {response.status_code}, Location: {response.url}")
    assert response.status_code == 302
    assert response.url == '/accounts/login/employer/'

    # 3. Super Admin
    client_admin = Client()
    admin_email = "logout.admin@talentvault.ai"
    User.objects.filter(email=admin_email).delete()
    admin = User.objects.create(
        email=admin_email,
        first_name="Logout",
        last_name="Admin",
        role=User.Role.SUPER_ADMIN,
        is_active=True,
        is_verified=True
    )
    client_admin.force_login(admin)
    
    response = client_admin.post(reverse('account_logout'))
    print(f"Admin Logout Status: {response.status_code}, Location: {response.url}")
    assert response.status_code == 302
    assert response.url == '/accounts/login/admin/'

    print("All role-specific logout redirection flows verified successfully!")

if __name__ == '__main__':
    verify_logout_redirects()
