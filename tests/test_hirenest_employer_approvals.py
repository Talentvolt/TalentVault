"""
TalentVault Admin Portal — HireNest Australia employer approvals integration.

These tests verify the admin-only proxy view. The view never touches the
HireNest database directly; it calls the HireNest admin API, so the HTTP calls
are mocked here.
"""
from unittest import mock

import pytest
from django.urls import reverse

from apps.accounts.models import User


URL_NAME = 'frontend:admin_hirenest_employer_approvals'


def _fake_response(employers, status_code=200):
    response = mock.Mock()
    response.status_code = status_code
    response.json.return_value = {'employers': employers}
    response.raise_for_status.return_value = None
    return response


@pytest.mark.django_db
def test_admin_can_access_hirenest_approvals(client, settings):
    settings.HIRENEST_API_BASE_URL = 'https://hirenest.example'
    settings.HIRENEST_ADMIN_API_KEY = 'test-key'

    admin = User.objects.create_superuser(email='tv.admin@example.com', password='AdminPass123!')
    client.force_login(admin)

    employers = [{
        'id': '11111111-1111-1111-1111-111111111111',
        'company_name': 'Aussie Co Pty Ltd',
        'contact_name': 'Alex Recruiter',
        'email': 'hr@aussieco.com',
        'phone': '+61 2 9000 0000',
        'industry': 'Technology',
        'location': 'Sydney NSW',
        'website': 'https://aussieco.com',
        'status': 'PENDING',
        'registration_date': '2026-01-01T00:00:00+00:00',
    }]

    with mock.patch('requests.get', return_value=_fake_response(employers)) as mocked:
        response = client.get(reverse(URL_NAME))

    assert response.status_code == 200
    assert b'HireNest Australia Approvals' in response.content
    assert b'Aussie Co Pty Ltd' in response.content
    # The secret is sent server-side only.
    _, kwargs = mocked.call_args
    assert kwargs['headers']['X-HireNest-Admin-Key'] == 'test-key'


@pytest.mark.django_db
def test_non_admin_cannot_access_hirenest_approvals(client, settings):
    settings.HIRENEST_API_BASE_URL = 'https://hirenest.example'
    settings.HIRENEST_ADMIN_API_KEY = 'test-key'

    recruiter = User.objects.create_user(
        email='recruiter@talentvault.in',
        password='RecruiterPass123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE,
    )
    client.force_login(recruiter)

    response = client.get(reverse(URL_NAME))
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_anonymous_cannot_access_hirenest_approvals(client):
    response = client.get(reverse(URL_NAME))
    assert response.status_code in (302, 403)
