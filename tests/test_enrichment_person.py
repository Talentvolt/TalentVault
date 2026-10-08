import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.candidates.models import CandidateProfile
from services.enrichment.mock_provider import MockEnrichmentProvider
from services.enrichment.person_match import PersonMatchService

EXT_ORIGIN = "chrome-extension://hneceobjjiehhicimdfdeheodcoklgec"


@pytest.fixture(autouse=True)
def _use_mock_provider(settings):
    settings.ENRICHMENT_PROVIDER = "mock"


ANANYA = {
    "name": "Ananya Deshmukh",
    "company": "NVIDIA",
    "title": "Principal AI Architect",
    "location": "Bengaluru, Karnataka, India",
    "profile_url": "https://www.linkedin.com/in/ananya-deshmukh-ai/",
}


@pytest.mark.django_db
def test_person_matching_full_match():
    provider = MockEnrichmentProvider()
    match = provider.match_person(ANANYA)
    assert match["matched"] is True
    assert match["confidence"] > 0.9


@pytest.mark.django_db
def test_person_matching_partial_match_name_company():
    provider = MockEnrichmentProvider()
    match = provider.match_person({"name": "Ananya Deshmukh", "company": "NVIDIA"})
    assert match["matched"] is True


@pytest.mark.django_db
def test_person_matching_no_match():
    provider = MockEnrichmentProvider()
    match = provider.match_person({"name": "Nobody Unknown", "company": "Acme Inc"})
    assert match["matched"] is False
    assert match["confidence"] == 0.0


@pytest.mark.django_db
def test_email_enrichment_found_verified():
    result = PersonMatchService.enrich(ANANYA, scope="email")
    assert result["matched"] is True
    assert result["email"]["value"] == "ananya.deshmukh@nvidia.com"
    assert result["email"]["status"] == "verified"
    assert result["phone"]["value"] is None
    assert result["phone"]["status"] == "not_found"


@pytest.mark.django_db
def test_phone_enrichment_found():
    result = PersonMatchService.enrich(ANANYA, scope="phone")
    assert result["matched"] is True
    assert result["phone"]["value"] == "+919876543210"
    assert result["phone"]["status"] == "found"


@pytest.mark.django_db
def test_email_and_phone_enrichment_not_found():
    vikram = {"name": "Vikram Singh", "company": "Infosys", "title": "Test Engineer"}
    result = PersonMatchService.enrich(vikram, scope="all")
    assert result["matched"] is True
    assert result["email"]["value"] is None
    assert result["email"]["status"] == "not_found"
    assert result["phone"]["value"] is None
    assert result["phone"]["status"] == "not_found"


@pytest.mark.django_db
def test_phone_enrichment_not_found_when_record_lacks_phone():
    rohan = {"name": "Rohan Sharma", "company": "Atlassian"}
    result = PersonMatchService.enrich(rohan, scope="phone")
    assert result["matched"] is True
    assert result["phone"]["value"] is None
    assert result["phone"]["status"] == "not_found"


@pytest.mark.django_db
def test_enrichment_api_endpoint_returns_shape():
    client = APIClient()
    url = reverse("api_person_enrichment")
    response = client.post(url, ANANYA, format="json", HTTP_ORIGIN=EXT_ORIGIN)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["matched"] is True
    assert "match_confidence" in data
    assert data["source"] == "mock"
    assert data["email"]["value"] == "ananya.deshmukh@nvidia.com"
    assert data["email"]["status"] == "verified"
    assert data["phone"]["value"] == "+919876543210"
    assert data["phone"]["status"] == "found"


@pytest.mark.django_db
def test_enrichment_api_endpoint_not_found():
    client = APIClient()
    url = reverse("api_person_enrichment")
    response = client.post(
        url,
        {"name": "Ghost Person", "company": "Nowhere"},
        format="json",
        HTTP_ORIGIN=EXT_ORIGIN,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["matched"] is False
    assert data["match_confidence"] == 0.0
    assert data["email"]["status"] == "not_found"
    assert data["phone"]["status"] == "not_found"


@pytest.mark.django_db
def test_enrichment_api_requires_person_data():
    client = APIClient()
    url = reverse("api_person_enrichment")
    response = client.post(url, {}, format="json", HTTP_ORIGIN=EXT_ORIGIN)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_enrichment_save_persists_validated_contacts_and_metadata():
    client = APIClient()

    # 1. Import a candidate first (mirrors the extension Save flow).
    import_url = reverse("api_candidate_import")
    import_payload = {
        "name": "Ananya Deshmukh",
        "headline": "Principal AI Architect",
        "current_company": "NVIDIA",
        "location": "Bengaluru, Karnataka, India",
        "profile_url": "https://www.linkedin.com/in/ananya-deshmukh-ai/",
        "source": "linkedin",
    }
    import_resp = client.post(import_url, import_payload, format="json", HTTP_ORIGIN=EXT_ORIGIN)
    assert import_resp.status_code == status.HTTP_201_CREATED
    candidate_id = import_resp.json()["candidate_id"]

    # 2. Enrich + save the returned, validated contacts.
    enrich_url = reverse("api_person_enrichment")
    enrich_resp = client.post(
        enrich_url,
        {**ANANYA, "save": True},
        format="json",
        HTTP_ORIGIN=EXT_ORIGIN,
    )
    assert enrich_resp.status_code == status.HTTP_200_OK
    data = enrich_resp.json()
    assert data["save"]["saved"] is True
    assert data["save"]["candidate_id"] == candidate_id

    profile = CandidateProfile.objects.get(id=candidate_id)
    assert profile.user.email == "ananya.deshmukh@nvidia.com"
    assert profile.user.phone_number == "+919876543210"

    enrichment_meta = profile.parsed_json["enrichment"]
    assert enrichment_meta["source"] == "mock"
    assert enrichment_meta["confidence"] > 0.9
    assert enrichment_meta["email"]["status"] == "verified"
    assert enrichment_meta["phone"]["status"] == "found"
    assert "last_verified_at" in enrichment_meta
