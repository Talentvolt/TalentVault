import json

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User

EXT_ORIGIN = "chrome-extension://egcfpgbhoklbacaijdachfbemffnfejp"
OTHER_ORIGIN = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

PAYLOAD = {
    "full_name": "CSRF Test Candidate",
    "current_designation": "Software Engineer",
    "current_company": "Acme Corp",
    "location": "Pune",
    "source": "linkedin",
}


@pytest.fixture
def authenticated_client(db):
    user = User.objects.create_user(
        email="recruiter_csrf@talentvault.in",
        password="Password123!",
        role=User.Role.RECRUITER,
        is_active=True,
    )
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    return client


def _get_csrf_token(client, url):
    res = client.get(url, HTTP_ORIGIN=EXT_ORIGIN)
    assert res.status_code == 200
    return res.json()["csrfToken"]


def _post(client, url, token=None, origin=EXT_ORIGIN):
    kwargs = {
        "data": json.dumps(PAYLOAD),
        "content_type": "application/json",
        "HTTP_ORIGIN": origin,
    }
    if token is not None:
        kwargs["HTTP_X_CSRFTOKEN"] = token
    return client.post(url, **kwargs)


@pytest.mark.django_db
def test_valid_authenticated_save_succeeds(authenticated_client):
    url = reverse("api_candidate_import")

    token = _get_csrf_token(authenticated_client, url)
    res = _post(authenticated_client, url, token=token)

    assert res.status_code == 201
    assert res.json()["status"] == "success"


@pytest.mark.django_db
def test_missing_csrf_token_rejected(authenticated_client):
    url = reverse("api_candidate_import")

    _get_csrf_token(authenticated_client, url)
    res = _post(authenticated_client, url)

    assert res.status_code == 403


@pytest.mark.django_db
def test_invalid_csrf_token_rejected(authenticated_client):
    url = reverse("api_candidate_import")

    _get_csrf_token(authenticated_client, url)
    res = _post(authenticated_client, url, token="invalidtokenvalue")

    assert res.status_code == 403


@pytest.mark.django_db
def test_different_extension_origin_rejected(authenticated_client):
    url = reverse("api_candidate_import")

    token = _get_csrf_token(authenticated_client, url)
    res = _post(authenticated_client, url, token=token, origin=OTHER_ORIGIN)

    assert res.status_code == 403
