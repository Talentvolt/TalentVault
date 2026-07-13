import os
import sys
import django
from django.test import Client
from django.urls import reverse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User

def run_tests():
    client = Client()
    print("=========================================================")
    print("RUNNING END-TO-END VERIFICATION")
    print("=========================================================")

    # 1. Verify Employer Landing & Admin Portal Button
    print("\n[1/5] Verifying Employer Landing & Admin Portal Button...")
    landing_url = "/employers/"
    response = client.get(landing_url)
    assert response.status_code == 200, f"Expected 200 on employer landing, got {response.status_code}"
    
    html = response.content.decode('utf-8')
    assert "Admin Portal" in html, "Admin Portal link not found in Employer Landing Page!"
    assert "/accounts/login/admin/" in html, "Admin Portal link does not point to the admin login page!"
    print("Employer Landing & Admin Portal link: SUCCESS")

    # 2. Verify Candidate Login
    print("\n[2/5] Verifying Candidate Login...")
    # Find/Create a verified candidate for testing
    candidate_email = "candidate.test.auth@talentvault.ai"
    candidate_pass = "TestCandidate123!"
    
    # Clean up first
    User.objects.filter(email=candidate_email).delete()
    
    user = User.objects.create(
        email=candidate_email,
        first_name="Test",
        last_name="Candidate",
        role=User.Role.CANDIDATE,
        is_active=True,
        is_verified=True
    )
    user.set_password(candidate_pass)
    user.save()
    
    login_url = reverse('candidate_login')
    client.get(login_url) # Get cookies/CSRF
    response = client.post(login_url, {
        'email': candidate_email,
        'password': candidate_pass
    })
    
    # Candidate login should redirect to candidate dashboard
    assert response.status_code == 302, f"Expected redirect on candidate login, got {response.status_code}"
    assert response.url == '/dashboard/candidate/', f"Expected redirect to /dashboard/candidate/, got {response.url}"
    print("Candidate Login: SUCCESS")

    # 3. Verify Sign Out
    print("\n[3/5] Verifying Sign Out...")
    logout_url = reverse('account_logout')
    response = client.post(logout_url) # POST to logout should log out
    assert response.status_code == 302, f"Expected redirect on logout, got {response.status_code}"
    
    # Try to access a protected page to verify we are logged out
    response = client.get('/dashboard/candidate/')
    assert response.status_code == 302, f"Expected redirect to login after logout, got {response.status_code}"
    print("Sign Out & Session Clearance: SUCCESS")

    # 4. Verify Register Page redirects / Auto-logout
    print("\n[4/5] Verifying Register Page Auto-Logout...")
    # Log in again
    client.post(login_url, {
        'email': candidate_email,
        'password': candidate_pass
    })
    
    # Check that we are logged in
    response = client.get('/dashboard/candidate/')
    assert response.status_code == 200, "Should be authenticated"
    
    # Now request the signup page. It should log us out!
    signup_url = reverse('account_signup')
    response = client.get(signup_url)
    assert response.status_code == 200, f"Expected 200 on signup page, got {response.status_code}"
    
    # Check that accessing the protected page now redirects to login (meaning we were successfully logged out!)
    response = client.get('/dashboard/candidate/')
    assert response.status_code == 302, "Expected redirect to login. Register page did not log us out!"
    print("Register Page Auto-Logout: SUCCESS")

    # 5. Verify Register submission does NOT auto-login
    print("\n[5/5] Verifying Register submission does not auto-login...")
    new_candidate_email = "new.candidate.auth@talentvault.ai"
    User.objects.filter(email=new_candidate_email).delete()
    
    signup_form_url = reverse('candidate_signup')
    response = client.post(signup_form_url, {
        'first_name': 'New',
        'last_name': 'Candidate',
        'email': new_candidate_email,
        'phone_number': '+91 99999 88888',
        'location': 'Mumbai, India',
        'password': 'Password123!',
        'confirm_password': 'Password123!',
        'role': 'CANDIDATE'
    })
    
    # Should redirect to verification page
    assert response.status_code == 302, f"Expected redirect on signup, got {response.status_code}"
    
    # Ensure they are NOT logged in (accessing candidate dashboard should redirect to login)
    response = client.get('/dashboard/candidate/')
    assert response.status_code == 302, "New registered user was auto-logged in! Security violation!"
    
    print("Register Submission does not auto-login: SUCCESS")

    print("\n=========================================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=========================================================")

if __name__ == '__main__':
    run_tests()
