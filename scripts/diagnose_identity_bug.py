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

def diagnose():
    setup_accounts()
    
    test_routes = [
        ('Dashboard', reverse('frontend:recruiter_dashboard')),
        ('Candidates Search', reverse('frontend:candidate_search')),
        ('Recruiter Candidates', reverse('frontend:recruiter_candidates')),
        ('Jobs List', reverse('frontend:jobs')),
        ('Recruiter Jobs', reverse('frontend:recruiter_jobs')),
        ('Clients List', reverse('clients:client_list')),
        ('Pipeline', reverse('frontend:ats_pipeline')),
        ('Interviews', reverse('frontend:interviews')),
        ('Campaigns', reverse('frontend:email_campaigns')),
        ('Resume Parser', reverse('frontend:resume_parser')),
        ('Analytics', reverse('frontend:analytics')),
        ('Settings', reverse('frontend:settings')),
    ]

    for user_email in ['snehal.2020technologies@gmail.com', 'chhayajoshi.2020technologies.in@gmail.com']:
        user = User.objects.get(email=user_email)
        client = Client()
        client.force_login(user)

        print("=" * 80)
        print(f"DIAGNOSING ROUTES FOR LOGGED-IN USER: {user.get_full_name()} ({user.email})")
        print("=" * 80)

        for name, url in test_routes:
            res = client.get(url)
            if res.status_code != 200:
                print(f"[HTTP {res.status_code}] {name} ({url})")
                continue

            html = res.content.decode('utf-8')
            
            # Check for incorrect hardcoded fallback strings or wrong identity
            has_wrong_email = "growfluencestudio@gmail.com" in html
            has_wrong_name = "TalentVault Recruiter" in html
            has_user_first = user.first_name in html
            has_user_email = user.email in html

            print(f"Route: {name:<25} ({url:<35}) -> Status: {res.status_code}")
            print(f"  -> Contains user.first_name ({user.first_name}): {has_user_first}")
            print(f"  -> Contains user.email ({user.email}): {has_user_email}")
            if has_wrong_email:
                print(f"  [ERROR] FOUND growfluencestudio@gmail.com on {name}!")
            if has_wrong_name:
                print(f"  [WARNING/ERROR] FOUND 'TalentVault Recruiter' on {name}!")

if __name__ == '__main__':
    diagnose()
