import os
import sys
import django
from django.test import Client

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

def test_pages():
    print("=========================================================")
    print("VERIFYING PUBLIC & PROTECTED PAGES GET REQUESTS")
    print("=========================================================")
    client = Client()

    pages_to_test = [
        ('/', 200, "Landing Page"),
        ('/employers/', 200, "Employer Landing Page"),
        ('/accounts/login/', 200, "Candidate Login"),
        ('/accounts/login/employer/', 200, "Employer Login"),
        ('/accounts/signup/candidate/', 200, "Candidate Sign Up"),
        ('/accounts/signup/employer/', 200, "Employer Sign Up"),
        ('/dashboard/candidate/', 302, "Candidate Dashboard (Redirect expected)"),
        ('/dashboard/recruiter/', 302, "Recruiter Dashboard (Redirect expected)"),
    ]

    failed = False
    for path, expected_status, name in pages_to_test:
        response = client.get(path)
        print(f"GET {path:30} -> Status {response.status_code} (Expected {expected_status}) [{name}]")
        if response.status_code != expected_status:
            print(f"ERROR: Expected status {expected_status} but got {response.status_code}")
            failed = True
            
    if failed:
        print("\nVerification: FAILED!")
        sys.exit(1)
    else:
        print("\nVerification: SUCCESS! All pages loaded with expected status codes.")

if __name__ == '__main__':
    test_pages()
