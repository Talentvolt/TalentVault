import os
import sys
import django
from dotenv import load_dotenv

# Load env
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.applications.models import Application

apps = Application.objects.all()
print(f"Total Applications: {apps.count()}")
for app in apps:
    cand_name = (app.candidate.full_name or "").encode('ascii', errors='ignore').decode('ascii')
    job_title = (app.job.title or "").encode('ascii', errors='ignore').decode('ascii')
    print(f"App ID: {app.id} | Candidate: {cand_name} ({app.candidate.user.email}) | Job: {job_title} | Match Score: {app.match_score}%")
