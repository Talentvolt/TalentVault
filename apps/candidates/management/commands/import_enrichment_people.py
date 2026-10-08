"""
Django Management Command: python manage.py import_enrichment_people <file>

Developer-only import of authorized contact datasets into the TalentVault
native People/Email/Phone database (``EnrichmentPerson``).

Supports JSON (a list of person objects) and CSV. Example JSON row:

    {
        "name": "Ananya Deshmukh",
        "company": "NVIDIA",
        "title": "Principal AI Architect",
        "location": "Bengaluru, Karnataka, India",
        "linkedin_url": "https://www.linkedin.com/in/ananya-deshmukh-ai/",
        "email": "ananya.deshmukh@nvidia.com",
        "email_status": "verified",
        "phone": "+919876543210",
        "phone_status": "verified",
        "confidence": 1.0
    }

Guard: refuses to run outside DEBUG mode unless ``--force`` is passed.
"""
import csv
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from services.enrichment.normalization import validated_email, validated_phone

VALID_CONTACT_STATUSES = ("found", "verified", "unverified", "not_found")


def _coerce_status(value, default):
    value = (value or default).strip().lower()
    return value if value in VALID_CONTACT_STATUSES else default


def _as_float(value, default=1.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def import_people(rows, source="manual", clear=False):
    """Import/upsert authorized people records into the EnrichmentPerson table.

    Returns the number of records imported. This function is also used directly
    by the developer seed tests.
    """
    from apps.candidates.models import EnrichmentPerson

    if clear:
        EnrichmentPerson.objects.all().delete()

    imported = 0
    for row in rows:
        if not isinstance(row, dict):
            continue

        name = (row.get("name") or row.get("full_name") or "").strip()
        if not name:
            continue
        company = (row.get("company") or "").strip()

        email = validated_email(row.get("email"))
        phone = validated_phone(row.get("phone"))

        linkedin_url = (row.get("linkedin_url") or row.get("profile_url") or "").strip() or None

        existing = EnrichmentPerson.objects.filter(
            full_name__iexact=name, company__iexact=company
        ).first()

        defaults = {
            "title": (row.get("title") or row.get("designation") or "").strip(),
            "location": (row.get("location") or "").strip(),
            "linkedin_url": linkedin_url,
            "email": email or None,
            "email_status": _coerce_status(row.get("email_status"), "verified" if email else "not_found"),
            "phone": phone or None,
            "phone_status": _coerce_status(row.get("phone_status"), "verified" if phone else "not_found"),
            "source": (row.get("source") or source).strip(),
            "confidence": _as_float(row.get("confidence"), 1.0),
        }

        if existing:
            for field, value in defaults.items():
                setattr(existing, field, value)
            existing.save()
        else:
            EnrichmentPerson.objects.create(full_name=name, company=company, **defaults)
        imported += 1

    return imported


class Command(BaseCommand):
    help = (
        "Import authorized contact datasets into the TalentVault People/Email/Phone "
        "database (developer-only)."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to a .json (list) or .csv dataset file.")
        parser.add_argument(
            "--source",
            default="manual",
            help="Provenance label applied to imported records (default: manual).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing people records before importing.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow the command to run outside DEBUG mode.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options.get("force"):
            raise CommandError(
                "This command is developer-only. Run with DEBUG=True or pass --force."
            )

        path = options["path"]
        if not os.path.exists(path):
            raise CommandError(f"File not found: {path}")

        rows = self._load_rows(path)
        if not isinstance(rows, list):
            raise CommandError("Dataset must be a list of person objects.")

        imported = import_people(
            rows,
            source=options.get("source", "manual"),
            clear=bool(options.get("clear")),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"[+] Imported {imported} people into the TalentVault People/Email/Phone database."
            )
        )

    def _load_rows(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        if ext == ".csv":
            with open(path, newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))
        raise CommandError("Unsupported file format. Use .json or .csv.")
