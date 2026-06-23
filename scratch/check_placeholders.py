import os
import sys
import django
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User
print("Users with '9876543210' phone number:", User.objects.filter(phone_number="9876543210").count())
print("Users with 'candidate@example.com' email:", User.objects.filter(email="candidate@example.com").count())
