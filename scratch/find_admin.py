import os
import sys
import django

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User

admins = User.objects.filter(role=User.Role.SUPER_ADMIN)
print(f"Total Super Admins: {admins.count()}")
for a in admins:
    print(f"Email: {a.email} | Active: {a.is_active}")
