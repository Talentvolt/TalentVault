import os
import django
import io
import sys

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.candidates.utils import process_resume_file
from apps.candidates.models import CandidateProfile
from apps.accounts.models import User
from PIL import Image, ImageDraw

def main():
    print("=" * 60)
    print("Verifying Real PNG Screenshot Resume Upload")
    print("=" * 60)

    # 1. Create media/uploads if it doesn't exist and generate a high-contrast screenshot resume image
    os.makedirs("media/uploads", exist_ok=True)
    screenshot_path = "media/uploads/screenshot_resume.png"
    
    # Check if a custom file path is passed as command-line argument
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        print(f"Using provided custom file: {file_path}")
        if not os.path.exists(file_path):
            print(f"Error: Provided file '{file_path}' does not exist.")
            return
    else:
        file_path = screenshot_path
        print(f"Generating a high-contrast PNG screenshot resume at '{file_path}'...")
        
        img = Image.new('RGB', (800, 600), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        
        text_content = (
            "Ankit Kumar\n"
            "ankit.kumar@example.com\n"
            "+91 9953699195\n"
            "Location: Delhi\n"
            "Skills: Python, Django, Docker, PostgreSQL\n"
            "\n"
            "Experience\n"
            "Software Engineer | Tech Corp | Worked on python web applications.\n"
            "\n"
            "Education\n"
            "Bachelor of Technology | Delhi Tech Institute\n"
        )
        
        y = 20
        for line in text_content.split('\n'):
            d.text((20, y), line, fill=(0, 0, 0))
            y += 30
            
        img.save(file_path, format='PNG')
        
    filename = os.path.basename(file_path)
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
    img_bytes_io = io.BytesIO(file_bytes)
    
    # Clean up any existing user/profile to avoid duplicate skip
    test_email = "ankit.kumar@example.com"
    User.objects.filter(email=test_email).delete()
    
    # 2. Run the process_resume_file logic
    print("Uploading and processing PNG resume through real OCR engine...")
    profile, status = process_resume_file(img_bytes_io, filename, overwrite=True)
    
    print("-" * 60)
    print(f"Status returned: {status}")
    
    if status == "SUCCESS" and profile:
        print("Candidate created successfully!")
        print(f"Candidate Name:       {profile.full_name}")
        print(f"Candidate Email:      {profile.user.email}")
        print(f"Candidate Phone:      {profile.user.phone_number}")
        print(f"OCR Engine Used:      {profile.ocr_engine}")
        print(f"OCR Confidence:       {profile.ocr_confidence}%")
        print(f"Resume Type:          {profile.resume_type}")
        print(f"Total Experience:     {profile.total_experience} years")
        print(f"Location:             {profile.location}")
        
        # Skills
        skills = [s.skill_name for s in profile.skills.all()]
        print(f"Skills Extracted:     {skills}")
        
        # Education
        education = [f"{e.degree} from {e.institution}" for e in profile.educations.all()]
        print(f"Education:            {education}")
        
        # Experience
        experience = [f"{exp.designation} at {exp.company_name}" for exp in profile.experiences.all()]
        print(f"Experience:           {experience}")
        
        # Clean up
        profile.user.delete()
        print("Test Candidate deleted successfully.")
    else:
        print("Failed to create candidate.")
    print("=" * 60)

if __name__ == "__main__":
    main()
