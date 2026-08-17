import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.test import Client as DjangoTestClient
from django.urls import reverse
from apps.jobs.models import Job
from apps.companies.models import Company
from apps.accounts.models import User
from apps.applications.models import Application
from apps.candidates.models import CandidateProfile
from apps.clients.models import Client as ClientModel

def verify():
    print("========================================")
    print("      JOBS SECTION VERIFICATION         ")
    print("========================================")
    
    # 1. Total Jobs Check
    total_jobs = Job.objects.count()
    active_jobs = Job.objects.filter(status='ACTIVE').count()
    print(f"\n1. Database Counts:")
    print(f"   • Total Jobs: {total_jobs} (Expected: 2)")
    print(f"   • Active Jobs: {active_jobs} (Expected: 2)")
    assert total_jobs == 2, f"Expected 2 total jobs, got {total_jobs}"
    assert active_jobs == 2, f"Expected 2 active jobs, got {active_jobs}"

    # 2. Check Job Titles & Companies
    jobs = list(Job.objects.order_by('title'))
    print(f"\n2. Job Details:")
    for j in jobs:
        print(f"   • Title: '{j.title}' | Company: '{j.company.name}' | Status: {j.status} | Location: {j.location}")
    
    job_titles = [j.title for j in jobs]
    job_companies = [j.company.name for j in jobs]
    
    assert "Car Inspector" in job_titles, "Car Inspector job not found"
    assert "Automobile Service Advisor" in job_titles, "Automobile Service Advisor job not found"
    assert "Cars 24" in job_companies, "Cars 24 company not found"
    assert "Lumax Group Asia" in job_companies, "Lumax Group Asia company not found"

    car_inspector = Job.objects.get(title="Car Inspector")
    assert car_inspector.company.name == "Cars 24", f"Expected Cars 24, got {car_inspector.company.name}"

    auto_advisor = Job.objects.get(title="Automobile Service Advisor")
    assert auto_advisor.company.name == "Lumax Group Asia", f"Expected Lumax Group Asia, got {auto_advisor.company.name}"

    # 3. Check Candidates, Applications, and Clients data preservation
    print(f"\n3. Data Preservation Check:")
    print(f"   • Total Applications: {Application.objects.count()}")
    print(f"   • Total Candidates: {CandidateProfile.objects.count()}")
    print(f"   • Total Clients: {ClientModel.objects.count()}")
    assert Application.objects.count() > 0, "Applications should not be deleted"
    assert CandidateProfile.objects.count() > 0, "Candidates should not be deleted"
    assert ClientModel.objects.count() > 0, "Clients should not be deleted"

    # 4. HTTP View Check: Candidate / Guest View (candidate_jobs.html)
    http_client = DjangoTestClient()
    resp_guest = http_client.get(reverse('frontend:jobs'))
    assert resp_guest.status_code == 200, f"Guest jobs status: {resp_guest.status_code}"
    guest_content = resp_guest.content.decode('utf-8')
    
    print(f"\n4. Candidate/Public Jobs View (/jobs/):")
    print(f"   • 'Car Inspector' present: {'Car Inspector' in guest_content}")
    print(f"   • 'Cars 24' present: {'Cars 24' in guest_content}")
    print(f"   • 'Automobile Service Advisor' present: {'Automobile Service Advisor' in guest_content}")
    print(f"   • 'Lumax Group Asia' present: {'Lumax Group Asia' in guest_content}")
    print(f"   • 'Talent-Vault Technologies' in jobs: {'Talent-Vault Technologies' not in guest_content}")

    assert "Car Inspector" in guest_content
    assert "Cars 24" in guest_content
    assert "Automobile Service Advisor" in guest_content
    assert "Lumax Group Asia" in guest_content

    # 5. HTTP View Check: Recruiter / Admin View (jobs.html)
    admin_user = User.objects.filter(is_superuser=True).first()
    if not admin_user:
        admin_user = User.objects.filter(role=User.Role.SUPER_ADMIN).first()
    
    http_client.force_login(admin_user)
    resp_admin = http_client.get(reverse('frontend:jobs'))
    assert resp_admin.status_code == 200, f"Admin jobs status: {resp_admin.status_code}"
    admin_content = resp_admin.content.decode('utf-8')

    print(f"\n5. Admin/Recruiter Jobs Table View (/jobs/):")
    print(f"   • 'Car Inspector' present: {'Car Inspector' in admin_content}")
    print(f"   • 'Cars 24' present: {'Cars 24' in admin_content}")
    print(f"   • 'Automobile Service Advisor' present: {'Automobile Service Advisor' in admin_content}")
    print(f"   • 'Lumax Group Asia' present: {'Lumax Group Asia' in admin_content}")
    
    # Check that "CLIENT / COMPANY" or "(Client: ...)" or "All Clients" or "Client" label is NOT in table/filter
    print(f"   • 'CLIENT / COMPANY' header absent: {'CLIENT / COMPANY' not in admin_content}")
    print(f"   • '(Client:' label absent: {'(Client:' not in admin_content}")
    print(f"   • 'All Clients' dropdown option absent: {'All Clients' not in admin_content}")
    print(f"   • 'COMPANY' column header present: {'COMPANY' in admin_content}")
    print(f"   • 'All Companies' dropdown option present: {'All Companies' in admin_content}")

    assert "CLIENT / COMPANY" not in admin_content
    assert "(Client:" not in admin_content
    assert "All Clients" not in admin_content
    assert "Car Inspector" in admin_content
    assert "Cars 24" in admin_content
    assert "Automobile Service Advisor" in admin_content
    assert "Lumax Group Asia" in admin_content

    # 6. Public Job Share Pages Check
    resp_share1 = http_client.get(reverse('frontend:public_job_share', kwargs={'pk': car_inspector.pk}))
    assert resp_share1.status_code == 200
    share1_content = resp_share1.content.decode('utf-8')
    assert "Car Inspector" in share1_content
    assert "Cars 24" in share1_content

    resp_share2 = http_client.get(reverse('frontend:public_job_share', kwargs={'pk': auto_advisor.pk}))
    assert resp_share2.status_code == 200
    share2_content = resp_share2.content.decode('utf-8')
    assert "Automobile Service Advisor" in share2_content
    assert "Lumax Group Asia" in share2_content

    print(f"\n6. Public Job Share Pages:")
    print(f"   • Job 1 Share ({car_inspector.id}): OK (Cars 24)")
    print(f"   • Job 2 Share ({auto_advisor.id}): OK (Lumax Group Asia)")

    print("\n========================================")
    print("   ALL VERIFICATION CHECKS PASSED!      ")
    print("========================================")

if __name__ == '__main__':
    verify()
