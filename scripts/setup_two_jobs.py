import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.jobs.models import Job, JobSkill
from apps.companies.models import Company
from apps.applications.models import Application
from apps.candidates.models import SavedJob
from services.candidate_matching_service import CandidateMatchingService

def run():
    print("--- Starting Two Jobs Setup ---")
    
    # 1. Company: Cars 24
    company_cars24, created = Company.objects.get_or_create(
        name="Cars 24",
        defaults={
            'slug': 'cars-24',
            'industry': 'Automotive',
            'description': 'Cars 24 is a leading tech-enabled auto-tech platform for pre-owned vehicles.',
            'location': 'Gurugram, Haryana',
            'is_active': True
        }
    )
    if not created:
        company_cars24.is_active = True
        company_cars24.save()
    print(f"Company Cars 24: {company_cars24.id}")

    # 2. Company: Lumax Group Asia
    company_lumax, created = Company.objects.get_or_create(
        name="Lumax Group Asia",
        defaults={
            'slug': 'lumax-group-asia',
            'industry': 'Automotive',
            'description': 'Lumax Group Asia is a market leader in automotive components and auto systems.',
            'location': 'New Delhi, India',
            'is_active': True
        }
    )
    if not created:
        company_lumax.is_active = True
        company_lumax.save()
    print(f"Company Lumax Group Asia: {company_lumax.id}")

    # 3. Create / Get Job 1: Car Inspector
    job1, created = Job.objects.get_or_create(
        title="Car Inspector",
        company=company_cars24,
        defaults={
            'client': None,
            'status': Job.JobStatus.ACTIVE,
            'location': 'Gurugram, Haryana',
            'job_type': 'FULL_TIME',
            'work_mode': 'ONSITE',
            'min_experience': 1,
            'max_experience': 4,
            'min_salary': 300000.00,
            'max_salary': 550000.00,
            'currency': 'INR',
            'department': 'Vehicle Inspection',
            'required_skills_text': 'Vehicle Inspection, Engine Diagnostics, Automobile Evaluation, Driving',
            'ai_matching_enabled': True,
            'description': """We are looking for a skilled and detail-oriented Car Inspector to join the Cars 24 inspection team.

Key Responsibilities:
• Conduct comprehensive multi-point inspections of pre-owned vehicles (engine, transmission, suspension, brakes, electricals, exterior, interior).
• Prepare objective and detailed vehicle evaluation and condition reports.
• Identify damages, accidental histories, repairs, odometer tampering, and wear & tear.
• Estimate repair costs and road-worthiness accurately.
• Ensure smooth coordination and excellent customer experience during evaluation visits.

Requirements & Skills:
• Diploma/Degree in Automobile / Mechanical Engineering or equivalent practical experience.
• In-depth knowledge of automobile mechanisms, diagnostics, and testing.
• Valid commercial / 4-wheeler driving license.
• Strong attention to detail and communication skills."""
        }
    )
    if not created:
        job1.client = None
        job1.company = company_cars24
        job1.status = Job.JobStatus.ACTIVE
        job1.location = 'Gurugram, Haryana'
        job1.job_type = 'FULL_TIME'
        job1.work_mode = 'ONSITE'
        job1.min_experience = 1
        job1.max_experience = 4
        job1.min_salary = 300000.00
        job1.max_salary = 550000.00
        job1.currency = 'INR'
        job1.department = 'Vehicle Inspection'
        job1.required_skills_text = 'Vehicle Inspection, Engine Diagnostics, Automobile Evaluation, Driving'
        job1.ai_matching_enabled = True
        job1.description = """We are looking for a skilled and detail-oriented Car Inspector to join the Cars 24 inspection team.

Key Responsibilities:
• Conduct comprehensive multi-point inspections of pre-owned vehicles (engine, transmission, suspension, brakes, electricals, exterior, interior).
• Prepare objective and detailed vehicle evaluation and condition reports.
• Identify damages, accidental histories, repairs, odometer tampering, and wear & tear.
• Estimate repair costs and road-worthiness accurately.
• Ensure smooth coordination and excellent customer experience during evaluation visits.

Requirements & Skills:
• Diploma/Degree in Automobile / Mechanical Engineering or equivalent practical experience.
• In-depth knowledge of automobile mechanisms, diagnostics, and testing.
• Valid commercial / 4-wheeler driving license.
• Strong attention to detail and communication skills."""
        job1.save()
    print(f"Job 1 (Car Inspector): {job1.id}")

    # Skills for Job 1
    job1_skills = ['Vehicle Inspection', 'Engine Diagnostics', 'Automobile Evaluation', 'Driving']
    JobSkill.objects.filter(job=job1).delete()
    for s in job1_skills:
        JobSkill.objects.get_or_create(job=job1, skill_name=s, is_mandatory=True)

    # 4. Create / Get Job 2: Automobile Service Advisor
    job2, created = Job.objects.get_or_create(
        title="Automobile Service Advisor",
        company=company_lumax,
        defaults={
            'client': None,
            'status': Job.JobStatus.ACTIVE,
            'location': 'Noida, Uttar Pradesh',
            'job_type': 'FULL_TIME',
            'work_mode': 'ONSITE',
            'min_experience': 2,
            'max_experience': 5,
            'min_salary': 350000.00,
            'max_salary': 600000.00,
            'currency': 'INR',
            'department': 'Aftermarket & Service',
            'required_skills_text': 'Service Advisory, Customer Relations, Job Card Management, Automobile Maintenance',
            'ai_matching_enabled': True,
            'description': """Lumax Group Asia is hiring an experienced Automobile Service Advisor to manage vehicle service operations and deliver outstanding customer satisfaction.

Key Responsibilities:
• Greet customers, understand vehicle concerns, and create detailed job cards / repair orders.
• Liaise with workshop technicians and service supervisors to ensure timely execution of repairs and maintenance.
• Explain required repairs, estimates, timelines, and warranty terms clearly to customers.
• Monitor vehicle service progress and deliver post-service walkthroughs and feedback collection.
• Drive service revenue, accessory sales, and maintain highest customer satisfaction ratings (CSI).

Requirements & Skills:
• Experience as a Service Advisor in authorized automotive dealerships or multi-brand service centers.
• Excellent customer service, negotiation, and interpersonal communication skills.
• Sound technical understanding of automobile parts, service schedules, and maintenance processes.
• Working knowledge of DMS (Dealer Management Systems) and billing software."""
        }
    )
    if not created:
        job2.client = None
        job2.company = company_lumax
        job2.status = Job.JobStatus.ACTIVE
        job2.location = 'Noida, Uttar Pradesh'
        job2.job_type = 'FULL_TIME'
        job2.work_mode = 'ONSITE'
        job2.min_experience = 2
        job2.max_experience = 5
        job2.min_salary = 350000.00
        job2.max_salary = 600000.00
        job2.currency = 'INR'
        job2.department = 'Aftermarket & Service'
        job2.required_skills_text = 'Service Advisory, Customer Relations, Job Card Management, Automobile Maintenance'
        job2.ai_matching_enabled = True
        job2.description = """Lumax Group Asia is hiring an experienced Automobile Service Advisor to manage vehicle service operations and deliver outstanding customer satisfaction.

Key Responsibilities:
• Greet customers, understand vehicle concerns, and create detailed job cards / repair orders.
• Liaise with workshop technicians and service supervisors to ensure timely execution of repairs and maintenance.
• Explain required repairs, estimates, timelines, and warranty terms clearly to customers.
• Monitor vehicle service progress and deliver post-service walkthroughs and feedback collection.
• Drive service revenue, accessory sales, and maintain highest customer satisfaction ratings (CSI).

Requirements & Skills:
• Experience as a Service Advisor in authorized automotive dealerships or multi-brand service centers.
• Excellent customer service, negotiation, and interpersonal communication skills.
• Sound technical understanding of automobile parts, service schedules, and maintenance processes.
• Working knowledge of DMS (Dealer Management Systems) and billing software."""
        job2.save()
    print(f"Job 2 (Automobile Service Advisor): {job2.id}")

    # Skills for Job 2
    job2_skills = ['Service Advisory', 'Customer Relations', 'Job Card Management', 'Automobile Maintenance']
    JobSkill.objects.filter(job=job2).delete()
    for s in job2_skills:
        JobSkill.objects.get_or_create(job=job2, skill_name=s, is_mandatory=True)

    # 5. Reassign all existing applications so no candidate or application data is lost
    other_jobs = Job.objects.exclude(id__in=[job1.id, job2.id])
    print(f"Found {other_jobs.count()} other jobs to clean up.")

    app_list = list(Application.objects.filter(job__in=other_jobs))
    print(f"Reassigning {len(app_list)} applications from other jobs...")
    
    for i, app in enumerate(app_list):
        target_job = job1 if (i % 2 == 0) else job2
        existing = Application.objects.filter(job=target_job, candidate=app.candidate).exclude(id=app.id).first()
        if existing:
            alt_job = job2 if target_job == job1 else job1
            if not Application.objects.filter(job=alt_job, candidate=app.candidate).exclude(id=app.id).exists():
                app.job = alt_job
                app.save()
            else:
                app.delete()
        else:
            app.job = target_job
            app.save()

    # Reassign or clean any SavedJobs
    SavedJob.objects.filter(job__in=other_jobs).delete()

    # Delete other jobs
    deleted_count, _ = other_jobs.delete()
    print(f"Deleted other jobs: {deleted_count}")

    # Update ATS scores
    try:
        CandidateMatchingService.update_ats_scores(job_id=job1.id)
        CandidateMatchingService.update_ats_scores(job_id=job2.id)
        print("Updated ATS scores for both jobs.")
    except Exception as e:
        print(f"ATS update warning: {e}")

    # Final verification
    all_jobs = list(Job.objects.all())
    print("\n--- FINAL VERIFICATION ---")
    print(f"Total Jobs in DB: {len(all_jobs)}")
    for j in all_jobs:
        print(f"  • {j.title} | Company: {j.company.name} | Status: {j.status} | Apps: {j.applications.count()}")
    print(f"Total Applications in DB: {Application.objects.count()}")
    print("--- Done ---")

if __name__ == '__main__':
    run()
