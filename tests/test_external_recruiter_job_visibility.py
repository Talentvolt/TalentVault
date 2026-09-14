import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.jobs.models import Job
from utils.tenant import get_tenant_jobs_qs


@pytest.fixture
def portal_setup(db):
    admin = User.objects.create_superuser(
        email='admin_portal@talentvault.in',
        password='Password123!',
        role=User.Role.SUPER_ADMIN,
    )

    company_1 = Company.objects.create(
        name='TechHire Agency',
        slug='techhire-agency',
        industry='Staffing',
        location='Mumbai',
    )
    recruiter_1 = User.objects.create_user(
        email='recruiter1@techhire.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE,
    )
    CompanyMember.objects.create(user=recruiter_1, company=company_1, designation='Lead Recruiter')

    company_2 = Company.objects.create(
        name='AlphaStaff',
        slug='alphastaff',
        industry='Consulting',
        location='Delhi',
    )
    recruiter_2 = User.objects.create_user(
        email='recruiter2@alphastaff.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE,
    )
    CompanyMember.objects.create(user=recruiter_2, company=company_2, designation='Recruiter')

    return {
        'admin': admin,
        'recruiter_1': recruiter_1,
        'company_1': company_1,
        'recruiter_2': recruiter_2,
        'company_2': company_2,
    }


@pytest.mark.django_db
def test_scenario_a_external_recruiter_creates_job(portal_setup):
    client = Client()
    recruiter = portal_setup['recruiter_1']
    admin = portal_setup['admin']

    client.force_login(recruiter)

    post_data = {
        'action': 'create',
        'title': 'Frontend React Engineer',
        'department': 'Engineering',
        'job_type': 'FULL_TIME',
        'location': 'Mumbai',
        'min_experience': '2',
        'max_experience': '5',
        'min_salary': '600000',
        'max_salary': '1200000',
        'required_skills': 'React, JavaScript, CSS',
        'preferred_skills': 'TypeScript',
        'education': 'B.Tech / B.E.',
        'notice_period': '30',
        'description': 'Building world-class frontend applications.',
    }
    response = client.post(reverse('frontend:recruiter_jobs'), data=post_data)
    assert response.status_code in [200, 302]

    created_job = Job.objects.get(title='Frontend React Engineer')
    assert created_job.created_by == recruiter

    recruiter_jobs_qs = get_tenant_jobs_qs(recruiter)
    assert created_job in recruiter_jobs_qs

    resp_recruiter = client.get(reverse('frontend:recruiter_jobs'))
    assert resp_recruiter.status_code == 200
    assert 'Frontend React Engineer' in resp_recruiter.content.decode('utf-8')

    admin_jobs_qs = get_tenant_jobs_qs(admin)
    assert created_job in admin_jobs_qs

    admin_client = Client()
    admin_client.force_login(admin)
    resp_admin = admin_client.get(reverse('frontend:jobs'))
    assert resp_admin.status_code == 200
    assert 'Frontend React Engineer' in resp_admin.content.decode('utf-8')


@pytest.mark.django_db
def test_scenario_b_admin_creates_job(portal_setup):
    admin = portal_setup['admin']
    recruiter = portal_setup['recruiter_1']

    admin_client = Client()
    admin_client.force_login(admin)

    admin_job = Job.objects.create(
        title='Confidential VP of Operations',
        company=portal_setup['company_1'],
        created_by=admin,
        status='ACTIVE',
        location='Bangalore',
    )

    admin_jobs_qs = get_tenant_jobs_qs(admin)
    assert admin_job in admin_jobs_qs

    resp_admin = admin_client.get(reverse('frontend:jobs'))
    assert resp_admin.status_code == 200
    assert 'Confidential VP of Operations' in resp_admin.content.decode('utf-8')

    recruiter_jobs_qs = get_tenant_jobs_qs(recruiter)
    assert admin_job not in recruiter_jobs_qs

    recruiter_client = Client()
    recruiter_client.force_login(recruiter)
    resp_recruiter = recruiter_client.get(reverse('frontend:recruiter_jobs'))
    assert resp_recruiter.status_code == 200
    assert 'Confidential VP of Operations' not in resp_recruiter.content.decode('utf-8')

    resp_recruiter_all_jobs = recruiter_client.get(reverse('frontend:jobs'))
    assert resp_recruiter_all_jobs.status_code == 200
    assert 'Confidential VP of Operations' not in resp_recruiter_all_jobs.content.decode('utf-8')


@pytest.mark.django_db
def test_scenario_c_direct_url_access_denied_safely(portal_setup):
    admin = portal_setup['admin']
    recruiter = portal_setup['recruiter_1']

    admin_job = Job.objects.create(
        title='Internal Executive Secret Job',
        company=portal_setup['company_1'],
        created_by=admin,
        status='ACTIVE',
        location='Confidential',
    )

    recruiter_client = Client()
    recruiter_client.force_login(recruiter)

    resp_edit = recruiter_client.get(reverse('frontend:job_edit', kwargs={'pk': admin_job.pk}))
    assert resp_edit.status_code == 404

    resp_delete = recruiter_client.get(reverse('frontend:job_delete', kwargs={'pk': admin_job.pk}))
    assert resp_delete.status_code == 404

    resp_action = recruiter_client.post(
        reverse('frontend:job_action', kwargs={'pk': admin_job.pk, 'action': 'close'})
    )
    assert resp_action.status_code == 404
    admin_job.refresh_from_db()
    assert admin_job.status == 'ACTIVE'

    resp_candidates = recruiter_client.get(
        reverse('frontend:job_candidates', kwargs={'job_id': admin_job.pk})
    )
    assert resp_candidates.status_code == 404

    resp_rec_cand = recruiter_client.get(
        f"{reverse('frontend:recruiter_candidates')}?job_id={admin_job.pk}"
    )
    assert resp_rec_cand.status_code == 200
    assert 'Internal Executive Secret Job' not in resp_rec_cand.content.decode('utf-8')


@pytest.mark.django_db
def test_scenario_d_admin_opens_and_manages_recruiter_job(portal_setup):
    admin = portal_setup['admin']
    recruiter = portal_setup['recruiter_1']

    recruiter_job = Job.objects.create(
        title='Backend Python Specialist',
        company=portal_setup['company_1'],
        created_by=recruiter,
        status='ACTIVE',
        location='Pune',
    )

    admin_client = Client()
    admin_client.force_login(admin)

    resp_edit = admin_client.get(reverse('frontend:job_edit', kwargs={'pk': recruiter_job.pk}))
    assert resp_edit.status_code == 200
    assert 'Backend Python Specialist' in resp_edit.content.decode('utf-8')

    resp_close = admin_client.post(
        reverse('frontend:job_action', kwargs={'pk': recruiter_job.pk, 'action': 'close'})
    )
    assert resp_close.status_code in [200, 302]

    recruiter_job.refresh_from_db()
    assert recruiter_job.status == 'CLOSED'
    assert recruiter_job.closed_by == admin
    assert recruiter_job.created_by == recruiter


@pytest.mark.django_db
def test_scenario_rule_3_unrelated_recruiter_isolation(portal_setup):
    recruiter_1 = portal_setup['recruiter_1']
    recruiter_2 = portal_setup['recruiter_2']

    job_1 = Job.objects.create(
        title='Agency 1 Private Role',
        company=portal_setup['company_1'],
        created_by=recruiter_1,
        status='ACTIVE',
    )
    job_2 = Job.objects.create(
        title='Agency 2 Private Role',
        company=portal_setup['company_2'],
        created_by=recruiter_2,
        status='ACTIVE',
    )

    r1_titles = set(get_tenant_jobs_qs(recruiter_1).values_list('title', flat=True))
    r2_titles = set(get_tenant_jobs_qs(recruiter_2).values_list('title', flat=True))

    assert 'Agency 1 Private Role' in r1_titles
    assert 'Agency 2 Private Role' not in r1_titles

    assert 'Agency 2 Private Role' in r2_titles
    assert 'Agency 1 Private Role' not in r2_titles
