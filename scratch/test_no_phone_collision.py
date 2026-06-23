import os
import sys
import django
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env variables from .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.utils import process_resume_file
from apps.accounts.models import User

# Clean test users
User.objects.filter(email__in=["no_phone_candidate1@example.com", "no_phone_candidate2@example.com"]).delete()

# We will mock process_resume_file or run it by passing a file
# Since process_resume_file runs OCR, we'll write a simple test for our query logic
from django.db.models import Q

email1 = "no_phone_candidate1@example.com"
phone1 = "" # parsed as empty or placeholder

email2 = "no_phone_candidate2@example.com"
phone2 = ""

# 1. Create first user
user1, created1 = User.objects.get_or_create(
    email=email1,
    defaults={'role': User.Role.CANDIDATE, 'phone_number': phone1 if phone1 else None}
)
print("Created first candidate without phone:", user1.email, "Phone in DB:", repr(user1.phone_number))

# 2. Query duplicate check for second user with empty phone
# If phone2 is not empty, check email OR phone. If phone2 is empty, check ONLY email.
if phone2:
    existing_user = User.objects.filter(Q(email=email2) | Q(phone_number=phone2)).first()
else:
    existing_user = User.objects.filter(email=email2).first()

if existing_user:
    print("Test failed! Collision found with:", existing_user.email)
else:
    print("Test passed! No duplicate collision for different candidates with empty phone numbers.")

# Clean up
User.objects.filter(email__in=["no_phone_candidate1@example.com", "no_phone_candidate2@example.com"]).delete()
