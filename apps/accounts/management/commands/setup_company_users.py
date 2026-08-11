from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

COMPANY_USERS = [
    {
        "first_name": "Snehal",
        "last_name": "Patil",
        "email": "snehal.2020technologies@gmail.com",
        "password": "TV_Snehal#2026!",
        "role": User.Role.RECRUITER,
    },
    {
        "first_name": "Chhaya",
        "last_name": "Joshi",
        "email": "chhayajoshi.2020technologies.in@gmail.com",
        "password": "TV_Chhaya#2026!",
        "role": User.Role.RECRUITER,
    },
    {
        "first_name": "Rahul",
        "last_name": "Nishad",
        "email": "rahul.2020technologies@gmail.com",
        "password": "TV_Rahul#2026!",
        "role": User.Role.RECRUITER,
    },
    {
        "first_name": "Anamika",
        "last_name": "Shukla",
        "email": "anamikashkla.2020technologies@gmail.com",
        "password": "TV_Anamika#2026!",
        "role": User.Role.RECRUITER,
    },
    {
        "first_name": "Deepak",
        "last_name": "Kumar",
        "email": "deepak.kumar@2020technologies.in",
        "password": "TV_Deepak#2026!",
        "role": User.Role.RECRUITER,
    },
    {
        "first_name": "Nikhil",
        "last_name": "Mittal",
        "email": "nikhil@2020technologies.in",
        "password": "TV_Nikhil#2026!",
        "role": User.Role.RECRUITER,
    },
    {
        "first_name": "Harshita",
        "last_name": "",
        "email": "harshita.2020technologies@gmail.com",
        "password": "TV_Harshita#2026!",
        "role": User.Role.RECRUITER,
    },
    {
        "first_name": "Deepanshu",
        "last_name": "Verma",
        "email": "deepanshu.verma@2020technologies.in",
        "password": "TV_Deepanshu#2026!",
        "role": User.Role.RECRUITER,
    },
    {
        "first_name": "Rajeev",
        "last_name": "Kumar",
        "email": "rajeevkumar9801456p@gmail.com",
        "password": "TV_Rajeev#2026!",
        "role": User.Role.RECRUITER,
    },
]

class Command(BaseCommand):
    help = "Idempotently setup or update the 9 company internal users for TalentVault workspace."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Company Users Setup..."))
        created_count = 0
        updated_count = 0

        for user_data in COMPANY_USERS:
            email = user_data["email"].strip().lower()
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": user_data["first_name"],
                    "last_name": user_data["last_name"],
                    "role": user_data["role"],
                    "is_active": True,
                    "recruiter_status": getattr(User, "RecruiterStatus", None) and User.RecruiterStatus.ACTIVE or "ACTIVE",
                }
            )

            # Update names and roles if changed
            user.first_name = user_data["first_name"]
            user.last_name = user_data["last_name"]
            user.role = User.Role.SUPER_ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            if hasattr(user, "recruiter_status"):
                user.recruiter_status = User.RecruiterStatus.ACTIVE
            
            # Set secure password using set_password
            user.set_password(user_data["password"])
            user.save()

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"[CREATED] {user.get_full_name()} ({user.email})"))
            else:
                updated_count += 1
                self.stdout.write(self.style.SUCCESS(f"[UPDATED] {user.get_full_name()} ({user.email})"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFinished Company Users Setup. Created: {created_count}, Updated: {updated_count}"
            )
        )
