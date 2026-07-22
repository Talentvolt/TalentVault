from django.apps import AppConfig
from django.db.models.signals import post_migrate

def create_default_recruiter(sender, **kwargs):
    from django.db import connection
    try:
        tables = connection.introspection.table_names()
        if 'accounts_user' in tables:
            from apps.accounts.models import User
            from apps.companies.models import Company, CompanyMember
            
            user, created = User.objects.get_or_create(
                email="growfluencestudio@gmail.com",
                defaults={
                    "is_staff": True,
                    "is_superuser": True,
                    "role": User.Role.RECRUITER,
                    "first_name": "TalentVault",
                    "last_name": "Recruiter",
                    "is_active": True,
                    "is_verified": True,
                }
            )
            if created:
                user.set_password("TalentVault2026!")
                user.save()
                print("Default recruiter account growfluencestudio@gmail.com created successfully with password TalentVault2026!")
            
            # Ensure default company association exists for dashboard integrity
            if 'companies_company' in tables and 'companies_companymember' in tables:
                company, _ = Company.objects.get_or_create(
                    name="TalentVault Technologies",
                    defaults={
                        'slug': 'talentvault-technologies',
                        'industry': 'Software Product',
                        'description': 'Default organization created during database initialization.',
                        'location': 'Remote'
                    }
                )
                CompanyMember.objects.get_or_create(
                    company=company,
                    user=user,
                    defaults={
                        'designation': 'Recruiter',
                        'role': CompanyMember.MemberRole.ADMIN
                    }
                )
    except Exception as err:
        import traceback
        print(f"Error in create_default_recruiter: {err}")
        traceback.print_exc()

def setup_google_social_app(sender, **kwargs):
    from django.db import connection
    import os
    try:
        tables = connection.introspection.table_names()
        if 'django_site' in tables and 'socialaccount_socialapp' in tables:
            from django.contrib.sites.models import Site
            from allauth.socialaccount.models import SocialApp
            from django.conf import settings

            site, _ = Site.objects.get_or_create(
                id=settings.SITE_ID,
                defaults={'domain': 'talent-vault.in', 'name': 'TalentVault'}
            )
            if site.domain != 'talent-vault.in':
                site.domain = 'talent-vault.in'
                site.name = 'TalentVault'
                site.save()

            client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '') or os.environ.get('GOOGLE_CLIENT_ID', '')
            client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '') or os.environ.get('GOOGLE_CLIENT_SECRET', '')

            if client_id:
                app, _ = SocialApp.objects.get_or_create(
                    provider='google',
                    defaults={
                        'name': 'Google OAuth',
                        'client_id': client_id,
                        'secret': client_secret,
                    }
                )
                if app.client_id != client_id or app.secret != client_secret:
                    app.client_id = client_id
                    app.secret = client_secret
                    app.save()
                if site not in app.sites.all():
                    app.sites.add(site)
    except Exception as e:
        import traceback
        print(f"Error in setup_google_social_app: {e}")
        traceback.print_exc()

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'

    def ready(self):
        post_migrate.connect(create_default_recruiter, sender=self)
        post_migrate.connect(setup_google_social_app, sender=self)
        
        # Enforce prompt=select_account, access_type=offline, include_granted_scopes=true on GoogleProvider
        try:
            from allauth.socialaccount.providers.google.provider import GoogleProvider
            _orig_get_auth_params = GoogleProvider.get_auth_params_from_request
            
            def custom_get_auth_params_from_request(self, request, action):
                ret = _orig_get_auth_params(self, request, action)
                ret['prompt'] = 'select_account'
                ret['access_type'] = 'offline'
                ret['include_granted_scopes'] = 'true'
                return ret

            GoogleProvider.get_auth_params_from_request = custom_get_auth_params_from_request
        except Exception as err:
            print(f"Error patching GoogleProvider: {err}")


