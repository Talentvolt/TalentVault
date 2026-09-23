"""
End-to-end mapping regression for the SreeHarsha CV.

Flow exercised:
    Parseora response JSON (fixture)
    -> ParseoraService.map_response_to_talentvault   (CRM adapter)
    -> simulated persistence into CandidateProfile/Experience/Education/Skill
    -> fields read by the candidate detail UI

The fixture is produced by Parseora from
tests/regression_resumes/Naukri_SreeHarshaGR_22y_0m_.pdf.
"""

import json
import os

from django.test import SimpleTestCase

from services.parseora_service import ParseoraService

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sreeharsha_parseora.json")


def _persist_candidate_fields(mapped: dict) -> dict:
    """Mirrors the field assignments in apps.candidates.utils.process_resume_file
    so we can assert exactly what the candidate detail UI would display."""
    info = mapped.get("personal_info", {}) or {}
    return {
        "full_name": (info.get("name") or "").strip(),
        "summary": mapped.get("summary") or "",
        "location": (info.get("location") or "").strip(),
        "current_company": (info.get("current_company") or "").strip(),
        "current_designation": (info.get("current_designation") or "").strip(),
        "date_of_birth": mapped.get("date_of_birth") or info.get("date_of_birth") or "",
        "total_experience": info.get("total_experience"),
        "experiences": [
            {
                "company_name": (e.get("company") or "")[:100],
                "designation": (e.get("designation") or "")[:100],
                "start_date": e.get("start_date"),
                "end_date": e.get("end_date"),
                "description": e.get("description") or "",
            }
            for e in mapped.get("experience", [])
        ],
        "educations": [
            {
                "institution": (e.get("institution") or "")[:100],
                "degree": (e.get("degree") or "")[:100],
                "field_of_study": (e.get("field_of_study") or "")[:100],
                "score": str(e.get("score") or ""),
            }
            for e in mapped.get("education", [])
        ],
        "skills": list(mapped.get("skills", [])),
        "languages": list(mapped.get("languages", [])),
        "has_photo": bool(mapped.get("photo_bytes")),
    }


class SreeHarshaParseoraMappingTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(FIXTURE, encoding="utf-8") as f:
            cls.res = json.load(f)
        cls.mapped = ParseoraService.map_response_to_talentvault(cls.res)
        cls.persisted = _persist_candidate_fields(cls.mapped)

    # ---------------- name ---------------- #
    def test_name_maps_to_candidate_name(self):
        name = self.persisted["full_name"]
        self.assertIn("Sreeharsha", name)
        self.assertTrue(name.upper().endswith("R"), name)
        # The document tagline must never be the candidate name.
        self.assertNotIn("SALES AND MARKETING", name.upper())

    # ---------------- summary ---------------- #
    def test_summary_maps_only_from_profile_summary(self):
        summary = self.persisted["summary"]
        self.assertTrue(summary.startswith("Results-driven Sales & Marketing"))
        self.assertNotIn("@", summary)
        self.assertNotIn("97311", summary)

    # ---------------- experience ---------------- #
    def test_experience_records_map_correctly(self):
        exps = self.persisted["experiences"]
        self.assertEqual(len(exps), 4, exps)
        pairs = {(e["company_name"], e["designation"]) for e in exps}
        self.assertIn(("LINK LOCKS PVT LTD", "Regional Sales Manager – Karnataka"), pairs)
        self.assertIn(("MODI PIPES PVT LTD", "Head – Branch Sales & Marketing, Karnataka (State Head)"), pairs)
        self.assertIn(("LEON SHING DONGA ELECTRICAL PVT LTD", "Senior Executive – Business Development"), pairs)
        self.assertIn(("SRF LIMITED", "Territory In Charge – Karnataka"), pairs)

    def test_experience_has_no_education_or_contact_data(self):
        for e in self.persisted["experiences"]:
            blob = f"{e['company_name']} {e['designation']} {e['description']}"
            self.assertNotIn("@", blob)
            self.assertNotIn("University", e["company_name"])
            self.assertNotIn("P.U.C", blob)

    def test_company_not_fabricated_with_date_fragment(self):
        for e in self.persisted["experiences"]:
            self.assertNotRegex(
                e["company_name"],
                r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b',
            )

    # ---------------- education ---------------- #
    def test_education_records_map_correctly(self):
        edus = self.persisted["educations"]
        self.assertEqual(len(edus), 3, edus)
        degrees = " ".join(e["degree"] for e in edus).upper()
        self.assertIn("M.A", degrees)
        self.assertIn("B.A", degrees)
        self.assertIn("P.U.C", degrees)
        institutions = " ".join(e["institution"] for e in edus)
        self.assertIn("Mysore University", institutions)
        self.assertIn("Sahyadri College", institutions)
        self.assertIn("DVS PU College", institutions)

    def test_education_receives_no_contact_or_header_data(self):
        for e in self.persisted["educations"]:
            blob = f"{e['degree']} {e['institution']}"
            self.assertNotIn("@", blob)
            self.assertNotRegex(blob, r'\+?\d[\d\s\-]{7,}')
            self.assertNotIn("SALES AND MARKETING", blob.upper())

    # ---------------- skills / personal ---------------- #
    def test_skills_are_not_sentences(self):
        skills = self.persisted["skills"]
        joined = " ".join(skills).lower()
        self.assertIn("ms office", joined)
        self.assertIn("sales reporting", joined)
        for s in skills:
            self.assertNotIn("•", s)
            self.assertFalse(s.rstrip().endswith("."))

    def test_personal_details(self):
        self.assertIn("14 August 1983", str(self.persisted["date_of_birth"]))
        self.assertIn("Bangalore", self.persisted["location"])
        self.assertTrue(
            {"English", "Hindi", "Kannada", "Tamil", "Telugu"}.issubset(set(self.persisted["languages"])),
            self.persisted["languages"],
        )

    def test_photo_not_fabricated(self):
        # This CV has no genuine candidate photograph.
        self.assertFalse(self.persisted["has_photo"])


if __name__ == "__main__":
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
    django.setup()
    import unittest
    unittest.main()
