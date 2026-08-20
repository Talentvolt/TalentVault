import pytest
from django.urls import reverse
from apps.accounts.models import User
from apps.companies.models import Company
from apps.clients.models import Client
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile
from apps.applications.models import Application

@pytest.mark.django_db
def test_candidate_listing_displays_client_name(client):
    recruiter = User.objects.create_user(
        email='recruiter_list@company.com',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    comp, _ = Company.objects.get_or_create(name="TalentVault Test Company")
    client_obj = Client.objects.create(
        company_name="Tech Mahindra",
        spoc_name="Rahul HR"
    )

    # Job with Client assigned
    job_with_client = Job.objects.create(
        company=comp,
        client=client_obj,
        title="Customer Support",
        location="Dehradun",
        work_mode="ONSITE",
        status="ACTIVE"
    )

    cand_user = User.objects.create_user(
        email='candidate_client@company.com',
        password='Password123!',
        role=User.Role.CANDIDATE
    )
    cand_profile = CandidateProfile.objects.create(
        user=cand_user,
        full_name="Rajeev Kumar"
    )

    app = Application.objects.create(
        job=job_with_client,
        candidate=cand_profile,
        created_by=recruiter
    )

    client.force_login(recruiter)
    url = reverse('frontend:candidate_search')
    response = client.get(url)
    assert response.status_code == 200

    html = response.content.decode('utf-8')
    assert "Customer Support" in html
    assert "Tech Mahindra" in html


@pytest.mark.django_db
def test_candidate_pagination_safe_fallbacks(client):
    recruiter = User.objects.create_user(
        email='recruiter_page_test@company.com',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    client.force_login(recruiter)
    url = reverse('frontend:candidate_search')

    # 1. Base URL
    resp1 = client.get(url)
    assert resp1.status_code == 200

    # 2. page=2 (when only 0 or 1 page exists)
    resp2 = client.get(url + '?page=2')
    assert resp2.status_code == 200

    # 3. page=999 (large out of bounds page)
    resp3 = client.get(url + '?page=999')
    assert resp3.status_code == 200

    # 4. tab=modified
    resp4 = client.get(url + '?tab=modified')
    assert resp4.status_code == 200

    # 5. tab=modified&tags=Sales Manager&sort_by=relevance
    resp5 = client.get(url + '?tab=modified&tags=Sales%20Manager&sort_by=relevance')
    assert resp5.status_code == 200

    # 6. Exact previously failing URL: page=2&tab=modified&tags=Sales Manager&sort_by=relevance
    resp6 = client.get(url + '?page=2&tab=modified&tags=Sales%20Manager&sort_by=relevance')
    assert resp6.status_code == 200

