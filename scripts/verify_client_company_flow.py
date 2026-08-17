import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.test import Client as DjangoTestClient
from django.urls import reverse
from apps.jobs.models import Job
from apps.companies.models import Company, CompanyMember
from apps.accounts.models import User
from apps.clients.models import Client as ClientModel

def verify_flow():
    print("==================================================")
    print("    VERIFYING CLIENT COMPANY JOB POSTING FLOW     ")
    print("==================================================")

    # 1. Setup / Verify Tech Mahindra Client
    client_tm, _ = ClientModel.objects.get_or_create(
        company_name="Tech Mahindra",
        defaults={
            'spoc_name': 'Tech Mahindra HR',
            'industry': 'IT_SERVICES',
            'city': 'Noida',
            'status': 'ACTIVE'
        }
    )
    print(f"\n1. Client Verification:")
    print(f"   • Client ID: {client_tm.id} | Name: {client_tm.company_name}")

    # 2. Get Recruiter / Admin User
    admin_user = User.objects.filter(is_superuser=True).first()
    if not admin_user:
        admin_user = User.objects.filter(role=User.Role.SUPER_ADMIN).first()
    if not admin_user:
        admin_user = User.objects.filter(role=User.Role.RECRUITER).first()

    http_client = DjangoTestClient()
    http_client.force_login(admin_user)

    # 3. Simulate Job Posting Flow with Client Company = Tech Mahindra
    print(f"\n2. Testing Job Creation via JobCreateView:")
    post_data = {
        'title': 'Senior Software Engineer Test',
        'client': str(client_tm.id),
        'location': 'Noida, Uttar Pradesh',
        'job_type': 'FULL_TIME',
        'work_mode': 'HYBRID',
        'min_experience': 2,
        'max_experience': 5,
        'min_salary': 800000,
        'max_salary': 1500000,
        'currency': 'INR',
        'description': '<p>Developing modern enterprise web applications.</p>',
        'skills_tags': 'Python, Django, React'
    }

    create_url = reverse('frontend:job_create')
    response_post = http_client.post(create_url, data=post_data, follow=True)
    assert response_post.status_code == 200, f"Failed post creation: {response_post.status_code}"

    new_job = Job.objects.filter(title='Senior Software Engineer Test').first()
    assert new_job is not None, "Job was not created!"
    print(f"   • Created Job: '{new_job.title}'")
    print(f"   • Job.client: {new_job.client.company_name}")
    print(f"   • Job.company: {new_job.company.name}")
    print(f"   • Job.display_company: {new_job.display_company}")

    assert new_job.client.company_name == "Tech Mahindra", f"Expected Tech Mahindra, got {new_job.client.company_name}"
    assert new_job.company.name == "Tech Mahindra", f"Expected Tech Mahindra, got {new_job.company.name}"
    assert new_job.display_company == "Tech Mahindra", f"Expected Tech Mahindra, got {new_job.display_company}"

    # 4. Check Jobs Management Listing Table (/jobs/)
    print(f"\n3. Testing Jobs Listing Page (/jobs/):")
    jobs_resp = http_client.get(reverse('frontend:jobs'))
    assert jobs_resp.status_code == 200
    jobs_html = jobs_resp.content.decode('utf-8')

    # Verify Tech Mahindra is displayed in the company column for the job
    assert "Senior Software Engineer Test" in jobs_html
    assert "Tech Mahindra" in jobs_html
    print("   • Job 'Senior Software Engineer Test' correctly displays 'Tech Mahindra' in company column: YES")

    # 5. Check Edit Job Page
    print(f"\n4. Testing Edit Job Page (/jobs/<id>/edit/):")
    edit_url = reverse('frontend:job_edit', kwargs={'pk': new_job.id})
    edit_resp = http_client.get(edit_url)
    assert edit_resp.status_code == 200
    edit_html = edit_resp.content.decode('utf-8')

    # Verify Client Company dropdown has Tech Mahindra selected
    expected_option = f'value="{client_tm.id}" selected'
    assert expected_option in edit_html or f'selected value="{client_tm.id}"' in edit_html or f'<option value="{client_tm.id}" selected>' in edit_html
    print("   • Edit Job page has 'Tech Mahindra' selected in Client dropdown: YES")

    # 6. Test Job Update Flow (Saving changes on edit page)
    print(f"\n5. Testing Job Update Flow:")
    update_data = {
        'title': 'Senior Software Engineer Test',
        'client': str(client_tm.id),
        'location': 'Bengaluru, Karnataka',
        'job_type': 'FULL_TIME',
        'work_mode': 'REMOTE',
        'min_experience': 3,
        'max_experience': 6,
        'min_salary': 1000000,
        'max_salary': 1800000,
        'currency': 'INR',
        'description': '<p>Updated description.</p>',
        'skills_tags': 'Python, Django, FastAPI'
    }
    update_resp = http_client.post(edit_url, data=update_data, follow=True)
    assert update_resp.status_code == 200

    new_job.refresh_from_db()
    print(f"   • Updated Job Location: {new_job.location}")
    print(f"   • Job.display_company after update: {new_job.display_company}")
    print(f"   • Job.client after update: {new_job.client.company_name}")
    print(f"   • Job.company after update: {new_job.company.name}")
    assert new_job.display_company == "Tech Mahindra"
    assert new_job.client.company_name == "Tech Mahindra"
    assert new_job.company.name == "Tech Mahindra"

    # 7. Check Public Share Page
    print(f"\n6. Testing Public Share Page:")
    share_url = reverse('frontend:public_job_share', kwargs={'pk': new_job.id})
    share_resp = http_client.get(share_url)
    assert share_resp.status_code == 200
    share_html = share_resp.content.decode('utf-8')
    assert "Tech Mahindra" in share_html
    print("   • Public Share page displays 'Tech Mahindra': YES")

    # Clean up test job
    new_job.delete()
    print("\n   • Test job cleaned up cleanly.")

    # 8. Check existing user's Software Engineer job
    print(f"\n7. Checking existing user's Software Engineer Job:")
    se_job = Job.objects.filter(title='Software Engineer').first()
    if se_job:
        print(f"   • Title: {se_job.title}")
        print(f"   • Client: {se_job.client.company_name if se_job.client else None}")
        print(f"   • Company: {se_job.company.name if se_job.company else None}")
        print(f"   • Display Company: {se_job.display_company}")
        assert se_job.display_company == "Tech Mahindra"
        assert se_job.client.company_name == "Tech Mahindra"

    print("\n==================================================")
    print("   ALL CLIENT COMPANY FLOW VERIFICATIONS PASSED!  ")
    print("==================================================")

if __name__ == '__main__':
    verify_flow()
