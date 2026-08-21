import pytest
from django.urls import reverse
from django.test import Client as DjangoTestClient
from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.clients.models import Client
from apps.jobs.models import Job

@pytest.fixture
def setup_company_data(db):
    # Recruiter agency company
    recruiter_company = Company.objects.create(
        name="2020technologies",
        slug="2020technologies",
        industry="Recruitment",
        location="India"
    )

    # Recruiter 1 (Anamika Shukla)
    recruiter_1 = User.objects.create_user(
        email="anamika@2020technologies.in",
        password="password123",
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE,
        first_name="Anamika",
        last_name="Shukla"
    )
    CompanyMember.objects.create(
        user=recruiter_1,
        company=recruiter_company,
        designation="Senior Recruiter"
    )

    # Recruiter 2 (Rahul Nishad, same agency)
    recruiter_2 = User.objects.create_user(
        email="rahul@2020technologies.in",
        password="password123",
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE,
        first_name="Rahul",
        last_name="Nishad"
    )
    CompanyMember.objects.create(
        user=recruiter_2,
        company=recruiter_company,
        designation="Recruiter"
    )

    # Recruiter 3 (Independent / Different agency)
    other_company = Company.objects.create(
        name="Acme Recruiters",
        slug="acme-recruiters",
        industry="Recruitment",
        location="India"
    )
    recruiter_3 = User.objects.create_user(
        email="other@acme.com",
        password="password123",
        role=User.Role.SUPER_ADMIN,
        first_name="Other",
        last_name="Recruiter"
    )
    CompanyMember.objects.create(
        user=recruiter_3,
        company=other_company,
        designation="Admin"
    )

    # Client Companies
    client_prince_pipes = Client.objects.create(
        company_name="Prince Pipes",
        spoc_name="Prince HR",
        industry=Client.Industry.MANUFACTURING,
        city="Mumbai",
        status=Client.Status.ACTIVE,
        created_by=recruiter_1
    )

    client_tech_mahindra = Client.objects.create(
        company_name="Tech Mahindra",
        spoc_name="TechM HR",
        industry=Client.Industry.IT_SERVICES,
        city="Noida",
        status=Client.Status.ACTIVE,
        created_by=recruiter_1
    )

    return {
        'recruiter_company': recruiter_company,
        'recruiter_1': recruiter_1,
        'recruiter_2': recruiter_2,
        'recruiter_3': recruiter_3,
        'client_prince_pipes': client_prince_pipes,
        'client_tech_mahindra': client_tech_mahindra,
    }

@pytest.mark.django_db
def test_scenario_a_recruiter_client_attribution(setup_company_data):
    """
    Scenario A:
    Recruiter = 2020technologies (Anamika Shukla)
    Client = Prince Pipes
    Job = Territory Sales Manager — Nizamabad
    Result:
    Company shown = Prince Pipes (NOT 2020technologies)
    """
    data = setup_company_data
    client = DjangoTestClient()
    client.force_login(data['recruiter_1'])

    # Post job via JobCreateView
    response = client.post(reverse('frontend:job_create'), {
        'title': 'Territory Sales Manager - Nizamabad',
        'client': str(data['client_prince_pipes'].id),
        'location': 'Nizamabad, Telangana',
        'job_type': 'FULL_TIME',
        'work_mode': 'ONSITE',
        'min_experience': 2,
        'max_experience': 5,
        'min_salary': 500000,
        'max_salary': 800000,
        'currency': 'INR',
        'description': 'Sales manager role in Nizamabad for Prince Pipes.'
    }, follow=True)

    assert response.status_code == 200
    job = Job.objects.filter(client=data['client_prince_pipes']).first()
    assert job is not None
    assert job.client == data['client_prince_pipes']
    assert job.display_company == "Prince Pipes"
    assert job.created_by == data['recruiter_1']

    # Check listing page
    list_resp = client.get(reverse('frontend:jobs'))
    assert list_resp.status_code == 200
    content = list_resp.content.decode('utf-8')
    assert "Territory Sales Manager" in content
    assert "Prince Pipes" in content

@pytest.mark.django_db
def test_scenario_b_multiple_recruiters_same_client(setup_company_data):
    """
    Scenario B:
    Recruiter 1 creates Prince Pipes job.
    Recruiter 2 creates another Prince Pipes job.
    Result:
    Both jobs appear under Prince Pipes in dropdown/table, never duplicated.
    """
    data = setup_company_data

    # Job 1 created by Recruiter 1
    job1 = Job.objects.create(
        title="Territory Sales Manager - Nizamabad",
        client=data['client_prince_pipes'],
        company=Company.objects.filter(name="Prince Pipes").first() or Company.objects.create(name="Prince Pipes", slug="prince-pipes"),
        created_by=data['recruiter_1'],
        location="Nizamabad",
        status="ACTIVE"
    )

    # Job 2 created by Recruiter 2
    job2 = Job.objects.create(
        title="Territory Sales Manager - Karimnagar",
        client=data['client_prince_pipes'],
        company=Company.objects.filter(name="Prince Pipes").first() or Company.objects.create(name="Prince Pipes", slug="prince-pipes-2"),
        created_by=data['recruiter_2'],
        location="Karimnagar",
        status="ACTIVE"
    )

    assert job1.display_company == "Prince Pipes"
    assert job2.display_company == "Prince Pipes"

    client = DjangoTestClient()
    client.force_login(data['recruiter_1'])

    # Listing page
    list_resp = client.get(reverse('frontend:jobs'))
    assert list_resp.status_code == 200
    companies_in_context = list_resp.context['companies']

    # Filter dropdown options must contain exactly one 'Prince Pipes'
    prince_options = [c for c in companies_in_context if c['name'].lower() == 'prince pipes']
    assert len(prince_options) == 1, f"Expected 1 Prince Pipes option, got: {prince_options}"

    # Filter by Prince Pipes UUID
    filter_resp = client.get(reverse('frontend:jobs') + f"?company={data['client_prince_pipes'].id}")
    assert filter_resp.status_code == 200
    jobs_listed = list(filter_resp.context['jobs'])
    assert len(jobs_listed) == 2
    assert job1 in jobs_listed
    assert job2 in jobs_listed

@pytest.mark.django_db
def test_scenario_c_recruiter_tech_mahindra_client(setup_company_data):
    """
    Scenario C:
    Recruiter = 2020technologies
    Client = Tech Mahindra
    Result:
    Company shown = Tech Mahindra, NOT 2020technologies.
    """
    data = setup_company_data
    client = DjangoTestClient()
    client.force_login(data['recruiter_1'])

    # Post job with Client = Tech Mahindra
    response = client.post(reverse('frontend:job_create'), {
        'title': 'Senior Java Developer',
        'client': str(data['client_tech_mahindra'].id),
        'location': 'Noida',
        'job_type': 'FULL_TIME',
        'work_mode': 'HYBRID',
        'min_experience': 4,
        'max_experience': 8,
        'min_salary': 1200000,
        'max_salary': 2000000,
        'currency': 'INR',
        'description': 'Tech Mahindra Java Developer role.'
    }, follow=True)

    assert response.status_code == 200
    job = Job.objects.get(title='Senior Java Developer')
    assert job.display_company == "Tech Mahindra"
    assert job.client.company_name == "Tech Mahindra"

    # Verify company filter dropdown does NOT substitute recruiter company for Tech Mahindra
    list_resp = client.get(reverse('frontend:jobs'))
    assert list_resp.status_code == 200
    companies_in_context = list_resp.context['companies']
    techm_options = [c for c in companies_in_context if 'tech mahindra' in c['name'].lower()]
    assert len(techm_options) == 1
    assert techm_options[0]['name'] == 'Tech Mahindra'

@pytest.mark.django_db
def test_company_filter_by_name_and_uuid(setup_company_data):
    """
    Test filtering by name, slug, and UUID for canonical hiring companies.
    """
    data = setup_company_data

    # Job for Prince Pipes
    job_pp = Job.objects.create(
        title="RSM Retail - pipes - Delhi",
        client=data['client_prince_pipes'],
        created_by=data['recruiter_1'],
        status="ACTIVE"
    )

    # Job for Tech Mahindra
    job_tm = Job.objects.create(
        title="Cloud Architect",
        client=data['client_tech_mahindra'],
        created_by=data['recruiter_1'],
        status="ACTIVE"
    )

    client = DjangoTestClient()
    client.force_login(data['recruiter_1'])

    # Filter by name "Prince Pipes"
    resp_name = client.get(reverse('frontend:jobs') + "?company=Prince+Pipes")
    assert resp_name.status_code == 200
    jobs = list(resp_name.context['jobs'])
    assert job_pp in jobs
    assert job_tm not in jobs

    # Filter by lowercase "prince pipes"
    resp_lower = client.get(reverse('frontend:jobs') + "?company=prince+pipes")
    assert resp_lower.status_code == 200
    jobs = list(resp_lower.context['jobs'])
    assert job_pp in jobs
    assert job_tm not in jobs

    # Filter by client UUID
    resp_uuid = client.get(reverse('frontend:jobs') + f"?company={data['client_tech_mahindra'].id}")
    assert resp_uuid.status_code == 200
    jobs = list(resp_uuid.context['jobs'])
    assert job_tm in jobs
    assert job_pp not in jobs

@pytest.mark.django_db
def test_public_and_candidate_company_display(setup_company_data):
    """
    Test candidate-facing and public share views display the hiring client company.
    """
    data = setup_company_data

    job = Job.objects.create(
        title="Territory Sales Manager - Nizamabad",
        client=data['client_prince_pipes'],
        created_by=data['recruiter_1'],
        location="Nizamabad",
        status="ACTIVE",
        min_salary=500000,
        max_salary=800000
    )

    client = DjangoTestClient()

    # Public share view
    share_url = reverse('frontend:public_job_share', kwargs={'pk': job.pk})
    resp_share = client.get(share_url)
    assert resp_share.status_code == 200
    share_html = resp_share.content.decode('utf-8')
    assert "Prince Pipes" in share_html

    # Candidate jobs list search by company
    cand_resp = client.get(reverse('frontend:jobs') + "?company=Prince+Pipes")
    assert cand_resp.status_code == 200
    cand_jobs = list(cand_resp.context['jobs'])
    assert job in cand_jobs
