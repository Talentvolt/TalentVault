import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass
django.setup()

from django.test import Client as DjangoTestClient
from apps.accounts.models import User
from apps.clients.models import Client

def run_tests():
    # Fetch a superadmin or recruiter user
    user = User.objects.filter(role__in=[User.Role.SUPER_ADMIN, User.Role.RECRUITER]).first()
    if not user:
        user = User.objects.create_superuser('testadmin@example.com', 'adminpass123')

    test_client = DjangoTestClient()
    test_client.force_login(user)

    db_count = Client.objects.count()
    print(f"Current Client database count: {db_count}")

    test_urls = [
        '/clients/',
        '/clients/?page=1',
        '/clients/?page=2',
        '/clients/?page=3',
        '/clients/?page=4',
        '/clients/?page=999',
        '/clients/?page=abc',
        '/clients/?company_name=Tech&page=1',
        '/clients/?company_name=Tech&page=999',
        '/clients/?company_name=NonExistentCompanyXYZ&page=1',
    ]

    print("\n--- TESTING EXACT PAGINATION URLs ---")
    for url in test_urls:
        response = test_client.get(url, follow=True)
        # Check if redirect happened
        redirect_info = f" (Redirected to: {response.redirect_chain[-1][0]})" if response.redirect_chain else ""
        print(f"URL: '{url}' -> Status: {response.status_code}{redirect_info}")
        if response.status_code != 200:
            print(f"  [FAIL] Unexpected status code {response.status_code} for {url}")
        else:
            print(f"  [PASS] Successfully rendered with 200 OK")

if __name__ == '__main__':
    run_tests()
