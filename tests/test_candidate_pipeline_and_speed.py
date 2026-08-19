import time
from django.test import TestCase, Client as DjangoTestClient
from django.urls import reverse
from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.candidates.models import CandidateProfile, CandidateSkill
from apps.jobs.models import Job
from apps.applications.models import Application
from apps.taxonomy.services.taxonomy_engine import TaxonomyEngine

class CandidatePipelineAndSpeedTest(TestCase):
    def setUp(self):
        TaxonomyEngine.ensure_seeded()
        self.company = Company.objects.create(name='Tech Recruiter Co', slug='tech-recruiter')
        self.user = User.objects.create_user(
            email='recruiter_cand@talentvault.in',
            password='password123',
            first_name='Candidate',
            last_name='Tester',
            role=User.Role.RECRUITER
        )
        CompanyMember.objects.create(user=self.user, company=self.company, designation='Lead Recruiter')

        self.job = Job.objects.create(
            company=self.company,
            created_by=self.user,
            title='Senior Fullstack Engineer',
            status='ACTIVE'
        )

        self.candidates = []
        for i in range(15):
            cand_user = User.objects.create_user(
                email=f'candidate_{i+1}@example.com',
                password='password123',
                first_name=f'Candidate_{i+1}',
                last_name='Test',
                role=User.Role.CANDIDATE
            )
            cand = CandidateProfile.objects.create(
                user=cand_user,
                full_name=f'Candidate_{i+1} Test',
                current_designation='Software Engineer',
                location='Bengaluru, India',
                total_experience=3.5,
                ats_score=85
            )
            CandidateSkill.objects.create(profile=cand, skill_name='Python')
            CandidateSkill.objects.create(profile=cand, skill_name='Django')
            self.candidates.append(cand)

        self.client = DjangoTestClient()
        self.client.force_login(self.user)

    def test_single_add_to_pipeline_ajax(self):
        """Test single candidate pipeline addition with AJAX header."""
        cand = self.candidates[0]
        url = reverse('frontend:add_to_pipeline', kwargs={'pk': cand.id})
        response = self.client.post(
            url,
            {'job_id': str(self.job.id)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertTrue(Application.objects.filter(candidate=cand, job=self.job, in_pipeline=True).exists())

    def test_single_add_to_pipeline_duplicate_protection(self):
        """Test duplicate pipeline addition returns positive non-error response."""
        cand = self.candidates[0]
        url = reverse('frontend:add_to_pipeline', kwargs={'pk': cand.id})
        # First addition
        self.client.post(url, {'job_id': str(self.job.id)}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        # Second addition attempt
        response = self.client.post(url, {'job_id': str(self.job.id)}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertFalse(data.get('created'))

    def test_bulk_add_to_pipeline(self):
        """Test bulk candidate addition in single request."""
        cand_ids = [str(c.id) for c in self.candidates[:3]]
        url = reverse('frontend:bulk_add_to_pipeline')
        response = self.client.post(
            url,
            {'job_id': str(self.job.id), 'candidate_ids': cand_ids},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('added_count'), 3)
        self.assertEqual(Application.objects.filter(job=self.job, in_pipeline=True).count(), 3)

    def test_bulk_add_validation_empty_candidates(self):
        """Test bulk pipeline validation returns 400 when no candidates selected."""
        url = reverse('frontend:bulk_add_to_pipeline')
        response = self.client.post(
            url,
            {'job_id': str(self.job.id)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn("at least one candidate", data.get('message'))

    def test_candidates_page_rendering_speed(self):
        """Test candidates page opens fast (< 1.0s)."""
        start = time.time()
        response = self.client.get(reverse('frontend:candidate_search'))
        elapsed = time.time() - start
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 1.0, f"Candidates page load took {elapsed:.2f}s (expected < 1.0s)")

    def test_recruiter_candidates_matching_speed(self):
        """Test recruiter AI candidates matching page loads fast (< 1.0s)."""
        start = time.time()
        url = f"{reverse('frontend:recruiter_candidates')}?job_id={self.job.id}"
        response = self.client.get(url)
        elapsed = time.time() - start
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 1.0, f"Recruiter candidates page took {elapsed:.2f}s (expected < 1.0s)")
