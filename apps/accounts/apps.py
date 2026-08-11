import logging
from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)

COMPANY_RECRUITERS = [
    {"email": "snehal.2020technologies@gmail.com", "first_name": "Snehal", "last_name": "Patil", "role": "SUPER_ADMIN"},
    {"email": "chhayajoshi.2020technologies.in@gmail.com", "first_name": "Chhaya", "last_name": "Joshi", "role": "SUPER_ADMIN"},
    {"email": "rahul.2020technologies@gmail.com", "first_name": "Rahul", "last_name": "Nishad", "role": "SUPER_ADMIN"},
    {"email": "anamikashkla.2020technologies@gmail.com", "first_name": "Anamika", "last_name": "", "role": "SUPER_ADMIN"},
    {"email": "deepak.kumar@2020technologies.in", "first_name": "Deepak", "last_name": "Kumar", "role": "SUPER_ADMIN"},
    {"email": "nikhil@2020technologies.in", "first_name": "Nikhil", "last_name": "Mittal", "role": "SUPER_ADMIN"},
    {"email": "harshita.2020technologies@gmail.com", "first_name": "Harshita", "last_name": "", "role": "SUPER_ADMIN"},
    {"email": "deepanshu.verma@2020technologies.in", "first_name": "Deepanshu", "last_name": "Verma", "role": "SUPER_ADMIN"},
    {"email": "rajeevkumar9801456p@gmail.com", "first_name": "Rajeev", "last_name": "Kumar", "role": "SUPER_ADMIN"},
]

ADMIN_ACCOUNTS = [
    {"email": "admin@talentvault.in", "first_name": "System", "last_name": "Administrator", "role": "SUPER_ADMIN"},
]

def create_default_recruiter(sender, **kwargs):
    from django.db import connection
    try:
        tables = connection.introspection.table_names()
        if 'accounts_user' in tables:
            from apps.accounts.models import User
            from apps.companies.models import Company, CompanyMember
            
            company = None
            if 'companies_company' in tables:
                company, _ = Company.objects.get_or_create(
                    name="TalentVault Technologies",
                    defaults={
                        'slug': 'talentvault-technologies',
                        'industry': 'Software Product',
                        'description': 'Default organization created during database initialization.',
                        'location': 'Remote'
                    }
                )
            
            for config in COMPANY_RECRUITERS:
                email = config['email'].lower().strip()
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "is_staff": True,
                        "is_superuser": True,
                        "role": User.Role.SUPER_ADMIN,
                        "first_name": config['first_name'],
                        "last_name": config['last_name'],
                        "is_active": True,
                        "is_verified": True,
                        "recruiter_status": User.RecruiterStatus.ACTIVE,
                    }
                )
                if created:
                    user.set_password("TalentVault2026!")
                    user.save()
                    logger.info(f"Created company administrator account: {email}")
                else:
                    updated = False
                    if not user.first_name and config['first_name']:
                        user.first_name = config['first_name']
                        updated = True
                    if not user.last_name and config['last_name']:
                        user.last_name = config['last_name']
                        updated = True
                    if user.role != User.Role.SUPER_ADMIN or not user.is_staff or not user.is_superuser:
                        user.role = User.Role.SUPER_ADMIN
                        user.is_staff = True
                        user.is_superuser = True
                        updated = True
                    if user.recruiter_status != User.RecruiterStatus.ACTIVE:
                        user.recruiter_status = User.RecruiterStatus.ACTIVE
                        updated = True
                    if updated:
                        user.save()

                if company and 'companies_companymember' in tables:
                    CompanyMember.objects.get_or_create(
                        company=company,
                        user=user,
                        defaults={
                            'designation': 'Recruiter',
                            'role': CompanyMember.MemberRole.RECRUITER
                        }
                    )

            for config in ADMIN_ACCOUNTS:
                email = config['email'].lower().strip()
                admin_user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "is_staff": True,
                        "is_superuser": True,
                        "role": User.Role.SUPER_ADMIN,
                        "first_name": config['first_name'],
                        "last_name": config['last_name'],
                        "is_active": True,
                        "is_verified": True,
                        "recruiter_status": User.RecruiterStatus.ACTIVE,
                    }
                )
                if created:
                    admin_user.set_password("TalentVaultAdmin2026!")
                    admin_user.save()
                    logger.info(f"Created admin account: {email}")
    except Exception as err:
        logger.error(f"Error in create_default_recruiter: {err}")

def setup_google_social_app(sender, **kwargs):
    from django.db import connection
    import os
    try:
        tables = connection.introspection.table_names()
        if 'django_site' in tables and 'socialaccount_socialapp' in tables:
            from django.contrib.sites.models import Site
            from allauth.socialaccount.models import SocialApp
            from django.conf import settings

            site_id = getattr(settings, 'SITE_ID', 1)
            site, _ = Site.objects.get_or_create(
                id=site_id,
                defaults={'domain': 'talent-vault.in', 'name': 'TalentVault'}
            )

            client_id = os.environ.get('GOOGLE_CLIENT_ID', '') or getattr(settings, 'GOOGLE_CLIENT_ID', '')
            if client_id.startswith("GOOGLE_CLIENT_ID="):
                client_id = client_id.replace("GOOGLE_CLIENT_ID=", "", 1)

            client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '') or getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
            if client_secret.startswith("GOOGLE_CLIENT_SECRET="):
                client_secret = client_secret.replace("GOOGLE_CLIENT_SECRET=", "", 1)

            effective_client_id = client_id if client_id else "placeholder-google-client-id"
            effective_client_secret = client_secret if client_secret else "placeholder-google-client-secret"

            app, _ = SocialApp.objects.get_or_create(
                provider='google',
                defaults={
                    'name': 'Google',
                    'client_id': effective_client_id,
                    'secret': effective_client_secret,
                }
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
    except Exception as e:
        logger.error(f"Error in setup_google_social_app: {e}")

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'

    def ready(self):
        post_migrate.connect(create_default_recruiter, sender=self)
        post_migrate.connect(setup_google_social_app)
        
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
            logger.error(f"Error patching GoogleProvider: {err}")


