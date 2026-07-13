import os
import sys
import django
from django.test import Client
from django.urls import reverse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User

def test_flow():
    print("=========================================================")
    print("STARTING ROLE-BASED ACCESS & ROUTE PROTECTION TESTS")
    print("=========================================================")

    candidate_email = "candidate.google@talentvault.ai"
    recruiter_email = "growfluencestudio@gmail.com"
    admin_email = "admin@2020tech.com"

    try:
        candidate_user = User.objects.get(email=candidate_email)
        recruiter_user = User.objects.get(email=recruiter_email)
        admin_user = User.objects.get(email=admin_email)
    except User.DoesNotExist as e:
        print(f"Failed to fetch test users: {e}")
        return

    # 1. TEST CANDIDATE FLOWS
    print("\n--- Testing Candidate: candidate.google@talentvault.ai ---")
    c_client = Client()
    c_client.force_login(candidate_user)

    # Test / redirect
    r = c_client.get('/')
    print(f"GET '/' redirects to: {r.url} (status {r.status_code})")
    assert r.status_code == 302 and r.url == '/dashboard/candidate/', "Candidate must be redirected to /dashboard/candidate/ from '/'!"
    
    # Test /employers/ redirect
    r = c_client.get('/employers/')
    print(f"GET '/employers/' redirects to: {r.url} (status {r.status_code})")
    assert r.status_code == 302 and r.url == '/', "Candidate must be redirected to '/' from '/employers/'!"
    
    # Test dashboard access
    r = c_client.get('/dashboard/candidate/')
    print(f"GET '/dashboard/candidate/' returns: {r.status_code}")
    assert r.status_code == 200, "Candidate must access /dashboard/candidate/!"

    # Test access to forbidden pages (should redirect to candidate dashboard)
    forbidden_for_candidate = [
        '/dashboard/recruiter/',
        '/dashboard/admin/',
        '/pipeline/',
        '/analytics/',
        '/candidates/',
        '/resume-parser/',
        '/email-campaigns/',
        '/jobs/new/'
    ]
    for path in forbidden_for_candidate:
        r = c_client.get(path)
        print(f"GET '{path}' redirects to: {r.url if hasattr(r, 'url') else r.get('Location')} (status {r.status_code})")
        # Follow check
        target = r.url if hasattr(r, 'url') else r.get('Location')
        assert r.status_code == 302 and target == '/dashboard/candidate/', f"Candidate should be redirected to /dashboard/candidate/ from '{path}'!"

    print("CANDIDATE TESTS: PASSED")

    # 2. TEST RECRUITER FLOWS
    print("\n--- Testing Recruiter: growfluencestudio@gmail.com ---")
    r_client = Client()
    r_client.force_login(recruiter_user)

    # Test / redirect
    r = r_client.get('/')
    print(f"GET '/' redirects to: {r.url} (status {r.status_code})")
    assert r.status_code == 302 and r.url == '/dashboard/recruiter/', "Recruiter must be redirected to /dashboard/recruiter/ from '/'!"
    
    # Test /employers/ redirect
    r = r_client.get('/employers/')
    print(f"GET '/employers/' redirects to: {r.url} (status {r.status_code})")
    assert r.status_code == 302 and r.url == '/', "Recruiter must be redirected to '/' from '/employers/'!"

    # Test dashboard access
    r = r_client.get('/dashboard/recruiter/')
    print(f"GET '/dashboard/recruiter/' returns: {r.status_code}")
    assert r.status_code == 200, "Recruiter must access /dashboard/recruiter/!"

    # Test access to forbidden pages (should redirect to recruiter dashboard)
    forbidden_for_recruiter = [
        '/dashboard/candidate/',
        '/dashboard/admin/',
        '/profile/',
        '/career-resources/',
        '/jobs/saved/',
        '/jobs/recommended/',
        '/applications/'
    ]
    for path in forbidden_for_recruiter:
        r = r_client.get(path)
        target = r.url if hasattr(r, 'url') else r.get('Location')
        print(f"GET '{path}' redirects to: {target} (status {r.status_code})")
        assert r.status_code == 302 and target == '/dashboard/recruiter/', f"Recruiter should be redirected to /dashboard/recruiter/ from '{path}'!"

    print("RECRUITER TESTS: PASSED")

    # 3. TEST ADMIN FLOWS
    print("\n--- Testing Admin: admin@2020tech.com ---")
    a_client = Client()
    a_client.force_login(admin_user)

    # Test / redirect
    r = a_client.get('/')
    print(f"GET '/' redirects to: {r.url} (status {r.status_code})")
    assert r.status_code == 302 and r.url == '/dashboard/admin/', "Admin must be redirected to /dashboard/admin/ from '/'!"
    
    # Test /employers/ redirect
    r = a_client.get('/employers/')
    print(f"GET '/employers/' redirects to: {r.url} (status {r.status_code})")
    assert r.status_code == 302 and r.url == '/dashboard/admin/', "Admin must be redirected to /dashboard/admin/ from '/employers/'!"

    # Test dashboard access
    r = a_client.get('/dashboard/admin/')
    print(f"GET '/dashboard/admin/' returns: {r.status_code}")
    assert r.status_code == 200, "Admin must access /dashboard/admin/!"

    # Test access to forbidden pages (should redirect to admin dashboard)
    forbidden_for_admin = [
        '/dashboard/candidate/',
        '/dashboard/recruiter/',
        '/pipeline/',
        '/analytics/',
        '/candidates/',
        '/resume-parser/',
        '/email-campaigns/',
        '/jobs/new/',
        '/profile/',
        '/career-resources/',
        '/jobs/saved/',
        '/jobs/recommended/',
        '/applications/'
    ]
    for path in forbidden_for_admin:
        r = a_client.get(path)
        target = r.url if hasattr(r, 'url') else r.get('Location')
        print(f"GET '{path}' redirects to: {target} (status {r.status_code})")
        assert r.status_code == 302 and target == '/dashboard/admin/', f"Admin should be redirected to /dashboard/admin/ from '{path}'!"

    print("ADMIN TESTS: PASSED")
    print("\n=========================================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=========================================================")

if __name__ == '__main__':
    test_flow()
