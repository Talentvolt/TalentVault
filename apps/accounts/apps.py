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

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'

    def ready(self):
        post_migrate.connect(create_default_recruiter, sender=self)
