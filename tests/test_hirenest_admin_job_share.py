"""
TalentVault Admin Portal — HireNest Australia job sharing links.

Verifies the admin "HireNest Australia Jobs" listing exposes permanent public
share links (built from the production HireNest domain) for active postings only.
"""
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


LIST_URL_NAME = 'frontend:admin_hirenest_jobs'
TEST_BASE_URL = 'https://hirenest.example'
TEST_API_KEY = 'tv-test-key-not-a-real-secret'
JOB_ID = '22222222-2222-2222-2222-222222222222'

ACTIVE_JOB = {
    'id': JOB_ID,
    'title': 'Senior Data Engineer',
    'company_name': 'Sydney Analytics Group',
    'company_id': '33333333-3333-3333-3333-333333333333',
    'location': 'Sydney NSW',
    'job_type': 'FULL_TIME',
    'work_mode': 'HYBRID',
    'department': 'Engineering',
    'status': 'ACTIVE',
    'currency': 'AUD',
    'min_experience': 5,
    'max_experience': 10,
    'min_salary': '150000.00',
    'max_salary': '190000.00',
    'salary_display': '$150,000 - $190,000 / year',
    'required_skills_text': 'Python, AWS',
    'preferred_skills_text': '',
    'description': 'Build the Australian data platform.',
    'source': 'ADMIN',
    'posted_by_admin': True,
    'created_at': '2026-01-01T00:00:00+00:00',
}


def _fake_response(payload):
    response = mock.Mock()
    response.status_code = 200
    response.text = ''
    response.json.return_value = payload
    return response


class HireNestAdminJobShareTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='tv.admin@example.com', password='AdminPass123!'
        )
        self.list_url = reverse(LIST_URL_NAME)

    def _configured(self):
        return self.settings(
            HIRENEST_API_BASE_URL=TEST_BASE_URL,
            HIRENEST_ADMIN_API_KEY=TEST_API_KEY,
        )

    def test_active_job_share_url_uses_production_domain(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', return_value=_fake_response({'jobs': [ACTIVE_JOB]})
            ):
                response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        share_url = f'https://hirenest.com.au/jobs/{JOB_ID}/'
        self.assertContains(response, f'data-share-url="{share_url}"')

    def test_share_url_never_uses_api_base_or_localhost(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', return_value=_fake_response({'jobs': [ACTIVE_JOB]})
            ):
                response = self.client.get(self.list_url)

        content = response.content.decode('utf-8')
        self.assertNotIn('localhost', content)
        self.assertNotIn('127.0.0.1', content)
        self.assertNotIn('hirenest.example/jobs/', content)

    def test_non_active_job_has_no_share_control(self):
        self.client.force_login(self.admin)
        draft = dict(ACTIVE_JOB, status='DRAFT')
        with self._configured():
            with mock.patch(
                'requests.get', return_value=_fake_response({'jobs': [draft]})
            ):
                response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Senior Data Engineer')
        self.assertNotContains(response, f'data-share-url="https://hirenest.com.au/jobs/{JOB_ID}/"')

    def test_public_base_url_helper(self):
        from apps.core.views import HirenestAdminJobsView

        view = HirenestAdminJobsView()
        with self.settings(HIRENEST_PUBLIC_BASE_URL='https://hirenest.com.au/'):
            self.assertEqual(view._public_base_url(), 'https://hirenest.com.au')
        with self.settings(HIRENEST_PUBLIC_BASE_URL=''):
            self.assertEqual(view._public_base_url(), 'https://hirenest.com.au')
