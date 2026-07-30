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
