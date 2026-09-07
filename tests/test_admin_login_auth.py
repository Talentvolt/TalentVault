import pytest

from apps.accounts.models import User

ADMIN_LOGIN_URL = "/accounts/login/admin/"
ADMIN_DASHBOARD_URL = "/dashboard/recruiter/"
LOGOUT_URL = "/accounts/logout/"


def _make_superuser(email="admin@example.com", password="AdminPass123!", **kwargs):
    return User.objects.create_superuser(email=email, password=password, **kwargs)


@pytest.mark.django_db
def test_admin_login_success_dashboard_and_logout(client):
    """1. Valid admin email + password -> login OK.
    4. Successful login -> dashboard accessible.
    5. Logout -> dashboard no longer accessible."""
    user = _make_superuser(email="admin@example.com", password="AdminPass123!")
    assert user.is_active and user.is_staff and user.is_superuser

    # 1. Valid credentials redirect to the dashboard
    resp = client.post(
        ADMIN_LOGIN_URL,
        {"email": "Admin@Example.com", "password": "AdminPass123!"},
    )
    assert resp.status_code == 302
    assert resp.get("Location") == ADMIN_DASHBOARD_URL
    assert "_auth_user_id" in client.session

    # 4. Dashboard is reachable after login
    dash = client.get(ADMIN_DASHBOARD_URL)
    assert dash.status_code == 200

    # 5. After logout the dashboard is no longer accessible
    out = client.post(LOGOUT_URL)
    assert out.status_code in (200, 302)
    assert "_auth_user_id" not in client.session
    blocked = client.get(ADMIN_DASHBOARD_URL)
    assert blocked.status_code == 302  # redirected away (unauthenticated)


@pytest.mark.django_db
def test_admin_login_rejects_wrong_password(client):
    """2. Invalid password -> rejected."""
    _make_superuser(email="admin@example.com", password="AdminPass123!")
    resp = client.post(
        ADMIN_LOGIN_URL,
        {"email": "admin@example.com", "password": "WrongPassword!"},
    )
    assert resp.status_code == 200
    assert b"Invalid email or password." in resp.content
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_admin_login_rejects_inactive_user(client):
    """3. Inactive admin user -> rejected."""
    user = _make_superuser(email="inactive@example.com", password="AdminPass123!")
    user.is_active = False
    user.save()

    resp = client.post(
        ADMIN_LOGIN_URL,
        {"email": "inactive@example.com", "password": "AdminPass123!"},
    )
    assert resp.status_code == 200
    assert b"disabled" in resp.content.lower()
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_admin_login_rejects_non_admin_user(client):
    """3. Non-admin (candidate) user -> rejected."""
    user = User.objects.create_user(
        email="candidate@example.com",
        password="CandidatePass123!",
        role=User.Role.CANDIDATE,
    )
    user.is_active = True
    user.is_verified = True
    user.save()

    resp = client.post(
        ADMIN_LOGIN_URL,
        {"email": "candidate@example.com", "password": "CandidatePass123!"},
    )
    assert resp.status_code == 200
    assert b"Access denied" in resp.content
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_admin_login_matches_email_case_insensitively(client):
    """Regression: correct credentials must work even when the stored email is
    not lowercase (admin login looks up by email identifier, case-insensitively)."""
    user = _make_superuser(email="adminmixed@example.com", password="AdminPass123!")
    # Emulate a legacy row whose stored email kept uppercase (bypasses model save()
    # normalization, e.g. created via raw import / bulk insert).
    User.objects.filter(pk=user.pk).update(email="AdminMixed@ExampleMail.io")

    resp = client.post(
        ADMIN_LOGIN_URL,
        {"email": "adminmixed@examplemail.io", "password": "AdminPass123!"},
    )
    assert resp.status_code == 302
    assert resp.get("Location") == ADMIN_DASHBOARD_URL
    assert "_auth_user_id" in client.session
