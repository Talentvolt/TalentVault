import os
import sys
import django
from django.test import Client

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

def test_pages():
    client = Client()
    routes = [
        '/dashboard/candidate/',
        '/profile/',
        '/applications/',
        '/jobs/saved/',
        '/interviews/',
        '/dashboard/recruiter/',
        '/pipeline/',
        '/analytics/',
        '/resume-parser/',
        '/email-campaigns/',
        '/export/candidates/',
        '/export/jobs/',
        '/export/interviews/',
        '/dashboard/admin/',
        '/admin/',
    ]
    
    print("Testing unauthenticated access to protected routes:")
    all_ok = True
    for route in routes:
        response = client.get(route)
        print(f"GET {route:30} -> Status: {response.status_code}")
        # We expect a redirect (302) or permission denied (403), NOT a success (200)
        if response.status_code == 200:
            print(f"  WARNING: {route} returned 200 (Success) without login!")
            all_ok = False
            
    if all_ok:
        print("All protected routes correctly require authentication.")
    else:
        print("Some protected routes DO NOT require authentication!")

if __name__ == '__main__':
    test_pages()
