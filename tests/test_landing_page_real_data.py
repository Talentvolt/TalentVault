import os
import sys
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from apps.jobs.models import Job, JobSkill
from apps.companies.models import Company
from apps.clients.models import Client as ClientModel

class LandingPageRealDataTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.company, _ = Company.objects.get_or_create(
            name="TalentVault Technologies",
            defaults={"slug": "talentvault-tech", "industry": "Software"}
        )
        self.client_company, _ = ClientModel.objects.get_or_create(
            company_name="Tech Mahindra",
            defaults={"spoc_name": "HR SPOC", "industry": "IT_SERVICES"}
        )
        
        # Create published/active job
        self.python_job = Job.objects.create(
            title="Python Developer",
            description="Python Developer needed with Django and FastAPI experience",
            location="Noida",
            company=self.company,
            client=self.client_company,
            status="ACTIVE"
        )
        JobSkill.objects.create(job=self.python_job, skill_name="Python")
        JobSkill.objects.create(job=self.python_job, skill_name="Django")

        # Create draft/inactive job
        self.draft_job = Job.objects.create(
            title="Draft Secret Job",
            description="Draft private information",
            location="Delhi",
            company=self.company,
            status="DRAFT"
        )

    def test_manage_check(self):
        """Test Django system check"""
        from django.core.management import call_command
        call_command('check')

    def test_landing_page_rendering(self):
        """Test landing page returns 200 and renders context with dynamic data and spreadsheet companies"""
        response = self.client.get(reverse('frontend:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('popular_searches', response.context)
        self.assertIn('trusted_employers', response.context)
        self.assertIn('trusted_categories', response.context)
        
        # Verify spreadsheet image companies exist in trusted_employers context
        trusted = [item['name'] for item in response.context['trusted_employers']]
        self.assertIn('Shipglobal', trusted)
        self.assertIn('Cars24', trusted)
        self.assertIn('OYO', trusted)
        self.assertIn('Apna', trusted)
        self.assertIn('Nobroker', trusted)
        self.assertIn('CUMI', trusted)
        self.assertIn('Meshr', trusted)
        
        # Verify old 7-company list and TCS/Infosys/Lenskart/Prince Pipes are NOT in the dataset
        self.assertNotIn('TCS', trusted)
        self.assertNotIn('Infosys', trusted)
        self.assertNotIn('Wipro', trusted)
        self.assertNotIn('Accenture', trusted)
        self.assertNotIn('Lenskart', trusted)
        self.assertNotIn('Prince Pipes', trusted)
        
        # Verify response HTML content
        content = response.content.decode('utf-8')
        self.assertIn('Shipglobal', content)
        self.assertIn('Cars24', content)
        self.assertIn('https://www.linkedin.com/company/talent-vault-tech/about/?viewAsMember=true', content)
        self.assertIn('https://www.instagram.com/talentvault2020?igsh=OWsydm1wMXdmZGtq', content)
        self.assertNotIn('twitter-x', content)
        self.assertNotIn('twitter.com', content)

    def test_job_search_python(self):
        """Test searching for Python returns matching active jobs and excludes draft jobs"""
        response = self.client.get(reverse('frontend:jobs') + '?search=Python')
        self.assertEqual(response.status_code, 200)
        jobs = list(response.context['jobs'])
        job_titles = [j.title for j in jobs]
        self.assertIn('Python Developer', job_titles)
        self.assertNotIn('Draft Secret Job', job_titles)

    def test_job_search_location(self):
        """Test location filter returns jobs in that location"""
        response = self.client.get(reverse('frontend:jobs') + '?location=Noida')
        self.assertEqual(response.status_code, 200)
        jobs = list(response.context['jobs'])
        job_locations = [j.location for j in jobs]
        self.assertIn('Noida', job_locations)

    def test_no_results_search(self):
        """Test searching non-existent job returns empty results cleanly"""
        response = self.client.get(reverse('frontend:jobs') + '?search=NonExistentSkillXYZ123')
        self.assertEqual(response.status_code, 200)
        jobs = list(response.context['jobs'])
        self.assertEqual(len(jobs), 0)
        content = response.content.decode('utf-8')
        self.assertIn('No jobs found', content)

    def test_location_search_api(self):
        """Test LocationSearchView returns active locations from DB"""
        response = self.client.get(reverse('frontend:location_search') + '?q=Noida')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = [r['name'] for r in data['results']]
        self.assertTrue(any('Noida' in r for r in results))

    def test_public_security(self):
        """Verify no candidate or sensitive information is leaked on public landing page"""
        response = self.client.get(reverse('frontend:dashboard'))
        content = response.content.decode('utf-8')
        self.assertNotIn('password', content)
        self.assertNotIn('SECRET_KEY', content)
