import pytest
import datetime
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from apps.jobs.models import Job
from apps.companies.models import Company
from apps.applications.models import Application

@pytest.mark.django_db
def test_apply_job_without_resume_fails():
    user = User.objects.create_user(
        email='no_resume_candidate@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE,
        phone_number='9876543210'
    )
    profile = CandidateProfile.objects.create(
        user=user,
        full_name='No Resume Candidate',
        location='Mumbai'
    )
    company = Company.objects.create(name='Test Company', slug='test-company')
    job = Job.objects.create(title='Backend Engineer', company=company, status='ACTIVE')

    client = APIClient()
    client.force_authenticate(user=user)

    data = {
        'job_id': str(job.id),
        'mobile_number': '9876543210',
        'current_ctc': '10.0',
        'expected_ctc': '15.0',
        'notice_period': 30,
        'current_location': 'Mumbai',
        'preferred_locations': ['Mumbai', 'Remote'],
        'key_skills': ['Python', 'Django'],
        'date_of_birth': '1995-05-15',
        'note_to_recruiter': 'Ready to join.'
    }

    res = client.post('/api/v1/applications/apply/', data, format='json')
    assert res.status_code == 400
    assert 'Please upload your resume in your Profile before applying.' in str(res.data)

@pytest.mark.django_db
def test_apply_job_invalid_mobile_number():
    user = User.objects.create_user(
        email='candidate_invalid_mobile@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE,
        phone_number='9876543210'
    )
    dummy_resume = SimpleUploadedFile("resume.pdf", b"PDF content", content_type="application/pdf")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name='Valid Candidate',
        resume=dummy_resume,
        location='Delhi'
    )
    company = Company.objects.create(name='Test Co', slug='test-co')
    job = Job.objects.create(title='Frontend Engineer', company=company, status='ACTIVE')

    client = APIClient()
    client.force_authenticate(user=user)

    data = {
        'job_id': str(job.id),
        'mobile_number': '12345',  # Invalid mobile
        'current_ctc': '8.0',
        'expected_ctc': '12.0',
        'notice_period': 15,
        'current_location': 'Delhi',
        'preferred_locations': ['Delhi'],
        'key_skills': ['React'],
        'date_of_birth': '1996-08-20'
    }

    res = client.post('/api/v1/applications/apply/', data, format='json')
    assert res.status_code == 400
    assert 'mobile_number' in res.data or 'Please enter a valid 10-digit Indian mobile number.' in str(res.data)

@pytest.mark.django_db
def test_apply_job_success():
    user = User.objects.create_user(
        email='valid_candidate@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE,
        phone_number='9988776655'
    )
    dummy_resume = SimpleUploadedFile("resume.pdf", b"PDF content", content_type="application/pdf")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name='Full Name',
        resume=dummy_resume,
        location='Bangalore'
    )
    company = Company.objects.create(name='Success Co', slug='success-co')
    job = Job.objects.create(title='Full Stack Developer', company=company, status='ACTIVE')

    client = APIClient()
    client.force_authenticate(user=user)

    data = {
        'job_id': str(job.id),
        'mobile_number': '9988776655',
        'current_ctc': '12.0',
        'expected_ctc': '18.0',
        'notice_period': 30,
        'current_location': 'Bangalore',
        'preferred_locations': ['Bangalore', 'Remote'],
        'key_skills': ['Python', 'Django', 'React'],
        'date_of_birth': '1994-11-25',
        'linkedin_url': 'https://linkedin.com/in/testuser',
        'portfolio_url': 'https://github.com/testuser',
        'note_to_recruiter': 'Excited about this opportunity!',
        'cover_letter': 'I have 5 years experience in React and Django.'
    }

    res = client.post('/api/v1/applications/apply/', data, format='json')
    assert res.status_code == 201

    app = Application.objects.get(job=job, candidate=profile)
    assert app.mobile_number == '9988776655'
    assert str(app.date_of_birth) == '1994-11-25'
    assert app.current_location == 'Bangalore'
    assert app.current_location_city == 'Bengaluru'
    assert app.current_location_tier == 'Tier 1'
    assert app.preferred_locations == ['Bangalore', 'Remote']
    assert app.key_skills == ['Python', 'Django', 'React']
    assert app.note_to_recruiter == 'Excited about this opportunity!'
    assert bool(app.resume)
    assert 'resume' in app.resume.name

@pytest.mark.django_db
def test_location_service_autocomplete_search():
    from services.location_service import LocationService
    results = LocationService.search_locations('n')
    names = [r['name'] for r in results]
    assert 'Noida Sector 18' in names or 'Noida Sector 62' in names or 'New Delhi' in names or 'Nagpur' in names
    
    noida_results = LocationService.search_locations('noida')
    noida_names = [r['name'] for r in noida_results]
    assert 'Noida Sector 62' in noida_names or 'Noida Sector 18' in noida_names or 'Knowledge Park' in noida_names

@pytest.mark.django_db
def test_apply_job_duplicate_prevented():
    user = User.objects.create_user(
        email='duplicate_candidate@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE,
        phone_number='9988776655'
    )
    dummy_resume = SimpleUploadedFile("resume.pdf", b"PDF content", content_type="application/pdf")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name='Duplicate Tester',
        resume=dummy_resume,
        location='Bangalore'
    )
    company = Company.objects.create(name='Dup Co', slug='dup-co')
    job = Job.objects.create(title='Software Engineer', company=company, status='ACTIVE')

    client = APIClient()
    client.force_authenticate(user=user)

    data = {
        'job_id': str(job.id),
        'mobile_number': '9988776655',
        'current_ctc': '12.0',
        'expected_ctc': '18.0',
        'notice_period': 30,
        'current_location': 'Bangalore',
        'preferred_locations': ['Bangalore'],
        'key_skills': ['Python', 'Django'],
        'date_of_birth': '1994-11-25'
    }

    res1 = client.post('/api/v1/applications/apply/', data, format='json')
    assert res1.status_code == 201

    res2 = client.post('/api/v1/applications/apply/', data, format='json')
    assert res2.status_code == 400
    assert 'You have already applied for this job.' in str(res2.data)

@pytest.mark.django_db
def test_apply_job_without_profile_fails():
    user = User.objects.create_user(
        email='no_profile_user@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE
    )
    company = Company.objects.create(name='NoProf Co', slug='noprof-co')
    job = Job.objects.create(title='Data Scientist', company=company, status='ACTIVE')

    client = APIClient()
    client.force_authenticate(user=user)

    data = {
        'job_id': str(job.id),
        'mobile_number': '9988776655',
        'current_ctc': '10.0',
        'expected_ctc': '15.0',
        'notice_period': 30,
        'current_location': 'Mumbai',
        'preferred_locations': ['Mumbai'],
        'key_skills': ['Python'],
        'date_of_birth': '1995-01-01'
    }

    res = client.post('/api/v1/applications/apply/', data, format='json')
    assert res.status_code == 400
    assert 'Candidate profile not found.' in str(res.data)

@pytest.mark.django_db
def test_apply_job_missing_required_fields_fails():
    user = User.objects.create_user(
        email='missing_fields@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE
    )
    dummy_resume = SimpleUploadedFile("resume.pdf", b"PDF content", content_type="application/pdf")
    profile = CandidateProfile.objects.create(
        user=user,
        full_name='Missing Fields Candidate',
        resume=dummy_resume,
        location='Delhi'
    )
    company = Company.objects.create(name='Missing Co', slug='missing-co')
    job = Job.objects.create(title='DevOps Engineer', company=company, status='ACTIVE')

    client = APIClient()
    client.force_authenticate(user=user)

    # Missing current_location and key_skills
    data = {
        'job_id': str(job.id),
        'mobile_number': '9988776655',
        'current_ctc': '10.0',
        'expected_ctc': '15.0',
        'notice_period': 30,
        'preferred_locations': ['Delhi'],
        'date_of_birth': '1995-01-01'
    }

    res = client.post('/api/v1/applications/apply/', data, format='json')
    assert res.status_code == 400
    assert 'current_location' in res.data or 'key_skills' in res.data

@pytest.mark.django_db
def test_recruiter_can_see_submitted_applicant_with_all_saved_fields():
    recruiter_user = User.objects.create_user(
        email='recruiter_view@talentvault.in',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    company = Company.objects.create(name='Recruiter Co', slug='recruiter-co')
    job = Job.objects.create(title='Staff Engineer', company=company, created_by=recruiter_user, status='ACTIVE')

    candidate_user = User.objects.create_user(
        email='candidate_full_saved@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE,
        phone_number='9876543210'
    )
    dummy_resume = SimpleUploadedFile("resume.pdf", b"PDF content", content_type="application/pdf")
    profile = CandidateProfile.objects.create(
        user=candidate_user,
        full_name='Saved Candidate',
        resume=dummy_resume,
        location='Gurugram'
    )

    client = APIClient()
    client.force_authenticate(user=candidate_user)

    data = {
        'job_id': str(job.id),
        'mobile_number': '9876543210',
        'current_ctc': '20.0',
        'expected_ctc': '30.0',
        'notice_period': 60,
        'current_location': 'Gurugram Sector 44',
        'preferred_locations': ['Gurugram', 'Noida'],
        'key_skills': ['Go', 'Kubernetes', 'Docker'],
        'date_of_birth': '1992-04-10',
        'linkedin_url': 'linkedin.com/in/savedcandidate',
        'portfolio_url': 'github.com/savedcandidate',
        'note_to_recruiter': 'Great fit for staff role.',
        'cover_letter': 'Built scalable microservices.'
    }

    res = client.post('/api/v1/applications/apply/', data, format='json')
    assert res.status_code == 201

    # Verify database fields on Application
    app = Application.objects.get(job=job, candidate=profile)
    assert app.candidate == profile
    assert app.job == job
    assert app.recruiter == recruiter_user
    assert float(app.current_ctc) == 20.0
    assert float(app.expected_ctc) == 30.0
    assert app.notice_period == 60
    assert app.current_location == 'Gurugram Sector 44'
    assert app.preferred_locations == ['Gurugram', 'Noida']
    assert app.key_skills == ['Go', 'Kubernetes', 'Docker']
    assert str(app.date_of_birth) == '1992-04-10'
    assert app.linkedin_url == 'https://linkedin.com/in/savedcandidate'
    assert app.portfolio_url == 'https://github.com/savedcandidate'
    assert app.note_to_recruiter == 'Great fit for staff role.'
    assert app.cover_letter == 'Built scalable microservices.'

    # Verify Recruiter View (JobCandidatesView / jobs/<job_id>/candidates/)
    from django.test import Client
    django_client = Client()
    django_client.force_login(recruiter_user)

    url = reverse('frontend:job_candidates', kwargs={'job_id': job.id})
    get_res = django_client.get(url)
    assert get_res.status_code == 200
    assert 'Saved Candidate' in get_res.content.decode('utf-8')
    assert 'Gurugram Sector 44' in get_res.content.decode('utf-8')

@pytest.mark.django_db
def test_salary_formatter_and_skills_slicing():
    from apps.applications.models import format_ctc_lpa
    assert format_ctc_lpa('5.5') == '₹5.5 LPA'
    assert format_ctc_lpa('7.5') == '₹7.5 LPA'
    assert format_ctc_lpa('550000.00') == '₹5.5 LPA'
    assert format_ctc_lpa('12.00') == '₹12 LPA'
    assert format_ctc_lpa(None) == 'N/A'
    assert format_ctc_lpa(0) == 'N/A'



