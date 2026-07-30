import pytest
from django.test import Client
from apps.accounts.models import User

@pytest.mark.django_db
def test_admin_login_redirects_strictly_to_admin_dashboard():
    admin = User.objects.create_superuser(
        email='super_admin@talentvault.in',
        password='Password123!',
        role=User.Role.SUPER_ADMIN
    )
    client = Client()
    response = client.post('/accounts/login/admin/', {
        'email': 'super_admin@talentvault.in',
        'password': 'Password123!'
    }, follow=True)

    assert response.status_code == 200
    assert response.redirect_chain[-1][0] == '/dashboard/recruiter/'


@pytest.mark.django_db
def test_recruiter_login_redirects_strictly_to_recruiter_dashboard():
    recruiter = User.objects.create_user(
        email='active_recruiter@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE
    )
    client = Client()
    response = client.post('/accounts/login/employer/', {
        'email': 'active_recruiter@company.com',
        'password': 'Password123!'
    }, follow=True)

    assert response.status_code == 200
    assert response.redirect_chain[-1][0] == '/dashboard/recruiter/'


@pytest.mark.django_db
def test_candidate_login_redirects_strictly_to_candidate_dashboard():
    candidate = User.objects.create_user(
        email='candidate_user@gmail.com',
        password='Password123!',
        role=User.Role.CANDIDATE,
        is_verified=True
    )
    client = Client()
    response = client.post('/accounts/login/candidate/', {
        'email': 'candidate_user@gmail.com',
        'password': 'Password123!'
    }, follow=True)

    assert response.status_code == 200
    assert response.redirect_chain[-1][0] == '/dashboard/candidate/'


@pytest.mark.django_db
def test_cross_login_prevention():
    client = Client()
    recruiter = User.objects.create_user(
        email='rec_user@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE
    )

    # Recruiter attempting Admin login page -> rejected
    admin_login_res = client.post('/accounts/login/admin/', {
        'email': 'rec_user@company.com',
        'password': 'Password123!'
    })
    assert admin_login_res.status_code == 200
    assert "Access denied. Only system administrators can log in here." in admin_login_res.content.decode('utf-8')


@pytest.mark.django_db
def test_recruiter_blocked_from_admin_dashboard_middleware():
    recruiter = User.objects.create_user(
        email='rec_block@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE
    )
    client = Client()
    client.force_login(recruiter)

    # Recruiter attempting /dashboard/admin/ -> redirected to /dashboard/recruiter/
    res = client.get('/dashboard/admin/', follow=True)
    assert res.status_code == 200
    assert res.redirect_chain[-1][0] == '/dashboard/recruiter/'


@pytest.mark.django_db
def test_admin_dashboard_get_returns_200_ok_directly():
    admin = User.objects.create_superuser(
        email='direct_admin@talentvault.in',
        password='Password123!'
    )
    client = Client()
    client.force_login(admin)

    res = client.get('/dashboard/admin/', follow=True)
    assert res.status_code == 200
    assert res.redirect_chain[-1][0] == '/dashboard/recruiter/'


@pytest.mark.django_db
def test_django_admin_accounts_user_returns_200_ok():
    admin = User.objects.create_superuser(
        email='django_admin_user@talentvault.in',
        password='Password123!',
        is_staff=True,
        is_superuser=True
    )
    client = Client()
    client.force_login(admin)

    # GET /admin/accounts/user/ -> MUST return HTTP 200 OK directly, NO 404
    res = client.get('/admin/accounts/user/')
    assert res.status_code == 200
