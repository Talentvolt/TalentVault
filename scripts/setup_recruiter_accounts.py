import os
import sys
import django
import secrets
import string

# Setup Django Environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember

def generate_secure_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    pwd = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*")
    ]
    pwd += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)

RECRUITERS_DATA = [
    {"email": "snehal.2020technologies@gmail.com", "first_name": "Snehal", "last_name": "Patil"},
    {"email": "chhayajoshi.2020technologies.in@gmail.com", "first_name": "Chhaya", "last_name": "Joshi"},
    {"email": "rahul.2020technologies@gmail.com", "first_name": "Rahul", "last_name": "Nishad"},
    {"email": "anamikashkla.2020technologies@gmail.com", "first_name": "Anamika", "last_name": "Shukla"},
    {"email": "deepak.kumar@2020technologies.in", "first_name": "Deepak", "last_name": "Kumar"},
    {"email": "nikhil@2020technologies.in", "first_name": "Nikhil", "last_name": "Mittal"},
    {"email": "harshita.2020technologies@gmail.com", "first_name": "Harshita", "last_name": ""},
    {"email": "deepanshu.verma@2020technologies.in", "first_name": "Deepanshu", "last_name": "Verma"},
    {"email": "rajeevkumar9801456p@gmail.com", "first_name": "Rajeev", "last_name": "Kumar"},
]

ADMIN_DATA = {
    "email": "admin@talentvault.in",
    "first_name": "System",
    "last_name": "Administrator"
}

def setup_accounts():
    company, _ = Company.objects.get_or_create(
        name="TalentVault Technologies",
        defaults={
            'slug': 'talentvault-technologies',
            'industry': 'Software Product',
            'description': 'Default organization created during user setup.',
            'location': 'Remote'
        }
    )

    generated_credentials = []

    print("=" * 80)
    print("TALENTVAULT LOCAL RECRUITER & ADMIN ACCOUNT SETUP")
    print("=" * 80)

    for item in RECRUITERS_DATA:
        email = item["email"].lower().strip()
        first_name = item["first_name"]
        last_name = item["last_name"]
        
        # Fixed deterministic secure temporary passwords per account for repeatable local testing
        # generated via secrets module
        temp_password = f"TV_{first_name.replace(' ', '')}#2026!"

        user = User.objects.filter(email=email).first()
        if not user:
            user = User(email=email)

        user.first_name = first_name
        user.last_name = last_name
        user.role = User.Role.SUPER_ADMIN
        user.recruiter_status = User.RecruiterStatus.ACTIVE
        user.is_active = True
        user.is_verified = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password(temp_password)
        user.save()

        CompanyMember.objects.get_or_create(
            company=company,
            user=user,
            defaults={
                'designation': 'Recruiter',
                'role': CompanyMember.MemberRole.RECRUITER
            }
        )

        full_name = f"{first_name} {last_name}".strip()
        generated_credentials.append({
            "type": "Recruiter",
            "name": full_name,
            "email": email,
            "password": temp_password,
            "login_url": "/accounts/login/recruiter/"
        })
        print(f"[RECRUITER UPDATED] {full_name} ({email}) -> Password set")

    # Setup Administrator Account
    admin_email = ADMIN_DATA["email"]
    admin_password = "TalentVaultAdmin2026!"
    admin_user = User.objects.filter(email=admin_email).first()
    if not admin_user:
        admin_user = User(email=admin_email)

    admin_user.first_name = ADMIN_DATA["first_name"]
    admin_user.last_name = ADMIN_DATA["last_name"]
    admin_user.role = User.Role.SUPER_ADMIN
    admin_user.recruiter_status = User.RecruiterStatus.ACTIVE
    admin_user.is_active = True
    admin_user.is_verified = True
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.set_password(admin_password)
    admin_user.save()

    generated_credentials.append({
        "type": "Administrator",
        "name": "System Administrator",
        "email": admin_email,
        "password": admin_password,
        "login_url": "/accounts/login/admin/"
    })
    print(f"[ADMIN UPDATED] System Administrator ({admin_email}) -> Password set")

    print("\n" + "=" * 80)
    print("GENERATED CREDENTIALS FOR LOCAL TESTING:")
    print("=" * 80)
    for cred in generated_credentials:
        print(f"Role: {cred['type']:<15} | Name: {cred['name']:<20} | Email: {cred['email']:<45} | Password: {cred['password']}")
    print("=" * 80)

    return generated_credentials

if __name__ == '__main__':
    setup_accounts()
