import os
import django
from django.test import Client
from django.urls import reverse

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User

def run_verification():
    print("Initializing login verification test...")
    client = Client()

    # 1. Test GET request on login page
    login_url = reverse('account_login')
    print(f"GET login page: {login_url}")
    response = client.get(login_url)
    assert response.status_code == 200, f"Expected 200 on login page, got {response.status_code}"
    print("GET login page: SUCCESS (200 OK)")

    # 2. Test POST request with default recruiter credentials
    email = "growfluencestudio@gmail.com"
    password = "TalentVault2026!"
    
    # Let's verify user exists
    try:
        user = User.objects.get(email=email)
        print(f"User '{email}' found in database with role: {user.role}")
    except User.DoesNotExist:
        print(f"ERROR: User '{email}' does not exist.")
        return

    print(f"POST login page with: {email}")
    # Get CSRF token
    client.get(login_url)
    response = client.post(login_url, {
        'email': email,
        'password': password,
        'remember_me': 'on'
    })
    
    # It should redirect to dashboard
    print(f"POST Response status code: {response.status_code}")
    print(f"POST Redirection target: {response.url if hasattr(response, 'url') else response.get('Location')}")
    assert response.status_code == 302, f"Expected 302 redirect, got {response.status_code}"
    
    # Follow the redirect to the dashboard
    dashboard_url = response.url
    response = client.get(dashboard_url, follow=True)
    
    print("Final redirected URL chain:")
    for redirect_url, status_code in response.redirect_chain:
        print(f" -> {redirect_url} (status: {status_code})")
    
    final_url = response.request.get('PATH_INFO')
    print(f"Final URL reached: {final_url}")
    
    # Verify that the final path is the recruiter dashboard
    assert final_url == '/dashboard/recruiter/', f"Expected to end up at /dashboard/recruiter/, but reached {final_url}"
    print("Verification result: SUCCESS!")

if __name__ == '__main__':
    run_verification()
