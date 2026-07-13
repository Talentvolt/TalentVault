import os
import sys
import django
from dotenv import load_dotenv

# Load env
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.core.views import RoleRedirectView

factory = RequestFactory()
request = factory.get('/')
request.user = AnonymousUser()

view = RoleRedirectView.as_view()
try:
    response = view(request)
    print("Response Status:", response.status_code)
except Exception as e:
    import traceback
    traceback.print_exc()
