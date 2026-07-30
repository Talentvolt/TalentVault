import pytest
from django.test import Client
from apps.accounts.models import User
import re

@pytest.mark.django_db
def test_admin_login_csrf_verification_success():
    admin = User.objects.create_superuser(
        email='admin_csrf_valid@talentvault.in',
        password='Password123!',
        role=User.Role.SUPER_ADMIN,
        is_active=True
    )

    client = Client(enforce_csrf_checks=True)

    # Step 1: GET admin login page
    get_res = client.get('/accounts/login/admin/', HTTP_HOST='127.0.0.1:8000')
    assert get_res.status_code == 200
    assert 'csrftoken' in get_res.cookies

    # Extract CSRF token from HTML form
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', get_res.content.decode('utf-8'))
    assert match is not None
    csrf_token = match.group(1)

    # Step 2: POST login form with valid CSRF token
    post_res = client.post(
        '/accounts/login/admin/',
        {
            'csrfmiddlewaretoken': csrf_token,
            'email': 'admin_csrf_valid@talentvault.in',
            'password': 'Password123!'
        },
        HTTP_HOST='127.0.0.1:8000',
        HTTP_ORIGIN='http://127.0.0.1:8000',
        HTTP_REFERER='http://127.0.0.1:8000/accounts/login/admin/',
        follow=True
    )

    assert post_res.status_code == 200
    assert post_res.redirect_chain[-1][0] == '/dashboard/recruiter/'


@pytest.mark.django_db
def test_admin_login_invalid_csrf_rejected():
    client = Client(enforce_csrf_checks=True)

    # GET page to get CSRF cookie
    client.get('/accounts/login/admin/', HTTP_HOST='127.0.0.1:8000')

    # POST with invalid csrfmiddlewaretoken
    post_res = client.post(
        '/accounts/login/admin/',
        {
            'csrfmiddlewaretoken': 'invalid_token_123',
            'email': 'admin@talentvault.in',
            'password': 'Password123!'
        },
        HTTP_HOST='127.0.0.1:8000',
        HTTP_ORIGIN='http://127.0.0.1:8000',
        HTTP_REFERER='http://127.0.0.1:8000/accounts/login/admin/'
    )

    assert post_res.status_code == 403


@pytest.mark.django_db
def test_logout_preserves_csrf_cookie_validity_for_subsequent_login():
    admin = User.objects.create_superuser(
        email='admin_logout_test@talentvault.in',
        password='Password123!',
        role=User.Role.SUPER_ADMIN,
        is_active=True
    )

    client = Client(enforce_csrf_checks=True)

    # 1. Login
    get_res = client.get('/accounts/login/admin/', HTTP_HOST='127.0.0.1:8000')
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', get_res.content.decode('utf-8'))
    csrf_token = match.group(1)

    client.post(
        '/accounts/login/admin/',
        {
            'csrfmiddlewaretoken': csrf_token,
            'email': 'admin_logout_test@talentvault.in',
            'password': 'Password123!'
        },
        HTTP_HOST='127.0.0.1:8000',
        HTTP_ORIGIN='http://127.0.0.1:8000',
        HTTP_REFERER='http://127.0.0.1:8000/accounts/login/admin/'
    )

    # 2. Logout
    logout_res = client.get('/accounts/logout/', HTTP_HOST='127.0.0.1:8000')
    assert logout_res.status_code in (200, 302)

    # 3. GET admin login again
    get_res2 = client.get('/accounts/login/admin/', HTTP_HOST='127.0.0.1:8000')
    assert get_res2.status_code == 200
    match2 = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', get_res2.content.decode('utf-8'))
    assert match2 is not None
    csrf_token2 = match2.group(1)

    # 4. Login again with new token
    post_res2 = client.post(
        '/accounts/login/admin/',
        {
            'csrfmiddlewaretoken': csrf_token2,
            'email': 'admin_logout_test@talentvault.in',
            'password': 'Password123!'
        },
        HTTP_HOST='127.0.0.1:8000',
        HTTP_ORIGIN='http://127.0.0.1:8000',
        HTTP_REFERER='http://127.0.0.1:8000/accounts/login/admin/',
        follow=True
    )

    assert post_res2.status_code == 200
    assert post_res2.redirect_chain[-1][0] == '/dashboard/recruiter/'
