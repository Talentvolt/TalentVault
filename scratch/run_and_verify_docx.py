import os
import sys
import django
import json
import time

# Setup path and environment
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
sys.stdout.reconfigure(encoding='utf-8')

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
from apps.candidates.models import CandidateProfile, Experience, Education, Project, Certification, CandidateSkill
from apps.candidates.utils import process_resume_file, copy_storage_file
from services.resume_intelligence import ResumeIntelligenceService

# Hook/Monkeypatch to capture raw OpenAI JSON response
from apps.candidates.utils import OpenAIResumeParser

orig_parse = OpenAIResumeParser.parse
raw_openai_json = [None]

def custom_parse(text):
    from openai import OpenAI
    from django.conf import settings
    from apps.candidates.utils import FastResumeSchema
    
    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
    model_name = getattr(settings, "OPENAI_MODEL_NAME", "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)
    
    system_content = (
        "You are a professional resume parsing assistant.\n"
        "Your critical objective is to extract 100% of the resume content without any summarization, omission, or simplification.\n"
        "- Extract EVERY work experience, education item, project, skill, and certification listed, preserving their original order exactly.\n"
        "- For work experience and projects descriptions (responsibilities): Do NOT merge separate bullet points, sentences, or responsibilities into one long paragraph.\n"
        "- Do NOT summarize or condense responsibilities. Convert each responsibility or action item into its own separate line starting with a bullet point character '• '.\n"
        "- If the resume already has bullets, keep them as separate lines. Each bullet item must be preserved with its exact wording.\n"
        "- Never combine multiple distinct bullet points or achievements into a single sentence or line."
    )
    
    completion = client.beta.chat.completions.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": text}
        ],
        response_format=FastResumeSchema
    )
    
    raw_data = completion.choices[0].message.parsed.model_dump()
    raw_openai_json[0] = raw_data
    
    # Run conversion to standard format
    from apps.candidates.utils import convert_llm_data_to_standard_format
    return convert_llm_data_to_standard_format(raw_data)

OpenAIResumeParser.parse = custom_parse

def main():
    cache.clear()
    
    User = get_user_model()
    test_user, _ = User.objects.get_or_create(
        email="real_test@example.com",
        defaults={"first_name": "Prashant", "last_name": "Singh", "role": "CANDIDATE"}
    )
    
    resume_path = "scratch/prashant_resume.docx"
    with open(resume_path, "rb") as f:
        file_bytes = f.read()
        
    print("==================================================")
    print("   1. RAW EXTRACTED TEXT FROM DOCX RESUME")
    print("==================================================")
    ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, os.path.basename(resume_path))
    raw_text = ocr_result["text"]
    print(raw_text)
    print("==================================================\n")
    
    # Delete existing profile for test_user if exists to do a clean overwrite run
    CandidateProfile.objects.filter(user=test_user).delete()
    
    # Run the process_resume_file pipeline
    profile, status = process_resume_file(
        file_obj=open(resume_path, "rb"),
        filename=os.path.basename(resume_path),
        overwrite=True,
        user=test_user
    )
    
    print("==================================================")
    print("   2. RAW OPENAI JSON RESPONSE (BEFORE VALIDATION)")
    print("==================================================")
    print(json.dumps(raw_openai_json[0], indent=2))
    print("==================================================\n")
    
    print("==================================================")
    print("   3. FINAL VALIDATED JSON (AFTER CONVERSION)")
    print("==================================================")
    print(json.dumps(profile.parsed_json, indent=2))
    print("==================================================\n")
    
    print("==================================================")
    print("   4. DATABASE VALUES WRITTEN TO DATABASE")
    print("==================================================")
    print(f"Profile: ID={profile.id}, Name={profile.full_name}, Email={profile.user.email}, Phone={profile.user.phone_number or profile.user.first_name}")
    print(f"Summary: {profile.summary}")
    print("\nExperiences Saved:")
    for exp in profile.experiences.all():
        print(f"  - Company: {exp.company_name} | Role: {exp.designation} | Dates: {exp.start_date} to {exp.end_date}")
        print(f"    Description: {exp.description}")
    print("\nEducations Saved:")
    for edu in profile.educations.all():
        print(f"  - Institution: {edu.institution} | Degree: {edu.degree} | Field: {edu.field_of_study} | Dates: {edu.start_date} to {edu.end_date}")
    print("\nProjects Saved:")
    for proj in profile.projects.all():
        print(f"  - Title: {proj.title} | Link: {proj.link}")
        print(f"    Description: {proj.description}")
    print("\nCertifications Saved:")
    for cert in profile.certifications.all():
        print(f"  - Name: {cert.name} | Org: {cert.issuing_organization}")
    print("\nSkills Saved:")
    print(f"  Skills: {[s.skill_name for s in profile.skills.all()]}")
    print("==================================================\n")
    
    print("==================================================")
    print("   5. CANDIDATE DETAIL VIEW WRAPPER VALUES")
    print("==================================================")
    from apps.core.views import CandidateProfileWrapper, MockQuerySet
    
    version_data = profile.parsed_json
    
    display_experiences = []
    for exp in version_data.get('experience', []):
        display_experiences.append({
            'company_name': exp.get('company') or exp.get('company_name') or '',
            'designation': exp.get('designation') or exp.get('title') or '',
            'description': exp.get('description') or '',
        })
    display_skills = [s for s in version_data.get('skills', [])]
    display_projects = [p.get('title') for p in version_data.get('projects', [])]
    display_certifications = [c.get('name') for c in version_data.get('certifications', [])]
    
    print(f"Wrapper Full Name: {version_data.get('personal_info', {}).get('name')}")
    print(f"Wrapper Summary: {version_data.get('summary')}")
    print(f"Wrapper Experiences: {display_experiences}")
    print(f"Wrapper Skills: {display_skills}")
    print(f"Wrapper Projects: {display_projects}")
    print(f"Wrapper Certifications: {display_certifications}")
    print("==================================================\n")
    
    # Check if there is any other Prashant candidate profiles and delete them if they have mock/fallback email
    fallback_profiles = CandidateProfile.objects.filter(full_name='Prashant Singh').exclude(id=profile.id)
    if fallback_profiles.exists():
        print(f"Cleaning up {fallback_profiles.count()} duplicate/fallback candidate profiles from DB...")
        for p in fallback_profiles:
            p.user.delete() # Deleting user deletes profile cascades

if __name__ == "__main__":
    main()
