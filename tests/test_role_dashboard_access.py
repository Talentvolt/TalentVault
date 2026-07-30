import pytest
from django.test import Client
from apps.accounts.models import User
import re

@pytest.mark.django_db
def test_admin_login_accesses_shared_recruiter_dashboard():
    admin = User.objects.create_superuser(
        email='super_admin_test@talentvault.in',
        password='Password123!',
        role=User.Role.SUPER_ADMIN,
        is_active=True
    )

    client = Client(enforce_csrf_checks=True)

    # GET admin login
    get_res = client.get('/accounts/login/admin/', HTTP_HOST='127.0.0.1:8000')
    assert get_res.status_code == 200
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', get_res.content.decode('utf-8'))
    assert match is not None
    csrf_token = match.group(1)

    # POST admin login
    post_res = client.post(
        '/accounts/login/admin/',
        {
            'csrfmiddlewaretoken': csrf_token,
            'email': 'super_admin_test@talentvault.in',
            'password': 'Password123!'
        },
        HTTP_HOST='127.0.0.1:8000',
        HTTP_ORIGIN='http://127.0.0.1:8000',
        HTTP_REFERER='http://127.0.0.1:8000/accounts/login/admin/',
        follow=True
    )

    assert post_res.status_code == 200
    assert post_res.redirect_chain[-1][0] == '/dashboard/recruiter/'
    assert b"TalentVault" in post_res.content


@pytest.mark.django_db
def test_recruiter_login_accesses_shared_recruiter_dashboard():
    recruiter = User.objects.create_user(
        email='recruiter_test@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE,
        is_active=True
    )

    client = Client(enforce_csrf_checks=True)

    # GET employer login
    get_res = client.get('/accounts/login/employer/', HTTP_HOST='127.0.0.1:8000')
    assert get_res.status_code == 200
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', get_res.content.decode('utf-8'))
    assert match is not None
    csrf_token = match.group(1)

    # POST employer login
    post_res = client.post(
        '/accounts/login/employer/',
        {
            'csrfmiddlewaretoken': csrf_token,
            'email': 'recruiter_test@company.com',
            'password': 'Password123!'
        },
        HTTP_HOST='127.0.0.1:8000',
        HTTP_ORIGIN='http://127.0.0.1:8000',
        HTTP_REFERER='http://127.0.0.1:8000/accounts/login/employer/',
        follow=True
    )

    assert post_res.status_code == 200
    assert post_res.redirect_chain[-1][0] == '/dashboard/recruiter/'


@pytest.mark.django_db
def test_company_admin_login_accesses_shared_recruiter_dashboard():
    company_admin = User.objects.create_user(
        email='company_admin_test@company.com',
        password='Password123!',
        role=User.Role.COMPANY_ADMIN,
        recruiter_status=User.RecruiterStatus.ACTIVE,
        is_active=True
    )

    client = Client(enforce_csrf_checks=True)

    # GET employer login
    get_res = client.get('/accounts/login/employer/', HTTP_HOST='127.0.0.1:8000')
    assert get_res.status_code == 200
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', get_res.content.decode('utf-8'))
    assert match is not None
    csrf_token = match.group(1)

    # POST employer login
    post_res = client.post(
        '/accounts/login/employer/',
        {
            'csrfmiddlewaretoken': csrf_token,
            'email': 'company_admin_test@company.com',
            'password': 'Password123!'
        },
        HTTP_HOST='127.0.0.1:8000',
        HTTP_ORIGIN='http://127.0.0.1:8000',
        HTTP_REFERER='http://127.0.0.1:8000/accounts/login/employer/',
        follow=True
    )

    assert post_res.status_code == 200
    assert post_res.redirect_chain[-1][0] == '/dashboard/recruiter/'
