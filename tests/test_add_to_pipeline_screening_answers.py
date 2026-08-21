import pytest
from django.test import TestCase, Client as DjangoTestClient
from django.urls import reverse
from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.candidates.models import CandidateProfile
from apps.jobs.models import Job
from apps.applications.models import Application
from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine
from services.application_service import ApplicationService
from django.core.files.uploadedfile import SimpleUploadedFile


class AddToPipelineScreeningAnswersTest(TestCase):
    def setUp(self):
        TaxonomyEngine.ensure_seeded()
        self.company = Company.objects.create(name='Acme Corp', slug='acme-corp')
        self.recruiter = User.objects.create_user(
            email='recruiter_pipeline@acme.com',
            password='password123',
            first_name='Recruiter',
            last_name='User',
            role=User.Role.RECRUITER
        )
        CompanyMember.objects.create(user=self.recruiter, company=self.company, designation='Senior Recruiter')

        self.job = Job.objects.create(
            company=self.company,
            created_by=self.recruiter,
            title='Backend Python Engineer',
            status='ACTIVE',
            screening_questions=[
                {'question': 'How many years of Django experience do you have?'},
                {'question': 'Are you comfortable with PostgreSQL?'}
            ]
        )

        self.job_no_questions = Job.objects.create(
            company=self.company,
            created_by=self.recruiter,
            title='DevOps Engineer',
            status='ACTIVE',
            screening_questions=[]
        )

        # Candidate
        self.candidate_user = User.objects.create_user(
            email='candidate_pipeline@example.com',
            password='password123',
            first_name='John',
            last_name='Doe',
            role=User.Role.CANDIDATE
        )
        dummy_resume = SimpleUploadedFile("resume.pdf", b"PDF dummy content", content_type="application/pdf")
        self.candidate = CandidateProfile.objects.create(
            user=self.candidate_user,
            full_name='John Doe',
            current_designation='Python Developer',
            location='Bengaluru, India',
            total_experience=4.0,
            resume=dummy_resume
        )

        self.client = DjangoTestClient()
        self.client.force_login(self.recruiter)

    def test_single_add_to_pipeline_no_screening_answers(self):
        """
        Verify Add to Pipeline creates an Application with screening_answers=[] and never NULL
        when no screening answers are supplied.
        """
        url = reverse('frontend:add_to_pipeline', kwargs={'pk': self.candidate.id})
        response = self.client.post(
            url,
            {'job_id': str(self.job.id)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))

        app = Application.objects.get(candidate=self.candidate, job=self.job)
        self.assertTrue(app.in_pipeline)
        self.assertEqual(app.stage, Application.ApplicationStage.OPEN)
        self.assertIsNotNone(app.screening_answers)
        self.assertEqual(app.screening_answers, [])
        self.assertIsInstance(app.screening_answers, list)

    def test_single_add_to_pipeline_job_without_screening_questions(self):
        """
        Verify Add to Pipeline for a job without screening questions creates application with screening_answers=[].
        """
        url = reverse('frontend:add_to_pipeline', kwargs={'pk': self.candidate.id})
        response = self.client.post(
            url,
            {'job_id': str(self.job_no_questions.id)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))

        app = Application.objects.get(candidate=self.candidate, job=self.job_no_questions)
        self.assertIsNotNone(app.screening_answers)
        self.assertEqual(app.screening_answers, [])
        self.assertIsInstance(app.screening_answers, list)

    def test_bulk_add_to_pipeline_no_screening_answers(self):
        """
        Verify Bulk Add to Pipeline initializes screening_answers=[] for all created applications.
        """
        # Create second candidate
        cand_user2 = User.objects.create_user(
            email='candidate_pipeline2@example.com',
            password='password123',
            first_name='Jane',
            last_name='Smith',
            role=User.Role.CANDIDATE
        )
        dummy_resume2 = SimpleUploadedFile("resume2.pdf", b"PDF dummy content 2", content_type="application/pdf")
        cand2 = CandidateProfile.objects.create(
            user=cand_user2,
            full_name='Jane Smith',
            resume=dummy_resume2
        )

        url = reverse('frontend:bulk_add_to_pipeline')
        response = self.client.post(
            url,
            {'job_id': str(self.job.id), 'candidate_ids': [str(self.candidate.id), str(cand2.id)]},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('added_count'), 2)

        apps = Application.objects.filter(job=self.job)
        self.assertEqual(apps.count(), 2)
        for app in apps:
            self.assertIsNotNone(app.screening_answers)
            self.assertEqual(app.screening_answers, [])
            self.assertIsInstance(app.screening_answers, list)

    def test_application_service_apply_with_screening_answers_preserved(self):
        """
        Verify ApplicationService preserves screening answers when supplied.
        """
        answers = [
            {'question': 'How many years of Django experience do you have?', 'answer': '4 years'},
            {'question': 'Are you comfortable with PostgreSQL?', 'answer': 'Yes, highly proficient'}
        ]

        app = ApplicationService.apply_for_job(
            job_id=str(self.job.id),
            candidate_id=str(self.candidate.id),
            screening_answers=answers,
            cover_letter='Excited to apply!'
        )

        self.assertIsNotNone(app.screening_answers)
        self.assertEqual(app.screening_answers, answers)
        self.assertEqual(len(app.screening_answers), 2)
        self.assertEqual(app.screening_answers[0]['answer'], '4 years')

        # Reload from DB to verify persistence
        app_db = Application.objects.get(id=app.id)
        self.assertEqual(app_db.screening_answers, answers)

    def test_application_service_apply_without_screening_answers_defaults_to_empty_list(self):
        """
        Verify ApplicationService defaults screening_answers to [] when none provided.
        """
        app = ApplicationService.apply_for_job(
            job_id=str(self.job.id),
            candidate_id=str(self.candidate.id),
            cover_letter='Applying without screening answers'
        )

        self.assertIsNotNone(app.screening_answers)
        self.assertEqual(app.screening_answers, [])
        self.assertIsInstance(app.screening_answers, list)

    def test_application_model_safeguards_none_value(self):
        """
        Verify Application model save() safeguards against None/null value for screening_answers.
        """
        app = Application(
            job=self.job,
            candidate=self.candidate,
            stage=Application.ApplicationStage.OPEN,
            screening_answers=None
        )
        app.save()

        self.assertIsNotNone(app.screening_answers)
        self.assertEqual(app.screening_answers, [])
        self.assertIsInstance(app.screening_answers, list)

        # Reload from DB
        app.refresh_from_db()
        self.assertEqual(app.screening_answers, [])
