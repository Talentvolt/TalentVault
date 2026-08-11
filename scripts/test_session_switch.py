import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.test import Client
from django.urls import reverse
from apps.accounts.models import User
from scripts.setup_recruiter_accounts import setup_accounts

def test_session_switching():
    setup_accounts()
    client = Client()

    routes = [
        ('Dashboard', reverse('frontend:recruiter_dashboard')),
        ('Candidates', reverse('frontend:candidate_search')),
        ('Jobs', reverse('frontend:jobs')),
        ('Clients', reverse('clients:client_list')),
        ('Pipeline', reverse('frontend:ats_pipeline')),
        ('Interviews', reverse('frontend:interviews')),
        ('Campaigns', reverse('frontend:email_campaigns')),
        ('Resume Parser', reverse('frontend:resume_parser')),
        ('Analytics', reverse('frontend:analytics')),
        ('Settings', reverse('frontend:settings')),
    ]

    print("=" * 80)
    print("TESTING SESSION SWITCHING AND USER IDENTITY ISOLATION")
    print("=" * 80)

    # 1. Login as Snehal
    snehal = User.objects.get(email="snehal.2020technologies@gmail.com")
    print(f"\n[1] Logging in as Snehal Patil ({snehal.email})...")
    client.post(reverse('recruiter_login'), {'email': snehal.email, 'password': 'TV_Snehal#2026!'})

    for name, url in routes:
        res = client.get(url)
        assert res.status_code == 200, f"Failed on {name} ({url})"
        html = res.content.decode('utf-8')
        
        # User identity checks
        assert snehal.email in html, f"Snehal email missing in header/sidebar/settings on {name}"
        assert "growfluencestudio@gmail.com" not in html, f"Old growfluence email found on {name}"

        # Ensure logged out user's email is not in header/sidebar/settings
        assert "chhayajoshi.2020technologies.in@gmail.com" not in html, f"Chhaya email leaked into session on {name}"
        print(f"  -> {name:<20}: Verified Snehal Patil (email: {snehal.email})")

    # 2. Logout Snehal
    print("\n[2] Logging out Snehal...")
    client.post(reverse('account_logout'))
    assert '_auth_user_id' not in client.session

    # 3. Login as Chhaya
    chhaya = User.objects.get(email="chhayajoshi.2020technologies.in@gmail.com")
    print(f"\n[3] Logging in as Chhaya Joshi ({chhaya.email})...")
    client.post(reverse('recruiter_login'), {'email': chhaya.email, 'password': 'TV_Chhaya#2026!'})

    for name, url in routes:
        res = client.get(url)
        assert res.status_code == 200, f"Failed on {name} ({url})"
        html = res.content.decode('utf-8')
        
        # User identity checks
        assert chhaya.email in html, f"Chhaya email missing in header/sidebar/settings on {name}"
        assert "growfluencestudio@gmail.com" not in html, f"Old growfluence email found on {name}"

        # Ensure Snehal's email is not in header/sidebar/settings
        assert "snehal.2020technologies@gmail.com" not in html, f"Snehal email leaked into Chhaya session on {name}"
        print(f"  -> {name:<20}: Verified Chhaya Joshi (email: {chhaya.email})")

    # 4. Logout Chhaya and re-login Snehal
    print("\n[4] Logging out Chhaya and re-logging in Snehal...")
    client.post(reverse('account_logout'))
    client.post(reverse('recruiter_login'), {'email': snehal.email, 'password': 'TV_Snehal#2026!'})

    for name, url in routes:
        res = client.get(url)
        assert res.status_code == 200
        html = res.content.decode('utf-8')
        assert snehal.email in html
        assert "chhayajoshi.2020technologies.in@gmail.com" not in html
        print(f"  -> {name:<20}: Verified Snehal Patil on round 2!")

    print("\n" + "=" * 80)
    print("SESSION SWITCHING AND USER IDENTITY ISOLATION PASSED 100%!")
    print("=" * 80)

if __name__ == '__main__':
    test_session_switching()
