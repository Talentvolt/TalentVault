import pytest
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from services.enrichment.http_provider import HTTPEnrichmentProvider
from services.enrichment.person_match import PersonMatchService
from services.enrichment.providers import EnrichmentProviderError

EXT_ORIGIN = "chrome-extension://hneceobjjiehhicimdfdeheodcoklgec"

PERSON = {
    "name": "Ananya Deshmukh",
    "company": "NVIDIA",
    "title": "Principal AI Architect",
    "location": "Bengaluru, Karnataka, India",
    "profile_url": "https://www.linkedin.com/in/ananya-deshmukh-ai/",
}


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.headers = {}
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.django_db
@override_settings(
    ENRICHMENT_BASE_URL="https://enrich.example.internal",
    ENRICHMENT_API_KEY="secret-key",
)
def test_http_provider_sends_expected_payload_and_auth():
    provider = HTTPEnrichmentProvider()

    with patch("services.enrichment.http_provider.requests.post") as post:
        post.return_value = _FakeResponse(200, {"email": None, "phone": None, "confidence": 1.0})
        provider.match_person(PERSON)

    call = post.call_args
    assert call.kwargs["json"] == {
        "name": "Ananya Deshmukh",
        "company": "NVIDIA",
        "title": "Principal AI Architect",
        "location": "Bengaluru, Karnataka, India",
        "linkedin_url": "https://www.linkedin.com/in/ananya-deshmukh-ai/",
    }
    assert call.kwargs["headers"]["X-Api-Key"] == "secret-key"
    assert post.call_args.args[0] == "https://enrich.example.internal/api/v1/enrich"


@pytest.mark.django_db
@override_settings(
    ENRICHMENT_BASE_URL="https://enrich.example.internal",
    ENRICHMENT_API_KEY="secret-key",
)
def test_http_provider_full_enrichment():
    provider = HTTPEnrichmentProvider()

    with patch("services.enrichment.http_provider.requests.post") as post:
        post.return_value = _FakeResponse(
            200,
            {
                "email": "ANANYA.DESHMUKH@nvidia.com",
                "phone": "+91 98765 43210",
                "confidence": 0.95,
                "email_verified": True,
                "phone_verified": False,
            },
        )
        result = PersonMatchService.enrich(PERSON, scope="all", provider=provider)

    assert result["matched"] is True
    assert result["match_confidence"] == 0.95
    assert result["source"] == "http"
    assert result["email"]["value"] == "ananya.deshmukh@nvidia.com"
    assert result["email"]["status"] == "verified"
    assert result["phone"]["value"] == "+919876543210"
    assert result["phone"]["status"] == "unverified"


@pytest.mark.django_db
@override_settings(
    ENRICHMENT_BASE_URL="https://enrich.example.internal",
    ENRICHMENT_API_KEY="secret-key",
)
def test_http_provider_email_only_scope():
    provider = HTTPEnrichmentProvider()

    with patch("services.enrichment.http_provider.requests.post") as post:
        post.return_value = _FakeResponse(
            200,
            {"email": "x@y.com", "phone": "+918888888888", "confidence": 0.9},
        )
        result = PersonMatchService.enrich(PERSON, scope="email", provider=provider)

    assert result["email"]["status"] == "found"
    assert result["email"]["value"] == "x@y.com"
    # phone not requested -> not_found
    assert result["phone"]["value"] is None
    assert result["phone"]["status"] == "not_found"


@pytest.mark.django_db
@override_settings(
    ENRICHMENT_BASE_URL="https://enrich.example.internal",
    ENRICHMENT_API_KEY="secret-key",
)
def test_http_provider_person_not_found_404():
    provider = HTTPEnrichmentProvider()

    with patch("services.enrichment.http_provider.requests.post") as post:
        post.return_value = _FakeResponse(404, {"error": "not found"})
        result = PersonMatchService.enrich(PERSON, scope="all", provider=provider)

    assert result["matched"] is False
    assert result["match_confidence"] == 0.0
    assert result["email"]["status"] == "not_found"
    assert result["phone"]["status"] == "not_found"


@pytest.mark.django_db
@override_settings(
    ENRICHMENT_BASE_URL="https://enrich.example.internal",
    ENRICHMENT_API_KEY="secret-key",
)
def test_http_provider_auth_rejection_raises():
    provider = HTTPEnrichmentProvider()

    with patch("services.enrichment.http_provider.requests.post") as post:
        post.return_value = _FakeResponse(401, {"error": "unauthorized"})
        with pytest.raises(EnrichmentProviderError):
            provider.match_person(PERSON)


@pytest.mark.django_db
@override_settings(ENRICHMENT_BASE_URL="", ENRICHMENT_API_KEY="")
def test_http_provider_requires_configuration():
    provider = HTTPEnrichmentProvider()

    with pytest.raises(EnrichmentProviderError):
        provider.match_person(PERSON)


@pytest.mark.django_db
@override_settings(
    ENRICHMENT_PROVIDER="http",
    ENRICHMENT_BASE_URL="https://enrich.example.internal",
    ENRICHMENT_API_KEY="secret-key",
)
def test_enrichment_api_endpoint_uses_http_provider():
    client = APIClient()
    url = reverse("api_person_enrichment")

    with patch("services.enrichment.http_provider.requests.post") as post:
        post.return_value = _FakeResponse(
            200,
            {
                "email": "ananya@nvidia.com",
                "phone": "+919876543210",
                "confidence": 0.97,
                "email_verified": True,
            },
        )
        response = client.post(url, PERSON, format="json", HTTP_ORIGIN=EXT_ORIGIN)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["source"] == "http"
    assert data["matched"] is True
    assert data["email"]["value"] == "ananya@nvidia.com"
    assert data["email"]["status"] == "verified"
    assert data["phone"]["status"] == "found"
