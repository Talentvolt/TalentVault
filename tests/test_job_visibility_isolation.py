import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.jobs.models import Job
from utils.tenant import get_tenant_jobs_qs


@pytest.fixture
def visibility_data(db):
    admin = User.objects.create_superuser(
        email='admin_visibility@talentvault.in',
        password='Password123!',
        role=User.Role.SUPER_ADMIN,
    )

    company = Company.objects.create(
        name='External Recruiters Co',
        slug='external-recruiters-co',
        industry='Recruiting',
        location='India',
    )
    recruiter = User.objects.create_user(
        email='recruiter_visibility@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE,
    )
    CompanyMember.objects.create(user=recruiter, company=company, designation='Recruiter')

    other_company = Company.objects.create(
        name='Unrelated Recruiters Co',
        slug='unrelated-recruiters-co',
        industry='Recruiting',
        location='India',
    )
    other_recruiter = User.objects.create_user(
        email='other_recruiter_visibility@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE,
    )
    CompanyMember.objects.create(user=other_recruiter, company=other_company, designation='Recruiter')

    admin_job = Job.objects.create(
        title='Admin Internal Job',
        company=company,
        created_by=admin,
        status='ACTIVE',
    )
    recruiter_job = Job.objects.create(
        title='Recruiter Own Job',
        company=company,
        created_by=recruiter,
        status='ACTIVE',
    )
    legacy_job = Job.objects.create(
        title='Legacy Unassigned Job',
        company=company,
        created_by=None,
        status='ACTIVE',
    )

    return {
        'admin': admin,
        'recruiter': recruiter,
        'other_recruiter': other_recruiter,
        'admin_job': admin_job,
        'recruiter_job': recruiter_job,
        'legacy_job': legacy_job,
    }


@pytest.mark.django_db
def test_admin_sees_admin_and_recruiter_created_jobs(visibility_data):
    titles = set(get_tenant_jobs_qs(visibility_data['admin']).values_list('title', flat=True))
    assert 'Admin Internal Job' in titles
    assert 'Recruiter Own Job' in titles


@pytest.mark.django_db
def test_recruiter_cannot_see_admin_created_jobs(visibility_data):
    titles = set(get_tenant_jobs_qs(visibility_data['recruiter']).values_list('title', flat=True))
    assert 'Recruiter Own Job' in titles
    assert 'Admin Internal Job' not in titles


@pytest.mark.django_db
def test_recruiter_cannot_see_unrelated_recruiter_jobs(visibility_data):
    titles = set(get_tenant_jobs_qs(visibility_data['recruiter']).values_list('title', flat=True))
    other_titles = set(get_tenant_jobs_qs(visibility_data['other_recruiter']).values_list('title', flat=True))

    assert 'Recruiter Own Job' in titles
    assert 'Recruiter Own Job' not in other_titles


@pytest.mark.django_db
def test_recruiter_job_list_excludes_admin_jobs(visibility_data):
    client = Client()
    client.force_login(visibility_data['recruiter'])
    response = client.get(reverse('frontend:recruiter_jobs'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Recruiter Own Job' in html
    assert 'Admin Internal Job' not in html


@pytest.mark.django_db
def test_recruiter_direct_action_on_admin_job_is_blocked(visibility_data):
    client = Client()
    client.force_login(visibility_data['recruiter'])
    admin_job = visibility_data['admin_job']

    response = client.post(
        reverse('frontend:job_action', kwargs={'pk': admin_job.pk, 'action': 'close'})
    )
    assert response.status_code == 404

    admin_job.refresh_from_db()
    assert admin_job.status == 'ACTIVE'


@pytest.mark.django_db
def test_admin_dashboard_keeps_all_widgets_and_clients(visibility_data):
    client = Client()
    client.force_login(visibility_data['admin'])
    html = client.get(reverse('frontend:recruiter_dashboard')).content.decode('utf-8')

    assert 'My Tasks' in html
    assert 'Recent Applications' in html
    assert 'Candidate Signup Overview' in html
    assert reverse('clients:client_list') in html


@pytest.mark.django_db
def test_recruiter_dashboard_hides_widgets_and_clients(visibility_data):
    client = Client()
    client.force_login(visibility_data['recruiter'])
    html = client.get(reverse('frontend:recruiter_dashboard')).content.decode('utf-8')

    assert 'My Tasks' not in html
    assert 'Recent Applications' not in html
    assert 'Candidate Signup Overview' not in html
    assert reverse('clients:client_list') not in html


@pytest.mark.django_db
def test_admin_sidebar_keeps_candidates_and_talent_pool(visibility_data):
    client = Client()
    client.force_login(visibility_data['admin'])
    html = client.get(reverse('frontend:recruiter_dashboard')).content.decode('utf-8')

    assert '>Candidates<' in html
    assert '>Talent Pool<' in html


@pytest.mark.django_db
def test_recruiter_sidebar_removes_candidates_and_talent_pool(visibility_data):
    client = Client()
    client.force_login(visibility_data['recruiter'])
    html = client.get(reverse('frontend:recruiter_dashboard')).content.decode('utf-8')

    assert '>Candidates<' not in html
    assert '>Talent Pool<' not in html
    # Other recruiter navigation must remain intact
    assert '>Jobs<' in html
    assert '>Pipeline<' in html
    assert '>Interviews<' in html
    assert '>Talent Search<' in html
    assert '>Taxonomy &amp; Tagging<' in html
    assert '>Campaigns<' in html
    assert '>Resume Parser<' in html
    assert '>Analytics<' in html
    assert '>Settings<' in html
