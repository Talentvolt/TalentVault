import os
import sys
import django
import time

# Setup path and environment
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Load env variables
try:
    import dotenv
    dotenv.load_dotenv(os.path.join(project_root, '.env'))
except ImportError:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from django.core.cache import cache
from django.contrib.auth import get_user_model
from services.parser.pipeline import ResumeParsingPipeline

def main():
    # 1. Clear Django cache to guarantee no cached results are used
    print("Clearing Django cache...")
    cache.clear()
    
    # 2. Get or create a test user
    User = get_user_model()
    test_user, _ = User.objects.get_or_create(
        email="real_test@example.com",
        defaults={"first_name": "Test", "last_name": "User"}
    )
    
    # 3. Path to real editable PDF
    resume_path = "scratch/rajeev_kumar_resume.pdf"
    print(f"Running one real resume: {resume_path} (size: {os.path.getsize(resume_path)} bytes)")
    
    # 4. Initialize and run production pipeline (NO mocks, NO cache)
    with open(resume_path, "rb") as f:
        pipeline = ResumeParsingPipeline(
            file_obj=f,
            filename=os.path.basename(resume_path),
            user=test_user
        )
        profile, status = pipeline.run()
        
    print(f"\nExecution Finished. Status: {status}")
    if profile:
        print(f"Created profile ID: {profile.id}, Name: {profile.full_name}")
    else:
        print("Profile creation failed!")

if __name__ == "__main__":
    main()
