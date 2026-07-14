import os
import sys
import django
from django.test import Client
from django.urls import reverse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User

def verify_employer_login_uionly():
    print("Verifying UI-only status of new Employer Login and Signup...")
    client = Client()
    
    # 1. GET employer login page
    login_url = reverse('employer_login')
    response = client.get(login_url)
    print(f"GET employer login status: {response.status_code}")
    assert response.status_code == 200, "Employer login page should render successfully (200)"
    
    # 2. POST employer login page with recruiter credentials
    email = "growfluencestudio@gmail.com"
    password = "TalentVault2026!"
    
    response = client.post(login_url, {
        'email': email,
        'password': password,
        'remember_me': 'on'
    })
    
    print(f"POST employer login status: {response.status_code}")
    # Since it is UI-only, it should NOT redirect (302) to the recruiter dashboard. It should just return 200.
    assert response.status_code == 200, f"Expected 200 (re-render form), got {response.status_code}"
    
    # Verify that the client is NOT authenticated
    response_dashboard = client.get('/dashboard/recruiter/')
    # Accessing recruiter dashboard should redirect to login (302)
    assert response_dashboard.status_code == 302, "User was authenticated by UI-only login!"
    
    print("New Employer Login is successfully verified to be UI-only!")

if __name__ == '__main__':
    verify_employer_login_uionly()
