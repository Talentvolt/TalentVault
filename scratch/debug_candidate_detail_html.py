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
from django.contrib.auth import get_user_model
from apps.candidates.models import CandidateProfile
from apps.core.views import CandidateDetailView

# Fetch a candidate who has a resume
candidate = CandidateProfile.objects.exclude(resume=None).exclude(resume='').first()
if not candidate:
    print("No candidate with resume found in database!")
    # Fallback to any candidate
    candidate = CandidateProfile.objects.all().first()

if not candidate:
    print("No candidate found in database!")
    sys.exit(1)

print(f"Testing Candidate: {candidate.full_name} ({candidate.id}) | Has Resume: {bool(candidate.resume)}")
if candidate.resume:
    print(f"Resume Name: {candidate.resume.name}")

# Setup mock request
factory = RequestFactory()
request = factory.get(f'/candidates/{candidate.id}/')

User = get_user_model()
mock_user = User(email="recruiter@example.com")
request.user = mock_user

view = CandidateDetailView()
view.request = request
view.kwargs = {'pk': candidate.id}
view.object = candidate

try:
    context = view.get_context_data()
    print("SUCCESS: get_context_data ran without exceptions!")
except Exception as e:
    import traceback
    print("ERROR in get_context_data:")
    traceback.print_exc()
