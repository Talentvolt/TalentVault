import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User
from apps.companies.models import Company
from apps.jobs.models import Job, JobSkill
from apps.candidates.models import CandidateProfile, CandidateSkill
from services.candidate_matching_service import CandidateMatchingService

def run_test():
    # 1. Create a Company
    company, _ = Company.objects.get_or_create(
        name="TechCorp",
        slug="techcorp",
        location="Remote"
    )

    # 2. Create a Job
    job, _ = Job.objects.get_or_create(
        company=company,
        title="Full Stack Developer",
        min_experience=6,
        max_experience=12,
        location="Remote",
        is_remote=True
    )
    
    # Add Job Skills
    skills_required = ["HTML", "CSS", "JavaScript", "React", "Node.js"]
    for skill_name in skills_required:
        JobSkill.objects.get_or_create(job=job, skill_name=skill_name)

    # 3. Create Candidates
    candidates_data = [
        {
            "email": "candidate1@example.com",
            "skills": ["HTML", "CSS", "JavaScript", "React", "Node.js"],
            "experience": 8
        },
        {
            "email": "candidate2@example.com",
            "skills": ["HTML", "CSS", "JavaScript", "React"],
            "experience": 7
        },
        {
            "email": "candidate3@example.com",
            "skills": ["Java", "Spring Boot", "Hibernate"],
            "experience": 10
        },
        {
            "email": "candidate4@example.com",
            "skills": ["HTML", "CSS"],
            "experience": 3
        }
    ]

    results = []

    for data in candidates_data:
        user, _ = User.objects.get_or_create(email=data["email"], role=User.Role.CANDIDATE)
        profile, _ = CandidateProfile.objects.get_or_create(
            user=user,
            location="Remote",
            total_experience=data["experience"]
        )
        # Clear existing skills for re-runability
        profile.skills.all().delete()
        for skill_name in data["skills"]:
            CandidateSkill.objects.create(profile=profile, skill_name=skill_name)

        # Run matching engine
        match_data = CandidateMatchingService.calculate_match_score(job, profile)
        
        results.append({
            "email": data["email"],
            "skills": ", ".join(data["skills"]),
            "experience": data["experience"],
            "match_score": match_data["match_score"],
            "is_qualified": match_data["is_qualified"]
        })

    # Display Results
    print(f"\n{'='*80}")
    print(f"{'Smart Candidate Search - Verification Results':^80}")
    print(f"{'='*80}\n")
    print(f"Job Requirements:")
    print(f"Skills: {', '.join(skills_required)}")
    print(f"Min Experience: 6 years\n")
    
    print(f"{'Candidate':<25} | {'Exp':<3} | {'Match %':<8} | {'Qualified?':<10}")
    print(f"{'-'*25}-+-{'-'*3}-+-{'-'*8}-+-{'-'*10}")
    
    for res in results:
        status = "INCLUDED" if res["is_qualified"] else "EXCLUDED"
        print(f"{res['email']:<25} | {res['experience']:<3} | {res['match_score']:<8.1f} | {status:<10}")

    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"Error running test: {e}")
