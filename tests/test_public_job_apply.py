import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from apps.jobs.models import Job
from apps.companies.models import Company
from apps.applications.models import Application
from apps.candidates.models import CandidateProfile
from apps.accounts.models import User

@pytest.mark.django_db
def test_public_job_apply_requires_resume(client):
    company = Company.objects.create(name="TechCorp")
    job = Job.objects.create(
        company=company,
        title="Full Stack Developer",
        description="Write code",
        location="Remote",
        status=Job.JobStatus.ACTIVE
    )

    url = reverse('frontend:public_job_apply', kwargs={'job_id': job.id})
    post_data = {
        'full_name': 'Ankit Verma',
        'email': 'ankit@example.com',
        'phone_number': '+919999988888',
        'current_location': 'Bangalore',
        'total_experience': '5',
        'current_company': 'InnovateTech',
        'current_designation': 'Senior Software Engineer',
        'current_ctc': '15',
        'expected_ctc': '20',
        'notice_period': '30',
        'preferred_location': 'Remote',
        'highest_qualification': 'B.Tech CS',
        'skills': 'Python, Django, React',
        # resume_file is intentionally missing
    }

    response = client.post(url, post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert response.status_code == 400
    data = response.json()
    assert data['success'] is False
    assert "Resume upload is required" in data['message']

@pytest.mark.django_db
def test_public_job_apply_rejects_non_pdf_resume(client):
    company = Company.objects.create(name="TechCorp")
    job = Job.objects.create(
        company=company,
        title="Full Stack Developer",
        description="Write code",
        location="Remote",
        status=Job.JobStatus.ACTIVE
    )

    docx_file = SimpleUploadedFile(
        "Resume.docx",
        b"docx test resume content",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    url = reverse('frontend:public_job_apply', kwargs={'job_id': job.id})
    post_data = {
        'full_name': 'Ankit Verma',
        'email': 'ankit@example.com',
        'phone_number': '+919999988888',
        'current_location': 'Bangalore',
        'total_experience': '5',
        'current_company': 'InnovateTech',
        'current_designation': 'Senior Software Engineer',
        'current_ctc': '15',
        'expected_ctc': '20',
        'notice_period': '30',
        'preferred_location': 'Remote',
        'highest_qualification': 'B.Tech CS',
        'skills': 'Python, Django, React',
        'resume_file': docx_file
    }

    response = client.post(url, post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert response.status_code == 400
    data = response.json()
    assert data['success'] is False
    assert "Only PDF resumes are allowed." in data['message']

@pytest.mark.django_db(transaction=True)
def test_public_job_apply_success_workflow(client):
    company = Company.objects.create(name="TechCorp")
    recruiter_user = User.objects.create_user(email="recruiter@techcorp.com", role=User.Role.RECRUITER)
    job = Job.objects.create(
        company=company,
        title="Python Lead",
        description="Lead python development",
        location="Mumbai",
        created_by=recruiter_user,
        status=Job.JobStatus.ACTIVE
    )

    resume_file = SimpleUploadedFile(
        "Candidate_Resume.pdf",
        b"%PDF-1.4 test resume content for Ankit Verma Python Django Developer",
        content_type="application/pdf"
    )

    url = reverse('frontend:public_job_apply', kwargs={'job_id': job.id})
    post_data = {
        'full_name': 'Ankit Verma',
        'email': 'ankit.verma@example.com',
        'phone_number': '+919876543210',
        'current_location': 'Mumbai',
        'total_experience': '6',
        'current_company': 'DevStudio',
        'current_designation': 'Lead Architect',
        'current_ctc': '18.5',
        'expected_ctc': '24.0',
        'notice_period': '15',
        'preferred_location': 'Mumbai / Remote',
        'highest_qualification': 'M.Tech IT',
        'skills': 'Python, Django, PostgreSQL, Docker',
        'cover_letter': 'Excited to join TechCorp as Python Lead.',
        'linkedin_url': 'https://linkedin.com/in/ankitverma',
        'portfolio_url': 'https://ankitverma.dev',
        'resume_file': resume_file
    }

    response = client.post(url, post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['message'] == "Application Submitted Successfully."

    # Verify Candidate User created without password requirement
    candidate_user = User.objects.get(email='ankit.verma@example.com')
    assert candidate_user.role == User.Role.CANDIDATE
    assert candidate_user.has_usable_password() is False

    # Verify CandidateProfile
    profile = CandidateProfile.objects.get(user=candidate_user)
    assert profile.full_name == 'Ankit Verma'
    assert profile.location == 'Mumbai'
    assert float(profile.total_experience) == 6.0
    assert profile.current_company == 'DevStudio'
    assert profile.current_designation == 'Lead Architect'
    assert float(profile.current_salary) == 18.5
    assert float(profile.expected_salary) == 24.0
    assert profile.notice_period == 15
    assert profile.preferred_location == 'Mumbai / Remote'
    assert profile.linkedin_url == 'https://linkedin.com/in/ankitverma'
    assert profile.portfolio_url == 'https://ankitverma.dev'

    # Verify Skills, Experience, and Education saved on CandidateProfile
    assert profile.skills.filter(skill_name='Python').exists()
    assert profile.experiences.filter(company_name='DevStudio').exists()
    assert profile.educations.filter(degree='M.Tech IT').exists()

    # Verify Application created & linked
    app = Application.objects.get(job=job, candidate=profile)
    assert app.stage == Application.ApplicationStage.OPEN
    assert app.in_pipeline is True
    assert app.cover_letter == 'Excited to join TechCorp as Python Lead.'
    assert app.current_company == 'DevStudio'
    assert app.current_designation == 'Lead Architect'
    assert float(app.total_experience) == 6.0
    assert float(app.current_ctc) == 18.5
    assert float(app.expected_ctc) == 24.0
    assert app.notice_period == 15
    assert app.preferred_location == 'Mumbai / Remote'

    # Verify Recruiter Dashboard context
    client.force_login(recruiter_user)
    dashboard_url = reverse('frontend:recruiter_dashboard')
    dash_response = client.get(dashboard_url)
    assert dash_response.status_code == 200
    assert any(a.id == app.id for a in dash_response.context['recent_applications'])
