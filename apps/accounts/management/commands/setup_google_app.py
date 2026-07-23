import os
from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from django.conf import settings


class Command(BaseCommand):
    help = (
        "Automatically verify and configure django.contrib.sites (Site id=1) "
        "and Google SocialApp for allauth OAuth login."
    )

    def handle(self, *args, **options):
        site_id = getattr(settings, "SITE_ID", 1)
        site, created_site = Site.objects.get_or_create(
            id=site_id,
            defaults={"domain": "talent-vault.in", "name": "TalentVault"},
        )
        if created_site:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created Site ID {site.id} ('{site.domain}')"
                )
            )
        else:
            self.stdout.write(f"Site ID {site.id} exists ('{site.domain}')")

        # Handle GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET with defensive cleaning
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "") or getattr(
            settings, "GOOGLE_CLIENT_ID", ""
        )
        if client_id.startswith("GOOGLE_CLIENT_ID="):
            client_id = client_id.replace("GOOGLE_CLIENT_ID=", "", 1)

        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "") or getattr(
            settings, "GOOGLE_CLIENT_SECRET", ""
        )
        if client_secret.startswith("GOOGLE_CLIENT_SECRET="):
            client_secret = client_secret.replace("GOOGLE_CLIENT_SECRET=", "", 1)

        effective_client_id = (
            client_id if client_id else "placeholder-google-client-id"
        )
        effective_client_secret = (
            client_secret if client_secret else "placeholder-google-client-secret"
        )

        app, created_app = SocialApp.objects.get_or_create(
            provider="google",
            defaults={
                "name": "Google",
                "client_id": effective_client_id,
                "secret": effective_client_secret,
            },
        )

        updated = False
        if client_id and app.client_id != client_id:
            app.client_id = client_id
            updated = True
        if client_secret and app.secret != client_secret:
            app.secret = client_secret
            updated = True

        if updated:
            app.save()

        if site not in app.sites.all():
            app.sites.add(site)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Attached Google SocialApp (ID {app.id}) to Site ID {site.id}"
                )
            )

        if created_app:
            self.stdout.write(
                self.style.SUCCESS(f"Created Google SocialApp (ID {app.id})")
            )
        elif updated:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated Google SocialApp (ID {app.id}) with credentials from environment"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Google SocialApp (ID {app.id}) verified and linked to Site ID {site.id}"
                )
            )
