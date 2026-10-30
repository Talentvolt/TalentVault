"""
Tests for bulk Email to Client and AI email suggestion feature on job candidates view.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import User
from apps.companies.models import Company
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile
from apps.applications.models import Application


class JobCandidatesEmailToClientTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(
            email='recruiter.email@talentvault.in',
            password='Password123!',
            role=User.Role.RECRUITER
        )
        self.company = Company.objects.create(name='TechCorp', slug='tech-corp')
        self.job = Job.objects.create(
            title='Python Developer',
            company=self.company,
            created_by=self.recruiter,
            status='ACTIVE'
        )

        self.candidate_user1 = User.objects.create_user(
            email='candidate1@example.com',
            role=User.Role.CANDIDATE,
            phone_number='9876543210'
        )
        dummy_resume1 = SimpleUploadedFile("resume1.pdf", b"PDF bytes 1", content_type="application/pdf")
        self.profile1 = CandidateProfile.objects.create(
            user=self.candidate_user1,
            full_name='Alice Smith',
            resume=dummy_resume1,
            location='Sydney'
        )
        self.app1 = Application.objects.create(
            job=self.job,
            candidate=self.profile1,
            created_by=self.recruiter
        )

        self.client_session = Client()
        self.client_session.force_login(self.recruiter)
        mail.outbox.clear()

    def test_email_to_client_endpoint_success(self):
        url = reverse('frontend:job_candidates_email_to_client', kwargs={'job_id': self.job.id})
        response = self.client_session.post(url, {
            'candidate_ids[]': [str(self.profile1.id)],
            'to_email': 'hiring.manager@clientcorp.com',
            'cc': 'colleague@talentvault.in',
            'subject': 'Shortlisted Candidates for Python Developer',
            'body': 'Please find attached the shortlisted profiles.',
            'attach_resumes': 'true'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Verify email was sent via mail.outbox
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ['hiring.manager@clientcorp.com'])
        self.assertEqual(sent_email.cc, ['colleague@talentvault.in'])
        self.assertIn('Shortlisted Candidates for Python Developer', sent_email.subject)
        self.assertIn('Alice Smith', sent_email.body)
        self.assertEqual(len(sent_email.attachments), 1)

    def test_email_to_client_missing_recipient_fails(self):
        url = reverse('frontend:job_candidates_email_to_client', kwargs={'job_id': self.job.id})
        response = self.client_session.post(url, {
            'candidate_ids[]': [str(self.profile1.id)],
            'to_email': '',
            'subject': 'Test Subject',
            'body': 'Test Body'
        })
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])

    def test_ai_suggest_email_endpoint(self):
        url = reverse('frontend:job_candidates_ai_suggest_email', kwargs={'job_id': self.job.id})
        response = self.client_session.post(url, {
            'candidate_ids[]': [str(self.profile1.id)]
        }, content_type='application/json')
        if response.status_code != 200:
            print(f"DEBUG: Response status: {response.status_code}")
            print(f"DEBUG: Response body: {response.content.decode()}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('subject', data)
        self.assertIn('body', data)
        self.assertIn('Alice Smith', data['body'])
