"""Mock enrichment provider for LOCAL testing only.

Contains deterministic test records so the enrichment pipeline can be exercised
end-to-end without any real network, scraping, CAPTCHA-bypass or external API.
Mock data lives exclusively in this backend provider/test layer — it is never
hardcoded in the extension or frontend.
"""
from services.enrichment.providers import EnrichmentProvider, FOUND, NOT_FOUND, VERIFIED, UNVERIFIED


def _norm(value):
    return " ".join((value or "").strip().lower().split())


class MockEnrichmentProvider(EnrichmentProvider):
    name = "mock"

    # A record matches when enough of its identity fields align. Weights:
    #   profile_url  -> 0.50 (strongest unique identifier)
    #   name         -> 0.30
    #   company      -> 0.15
    #   title        -> 0.15
    #   location     -> 0.05 (weak bonus)
    MATCH_THRESHOLD = 0.40

    RECORDS = [
        {
            "name": "Ananya Deshmukh",
            "company": "NVIDIA",
            "title": "Principal AI Architect",
            "location": "Bengaluru, Karnataka, India",
            "profile_url": "https://www.linkedin.com/in/ananya-deshmukh-ai/",
            "email": "ananya.deshmukh@nvidia.com",
            "email_status": VERIFIED,
            "phone": "+919876543210",
            "phone_status": FOUND,
        },
        {
            "name": "Rohan Sharma",
            "company": "Atlassian",
            "title": "Staff Frontend Engineer",
            "location": "Bengaluru, India",
            "profile_url": "https://www.linkedin.com/in/rohan-sharma-dev/",
            "email": "rohan.sharma@atlassian.com",
            "email_status": FOUND,
            "phone": None,
            "phone_status": NOT_FOUND,
        },
        {
            "name": "Priya Nair",
            "company": "Google",
            "title": "Data Scientist",
            "location": "Hyderabad, India",
            "profile_url": "https://www.linkedin.com/in/priya-nair-data/",
            "email": "priya.nair@gmail.com",
            "email_status": UNVERIFIED,
            "phone": "+918888888888",
            "phone_status": UNVERIFIED,
        },
        {
            "name": "Vikram Singh",
            "company": "Infosys",
            "title": "Test Engineer",
            "location": "Pune, India",
            "profile_url": "https://www.linkedin.com/in/vikram-singh-qa/",
            "email": None,
            "email_status": NOT_FOUND,
            "phone": None,
            "phone_status": NOT_FOUND,
        },
    ]

    def match_person(self, person):
        name = _norm(person.get("name"))
        company = _norm(person.get("company"))
        title = _norm(person.get("title"))
        location = _norm(person.get("location"))
        profile_url = _norm(person.get("profile_url"))

        best = None
        best_score = 0.0

        for record in self.RECORDS:
            score = 0.0
            if profile_url and _norm(record.get("profile_url")) == profile_url:
                score += 0.50
            if name and _norm(record.get("name")) == name:
                score += 0.30
            if company and _norm(record.get("company")) == company:
                score += 0.15
            if title and _norm(record.get("title")) == title:
                score += 0.15
            if location and _norm(record.get("location")) == location:
                score += 0.05

            if score > best_score:
                best = record
                best_score = score

        if best is None or best_score < self.MATCH_THRESHOLD:
            return {"matched": False, "confidence": 0.0, "record": None}

        return {"matched": True, "confidence": round(min(best_score, 1.0), 2), "record": best}

    def find_email(self, person, match):
        record = (match or {}).get("record")
        if not record:
            return {"value": None, "status": NOT_FOUND}
        value = record.get("email")
        if not value:
            return {"value": None, "status": NOT_FOUND}
        return {"value": value, "status": record.get("email_status") or FOUND}

    def find_phone(self, person, match):
        record = (match or {}).get("record")
        if not record:
            return {"value": None, "status": NOT_FOUND}
        value = record.get("phone")
        if not value:
            return {"value": None, "status": NOT_FOUND}
        return {"value": value, "status": record.get("phone_status") or FOUND}
