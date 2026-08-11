import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User

def check():
    print("Searching for growfluencestudio or default recruiter accounts in DB:")
    users = User.objects.filter(email__icontains='growfluence')
    print(f"Found {users.count()} users matching 'growfluence'")
    for u in users:
        print(f"ID: {u.id} | Email: {u.email} | First: '{u.first_name}' | Last: '{u.last_name}' | Role: {u.role}")

    print("\nAll RECRUITER and SUPER_ADMIN users in DB:")
    for u in User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.SUPER_ADMIN, User.Role.COMPANY_ADMIN]):
        print(f"ID: {u.id} | Email: {u.email} | First: '{u.first_name}' | Last: '{u.last_name}' | Role: {u.role}")

if __name__ == '__main__':
    check()
