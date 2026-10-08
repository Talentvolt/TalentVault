import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.candidates.management.commands.import_enrichment_people import import_people
from apps.candidates.models import EnrichmentPerson
from services.enrichment.native_provider import NativeEnrichmentProvider
from services.enrichment.person_match import PersonMatchService

EXT_ORIGIN = "chrome-extension://hneceobjjiehhicimdfdeheodcoklgec"

PERSON = {
    "name": "Ananya Deshmukh",
    "company": "NVIDIA",
    "title": "Principal AI Architect",
    "location": "Bengaluru, Karnataka, India",
    "profile_url": "https://www.linkedin.com/in/ananya-deshmukh-ai/",
}

DATASET = [
    {
        "name": "Ananya Deshmukh",
        "company": "NVIDIA",
        "title": "Principal AI Architect",
        "location": "Bengaluru, Karnataka, India",
        "linkedin_url": "https://www.linkedin.com/in/ananya-deshmukh-ai/",
        "email": "ananya.deshmukh@nvidia.com",
        "email_status": "verified",
        "phone": "+91 98765 43210",
        "phone_status": "verified",
        "confidence": 1.0,
    },
    {
        "name": "Rohan Sharma",
        "company": "Atlassian",
        "title": "Staff Frontend Engineer",
        "location": "Bengaluru, India",
        "linkedin_url": "https://www.linkedin.com/in/rohan-sharma-dev/",
        "email": "rohan.sharma@atlassian.com",
        "email_status": "found",
        "phone": None,
        "phone_status": "not_found",
        "confidence": 0.9,
    },
]


@pytest.mark.django_db
def test_import_people_mechanism():
    count = import_people(DATASET, source="authorized-fixture")
    assert count == 2
    assert EnrichmentPerson.objects.count() == 2

    ananya = EnrichmentPerson.objects.get(full_name="Ananya Deshmukh")
    assert ananya.email == "ananya.deshmukh@nvidia.com"
    assert ananya.email_status == "verified"
    assert ananya.phone == "+919876543210"  # normalized, not truncated
    assert ananya.phone_status == "verified"
    assert ananya.source == "authorized-fixture"


@pytest.mark.django_db
def test_import_people_rejects_dummy_contacts():
    rows = [
        {
            "name": "Fake Person",
            "company": "Acme",
            "email": "candidate@example.com",
            "phone": "9876543210",
        }
    ]
    import_people(rows)
    person = EnrichmentPerson.objects.get(full_name="Fake Person")
    assert person.email is None
    assert person.email_status == "not_found"
    assert person.phone is None
    assert person.phone_status == "not_found"


@pytest.mark.django_db
def test_native_provider_matches_by_linkedin_url():
    import_people(DATASET)
    provider = NativeEnrichmentProvider()
    match = provider.match_person({"profile_url": PERSON["profile_url"]})
    assert match["matched"] is True
    assert match["confidence"] == 1.0


@pytest.mark.django_db
def test_native_provider_matches_by_name_and_company():
    import_people(DATASET)
    provider = NativeEnrichmentProvider()
    match = provider.match_person({"name": "Ananya Deshmukh", "company": "NVIDIA"})
    assert match["matched"] is True
    assert match["confidence"] >= 0.4


@pytest.mark.django_db
def test_native_provider_no_match():
    import_people(DATASET)
    provider = NativeEnrichmentProvider()
    match = provider.match_person({"name": "Nobody Unknown", "company": "Nowhere"})
    assert match["matched"] is False
    assert match["confidence"] == 0.0


@pytest.mark.django_db
def test_native_email_and_phone_enrichment():
    import_people(DATASET)
    result = PersonMatchService.enrich(PERSON, scope="all", provider=NativeEnrichmentProvider())
    assert result["matched"] is True
    assert result["source"] == "talentvault"
    assert result["email"]["value"] == "ananya.deshmukh@nvidia.com"
    assert result["email"]["status"] == "verified"
    assert result["phone"]["value"] == "+919876543210"
    assert result["phone"]["status"] == "verified"


@pytest.mark.django_db
def test_native_phone_not_found_when_record_lacks_phone():
    import_people(DATASET)
    rohan = {"name": "Rohan Sharma", "company": "Atlassian"}
    result = PersonMatchService.enrich(rohan, scope="phone", provider=NativeEnrichmentProvider())
    assert result["matched"] is True
    assert result["phone"]["value"] is None
    assert result["phone"]["status"] == "not_found"


@pytest.mark.django_db
def test_native_end_to_end_profile_to_extension_result():
    # Seed the native TalentVault people database.
    import_people(DATASET, source="authorized-fixture")

    # The default provider is "native"; the extension hits this endpoint.
    client = APIClient()
    url = reverse("api_person_enrichment")

    response = client.post(url, PERSON, format="json", HTTP_ORIGIN=EXT_ORIGIN)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["matched"] is True
    assert data["source"] == "talentvault"
    assert data["match_confidence"] == 1.0
    assert data["email"]["value"] == "ananya.deshmukh@nvidia.com"
    assert data["email"]["status"] == "verified"
    assert data["phone"]["value"] == "+919876543210"
    assert data["phone"]["status"] == "verified"
