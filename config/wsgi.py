import os
import django
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

# Programmatically run collectstatic and migrate on startup to ensure the production environment is always updated
from django.core.management import call_command
try:
    call_command('collectstatic', '--noinput')
except Exception as e:
    print(f"Error running collectstatic on WSGI startup: {e}")

try:
    call_command('migrate', '--noinput')
except Exception as e:
    print(f"Error running migrate on WSGI startup: {e}")

application = get_wsgi_application()
