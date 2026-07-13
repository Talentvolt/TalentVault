import os
import sys
import django

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User

users = User.objects.all()[:10]
print(f"Total Users: {User.objects.count()}")
for u in users:
    print(f"Email: {u.email} | Role: {u.role} | Active: {u.is_active} | Verified: {u.is_verified}")
