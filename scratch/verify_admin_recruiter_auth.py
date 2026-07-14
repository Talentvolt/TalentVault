import os
import sys
import django
from django.test import Client
from django.urls import reverse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User

def verify_admin_recruiter_auth():
    print("Verifying recruiter login via Admin Portal...")
    client = Client()
    admin_login_url = reverse('admin_login')
    
    # Pre-get for cookies
    client.get(admin_login_url)
    
    # Recruiter credentials
    email = "growfluencestudio@gmail.com"
    password = "TalentVault2026!"
    
    response = client.post(admin_login_url, {
        'email': email,
        'password': password,
        'remember_me': 'on'
    })
    
    print(f"Response status code: {response.status_code}")
    assert response.status_code == 302, f"Expected 302 redirect, got {response.status_code}"
    
    redirect_target = response.url
    print(f"Redirected to: {redirect_target}")
    assert redirect_target == '/dashboard/recruiter/', f"Expected redirect to /dashboard/recruiter/, got {redirect_target}"
    
    print("Recruiter login via Admin Portal: SUCCESS!")

if __name__ == '__main__':
    verify_admin_recruiter_auth()
