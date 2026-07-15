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
from apps.candidates.models import CandidateProfile, Experience, Education, CandidateSkill
from apps.candidates.utils import process_resume_file

def main():
    print("Clearing Django cache...")
    cache.clear()
    
    User = get_user_model()
    test_user, _ = User.objects.get_or_create(
        email="real_test@example.com",
        defaults={"first_name": "Test", "last_name": "User"}
    )
    
    resume_path = "scratch/prashant_resume.docx"
    print(f"Running restored parser on: {resume_path} (size: {os.path.getsize(resume_path)} bytes)")
    
    # Measure total parsing time
    t_start = time.time()
    profile, status = process_resume_file(
        file_obj=open(resume_path, "rb"),
        filename=os.path.basename(resume_path),
        overwrite=True,
        user=test_user
    )
    t_total = time.time() - t_start
    
    print(f"\nExecution Finished. Status: {status}")
    print(f"Total parsing time: {t_total:.2f}s")
    
    if profile:
        print("\n--- EXTRACTED CANDIDATE DATA ---")
        print(f"Name: {profile.full_name}")
        
        print("\n--- EXPERIENCE ---")
        experiences = profile.experiences.all()
        companies = []
        for exp in experiences:
            print(f"- Company: {exp.company_name} | Role: {exp.designation} | Dates: {exp.start_date} to {exp.end_date}")
            if exp.company_name:
                companies.append(exp.company_name)
                
        print("\n--- COMPANIES LIST ---")
        print(f"Companies: {companies}")
        
        print("\n--- EDUCATION ---")
        educations = profile.educations.all()
        for edu in educations:
            print(f"- Institution: {edu.institution} | Degree: {edu.degree} | Field: {edu.field_of_study} | Dates: {edu.start_date} to {edu.end_date}")
            
        print("\n--- SKILLS ---")
        skills = [sk.skill_name for sk in profile.skills.all()]
        print(f"Skills: {skills}")
    else:
        print("Profile creation failed!")

if __name__ == "__main__":
    main()
