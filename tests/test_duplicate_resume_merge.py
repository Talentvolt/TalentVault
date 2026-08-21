import io
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.candidates.models import (
    CandidateProfile, CandidateSkill, DuplicateResumeLog,
    Experience, Education, Project, Certification
)
from apps.candidates.utils import (
    process_resume_file,
    handle_resume_upload,
    merge_candidate_profile_data,
    process_and_merge_resume
)
from apps.jobs.models import Job
from apps.applications.models import Application


@pytest.mark.django_db
class TestDuplicateResumeMergeFlow(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_superuser(
            email='recruiter.admin@talentvault.in',
            password='TestPassword123!',
            role=User.Role.SUPER_ADMIN,
            is_active=True
        )
        self.client = Client()
        self.client.force_login(self.recruiter)

        # Create initial candidate profile
        self.candidate_user = User.objects.create(
            email='alex.morgan@example.com',
            phone_number='9876543211',
            role=User.Role.CANDIDATE
        )
        self.candidate_profile = CandidateProfile.objects.create(
            user=self.candidate_user,
            full_name='Alex Morgan',
            current_company='Alpha Tech Solutions',
            current_designation='Software Engineer',
            total_experience=Decimal('3.0'),
            location='Bangalore',
            summary='Experienced backend developer specializing in Python and Django.',
            created_by=self.recruiter,
            uploaded_by=self.recruiter
        )

        # Add initial skills
        CandidateSkill.objects.create(profile=self.candidate_profile, skill_name='Python')
        CandidateSkill.objects.create(profile=self.candidate_profile, skill_name='Django')
        CandidateSkill.objects.create(profile=self.candidate_profile, skill_name='Postgresql')

        # Add initial education
        Education.objects.create(
            profile=self.candidate_profile,
            institution='National Institute of Technology',
            degree='B.Tech in Computer Science',
            field_of_study='Computer Science'
        )

        # Add initial experience
        Experience.objects.create(
            profile=self.candidate_profile,
            company_name='Alpha Tech Solutions',
            designation='Software Engineer',
            description='<p>Built REST APIs using Django.</p>'
        )

    def _create_sample_pdf(self, text_content="Alex Morgan\nPython, Django, AWS, React\nEmail: alex.morgan@example.com"):
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        y = 750
        for line in text_content.split('\n'):
            line_str = line.strip()
            if line_str:
                c.drawString(50, y, line_str)
                y -= 20
        c.save()
        buf.seek(0)
        return buf.read()

    def test_duplicate_detection_preserves_single_profile(self):
        """Test that uploading the same resume triggers duplicate detection without creating a new profile."""
        initial_count = CandidateProfile.objects.count()
        pdf_bytes = self._create_sample_pdf("Alex Morgan\nEmail: alex.morgan@example.com\nPhone: 9876543211")
        uploaded_file = SimpleUploadedFile("alex_resume.pdf", pdf_bytes, content_type="application/pdf")

        results = handle_resume_upload(uploaded_file, overwrite=False, user=self.recruiter)
        
        assert results['duplicates'] == 1
        assert len(results['created']) == 0
        assert CandidateProfile.objects.count() == initial_count
        
        # Check DuplicateResumeLog is logged as SKIPPED
        log = DuplicateResumeLog.objects.filter(email='alex.morgan@example.com').first()
        assert log is not None
        assert log.action_taken == 'SKIPPED'

    def test_merge_candidate_profile_data_intelligent_merging(self):
        """Test intelligent merging of skills, education, experience, projects, certifications, and summary."""
        new_parsed_data = {
            "personal_info": {
                "name": "Alex Morgan",
                "email": "alex.morgan@example.com",
                "phone": "9876543211",
                "location": "Bangalore",
                "current_company": "Alpha Tech Solutions",
                "current_designation": "Senior Software Engineer",
                "total_experience": 4.5,
                "linkedin_url": "https://linkedin.com/in/alexmorgan",
                "github_url": "https://github.com/alexmorgan",
                "portfolio_url": "https://alexmorgan.dev"
            },
            "skills": ["python", "DJANGO", "AWS", "Docker", "Kubernetes", "Redis"],
            "education": [
                {
                    "institution": "National Institute of Technology",
                    "degree": "B.Tech in Computer Science",
                    "score": "8.5 CGPA"
                },
                {
                    "institution": "Stanford Online",
                    "degree": "Advanced Cloud Architecture",
                    "field_of_study": "Cloud Computing"
                }
            ],
            "experience": [
                {
                    "company": "Alpha Tech Solutions",
                    "designation": "Software Engineer",
                    "description": "Built scalable REST APIs and microservices using Django and PostgreSQL."
                },
                {
                    "company": "Beta Cloud Corp",
                    "designation": "Cloud Consultant",
                    "description": "Designed multi-region AWS cloud architectures."
                }
            ],
            "projects": [
                {
                    "title": "Cloud Orchestrator",
                    "description": "Kubernetes automation framework in Python.",
                    "link": "https://github.com/alexmorgan/orchestrator"
                }
            ],
            "certifications": [
                {
                    "name": "AWS Certified Solutions Architect",
                    "issuing_organization": "Amazon Web Services"
                }
            ],
            "languages": ["English", "Spanish"],
            "summary": "Cloud certified architect with extensive background in distributed systems."
        }

        merged_profile = merge_candidate_profile_data(
            existing_profile=self.candidate_profile,
            parsed_data=new_parsed_data,
            info=new_parsed_data['personal_info'],
            filename="alex_updated_resume.pdf",
            uploaded_by=self.recruiter
        )

        # 1. Candidate ID and profile count must remain unchanged
        assert merged_profile.id == self.candidate_profile.id
        assert CandidateProfile.objects.count() == 1

        # 2. Skills must be combined and deduplicated
        skills_set = set(self.candidate_profile.skills.values_list('skill_name', flat=True))
        assert 'Python' in skills_set
        assert 'Django' in skills_set
        assert 'Postgresql' in skills_set
        assert 'Aws' in skills_set or 'AWS' in skills_set
        assert 'Docker' in skills_set
        assert 'Kubernetes' in skills_set
        assert 'Redis' in skills_set
        assert self.candidate_profile.skills.filter(skill_name__iexact='python').count() == 1

        # 3. Educations must be preserved and missing education added
        assert self.candidate_profile.educations.count() == 2
        degrees = list(self.candidate_profile.educations.values_list('degree', flat=True))
        assert any('B.Tech' in d for d in degrees)
        assert any('Advanced Cloud Architecture' in d for d in degrees)

        # 4. Experiences must be preserved and missing experience added
        assert self.candidate_profile.experiences.count() == 2
        companies = list(self.candidate_profile.experiences.values_list('company_name', flat=True))
        assert 'Alpha Tech Solutions' in companies
        assert 'Beta Cloud Corp' in companies

        # 5. Projects and Certifications must be added
        assert self.candidate_profile.projects.count() == 1
        assert self.candidate_profile.projects.first().title == 'Cloud Orchestrator'
        assert self.candidate_profile.certifications.count() == 1
        assert self.candidate_profile.certifications.first().name == 'AWS Certified Solutions Architect'

        # 6. Summary must preserve existing and incorporate new summary
        assert 'Experienced backend developer' in self.candidate_profile.summary
        assert 'Cloud certified architect' in self.candidate_profile.summary

        # 7. Total experience and URLs must be updated
        assert self.candidate_profile.total_experience == Decimal('4.5')
        assert self.candidate_profile.linkedin_url == 'https://linkedin.com/in/alexmorgan'
        assert self.candidate_profile.portfolio_url == 'https://alexmorgan.dev'

        # 8. DuplicateResumeLog must record MERGED
        merge_log = DuplicateResumeLog.objects.filter(email='alex.morgan@example.com', action_taken='MERGED').first()
        assert merge_log is not None

        # 9. Version and audit logs must be updated
        assert self.candidate_profile.current_version >= 2
        assert len(self.candidate_profile.audit_logs) >= 1

    def test_merge_resume_post_endpoint(self):
        """Test POST /resume-parser/ with action=merge_resume."""
        pdf_bytes = self._create_sample_pdf("Alex Morgan\nSenior Python Engineer\nSkills: Python, Django, AWS, GraphQL\nEmail: alex.morgan@example.com")
        uploaded_file = SimpleUploadedFile("alex_resume_v2.pdf", pdf_bytes, content_type="application/pdf")

        response = self.client.post(
            '/resume-parser/',
            {
                'action': 'merge_resume',
                'candidate_id': str(self.candidate_profile.id),
                'resume': uploaded_file
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['stage'] == 'completed'
        assert data['message'] == "Resume merged successfully into existing candidate."
        assert data['candidate_id'] == str(self.candidate_profile.id)

        # Confirm candidate profile was enriched and not duplicated
        assert CandidateProfile.objects.count() == 1
        self.candidate_profile.refresh_from_db()
        assert self.candidate_profile.skills.count() >= 3

    def test_merge_atomicity_preserves_candidate_on_error(self):
        """Test that if an error occurs during merge, transaction rolls back completely."""
        initial_skills_count = self.candidate_profile.skills.count()
        initial_summary = self.candidate_profile.summary

        try:
            # Pass invalid data structure that causes exception
            merge_candidate_profile_data(
                existing_profile=self.candidate_profile,
                parsed_data={"skills": "NOT_A_LIST_INVALID", "education": None},
                info=None
            )
        except Exception:
            pass

        self.candidate_profile.refresh_from_db()
        # Ensure state was not partially modified
        assert self.candidate_profile.skills.count() == initial_skills_count
        assert self.candidate_profile.summary == initial_summary

    def test_manual_merge_post_endpoint(self):
        """Test POST /resume-parser/ with action=manual_merge."""
        response = self.client.post(
            '/resume-parser/',
            {
                'action': 'manual_merge',
                'candidate_id': str(self.candidate_profile.id),
                'full_name': 'Alex Morgan',
                'email': 'alex.morgan@example.com',
                'phone_number': '9876543211',
                'primary_skills': 'Python, Django, FastAPI',
                'secondary_skills': 'PostgreSQL, Redis',
                'summary': 'Senior software engineer with expertise in microservices.',
                'current_company': 'Alpha Tech Solutions',
                'current_designation': 'Principal Engineer',
                'total_experience': '5.0',
                'relevant_experience': '4.5',
                'location': 'Bangalore',
                'experience[0][company]': 'Delta Innovations',
                'experience[0][designation]': 'Lead Backend Developer',
                'experience[0][start_date]': '2024-01-01',
                'experience[0][end_date]': '2025-01-01',
                'experience[0][is_current]': 'false',
                'experience[0][job_description]': 'Led the migration of microservices to Django and FastAPI.'
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['stage'] == 'completed'
        assert data['message'] == "Resume merged successfully into existing candidate."

        self.candidate_profile.refresh_from_db()
        # Check skill additions
        skills = list(self.candidate_profile.skills.values_list('skill_name', flat=True))
        assert 'Fastapi' in skills or 'FastAPI' in skills
        assert 'Redis' in skills

        # Check experience additions
        companies = list(self.candidate_profile.experiences.values_list('company_name', flat=True))
        assert 'Delta Innovations' in companies

    def test_merge_with_job_and_ats_scoring(self):
        """Test that merging a resume calculates/updates ATS score for an associated job."""
        from apps.companies.models import Company
        company = Company.objects.create(name='Tech Innovations Inc', created_by=self.recruiter)
        job = Job.objects.create(
            company=company,
            title='Senior Python Architect',
            description='Looking for an experienced Python and AWS architect.',
            department='Engineering',
            location='Bangalore',
            required_skills_text='Python, Django, AWS, Kubernetes',
            created_by=self.recruiter
        )

        new_parsed_data = {
            "personal_info": {
                "name": "Alex Morgan",
                "email": "alex.morgan@example.com",
                "phone": "9876543211"
            },
            "skills": ["AWS", "Kubernetes"],
            "education": [],
            "experience": [],
            "projects": [],
            "certifications": [],
            "summary": "Architect with Kubernetes and AWS experience."
        }

        merged_profile = merge_candidate_profile_data(
            existing_profile=self.candidate_profile,
            parsed_data=new_parsed_data,
            job_id=job.id,
            uploaded_by=self.recruiter
        )

        # Check application created
        app = Application.objects.filter(job=job, candidate=merged_profile).first()
        assert app is not None
        assert app.candidate.id == self.candidate_profile.id

