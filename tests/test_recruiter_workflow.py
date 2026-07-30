import pytest
from django.test import Client
from apps.accounts.models import User
from apps.jobs.models import Job, JobSkill
from apps.candidates.models import CandidateProfile, CandidateSkill
from apps.companies.models import Company, CompanyMember

@pytest.mark.django_db
def test_employer_registration_flow_and_pending_status():
    client = Client()
    # 1. Register new employer
    response = client.post('/accounts/signup/employer/', {
        'email': 'new_recruiter@company.com',
        'password': 'Password123!',
        'phone_number': '+1999888777',
        'org_name': 'Acme Corp',
        'hiring_type': 'organization',
        'website': 'https://acme.com',
        'company_size': '50-100',
        'industry': 'Software'
    }, follow=True)

    assert response.status_code == 200
    user = User.objects.get(email='new_recruiter@company.com')
    assert user.role == User.Role.RECRUITER
    assert user.recruiter_status == User.RecruiterStatus.PENDING

    # 2. Attempt login while PENDING -> should be rejected with message
    login_res = client.post('/accounts/login/employer/', {
        'email': 'new_recruiter@company.com',
        'password': 'Password123!'
    })
    assert login_res.status_code == 200
    assert "Your account is currently under verification" in login_res.content.decode('utf-8')


@pytest.mark.django_db
def test_admin_approval_system():
    admin = User.objects.create_superuser(email='admin_master@talentvault.in', password='Password123!', role=User.Role.SUPER_ADMIN)
    recruiter = User.objects.create_user(
        email='pending_rec@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.PENDING
    )
    client = Client()
    client.force_login(admin)

    # Admin approves recruiter
    res = client.post('/dashboard/admin/recruiter-approvals/', {
        'user_id': str(recruiter.id),
        'action': 'approve'
    }, follow=True)

    assert res.status_code == 200
    recruiter.refresh_from_db()
    assert recruiter.recruiter_status == User.RecruiterStatus.ACTIVE

    # Now recruiter can log in
    client.logout()
    login_res = client.post('/accounts/login/employer/', {
        'email': 'pending_rec@company.com',
        'password': 'Password123!'
    }, follow=True)
    assert login_res.status_code == 200
    assert login_res.redirect_chain[-1][0] == '/dashboard/recruiter/'


@pytest.mark.django_db
def test_recruiter_job_creation_and_ai_candidate_matching():
    recruiter = User.objects.create_user(
        email='active_rec@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE
    )
    company = Company.objects.create(name='DevOps Inc', slug='devops-inc')
    CompanyMember.objects.create(company=company, user=recruiter, designation='Lead Recruiter')

    # Create Candidates: 1 DevOps, 1 Accountant
    cand_user1 = User.objects.create_user(email='devops_cand@talentvault.in', password='Password123!', role=User.Role.CANDIDATE)
    c_profile1 = CandidateProfile.objects.create(
        user=cand_user1,
        full_name='Alex Docker',
        current_designation='DevOps Engineer',
        total_experience=4.0,
        location='Bangalore'
    )
    CandidateSkill.objects.create(profile=c_profile1, skill_name='Docker')
    CandidateSkill.objects.create(profile=c_profile1, skill_name='AWS')
    CandidateSkill.objects.create(profile=c_profile1, skill_name='Kubernetes')

    cand_user2 = User.objects.create_user(email='accountant_cand@talentvault.in', password='Password123!', role=User.Role.CANDIDATE)
    c_profile2 = CandidateProfile.objects.create(
        user=cand_user2,
        full_name='John Finance',
        current_designation='Senior Accountant',
        total_experience=5.0,
        location='Mumbai'
    )
    CandidateSkill.objects.create(profile=c_profile2, skill_name='Tally')
    CandidateSkill.objects.create(profile=c_profile2, skill_name='Accounting')

    client = Client()
    client.force_login(recruiter)

    # 1. Post DevOps Job
    create_job_res = client.post('/recruiter/jobs/', {
        'action': 'create',
        'title': 'Senior DevOps Engineer',
        'department': 'Cloud Ops',
        'job_type': 'FULL_TIME',
        'location': 'Bangalore',
        'min_experience': 2,
        'max_experience': 6,
        'min_salary': 12.0,
        'max_salary': 20.0,
        'required_skills': 'Docker, AWS, Kubernetes',
        'preferred_skills': 'Terraform, Linux',
        'education': 'B.Tech',
        'notice_period': 30,
        'description': 'Looking for experienced DevOps Engineer to manage Kubernetes clusters on AWS.',
        'ai_matching_enabled': 'on'
    }, follow=True)

    assert create_job_res.status_code == 200
    job = Job.objects.get(title='Senior DevOps Engineer')
    assert job.department == 'Cloud Ops'
    assert job.ai_matching_enabled is True

    # 2. View AI Matched Candidates
    match_res = client.get(f'/recruiter/candidates/?job_id={job.id}')
    assert match_res.status_code == 200
    matched_list = match_res.context['candidates']

    # DevOps candidate should be matched, Accountant should be excluded
    matched_names = [m['candidate'].full_name for m in matched_list]
    assert 'Alex Docker' in matched_names
    assert 'John Finance' not in matched_names
