"""
TalentVault Admin Portal — HireNest Australia jobs integration.

These tests verify the admin-only proxy views that create and manage HireNest
Australia job postings. The views never touch the HireNest database directly;
they call the HireNest admin API, so the HTTP calls are mocked here. No real
secret is used anywhere in this file.
"""
from unittest import mock

import requests
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.jobs.models import Job


LIST_URL_NAME = 'frontend:admin_hirenest_jobs'
DETAIL_URL_NAME = 'frontend:admin_hirenest_job_detail'
TEST_BASE_URL = 'https://hirenest.example'
# Clearly fake value used only by the tests. Not a production secret.
TEST_API_KEY = 'tv-test-key-not-a-real-secret'
JOB_ID = '22222222-2222-2222-2222-222222222222'

HIRENEST_JOB = {
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


def _fake_response(payload=None, status_code=200, text=''):
    response = mock.Mock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = payload if payload is not None else {'jobs': []}
    response.raise_for_status.return_value = None
    return response


class HireNestAdminJobsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='tv.admin@example.com', password='AdminPass123!'
        )
        self.recruiter = User.objects.create_user(
            email='recruiter@talentvault.in',
            password='RecruiterPass123!',
            role=User.Role.RECRUITER,
            recruiter_status=User.RecruiterStatus.ACTIVE,
        )
        self.list_url = reverse(LIST_URL_NAME)
        self.detail_url = reverse(DETAIL_URL_NAME, args=[JOB_ID])

    def _configured(self, api_key=TEST_API_KEY):
        return self.settings(
            HIRENEST_API_BASE_URL=TEST_BASE_URL,
            HIRENEST_ADMIN_API_KEY=api_key,
        )

    # ------------------------------------------------------------------
    # Configuration handling
    # ------------------------------------------------------------------
    def test_missing_configuration_shows_warning_without_http_call(self):
        self.client.force_login(self.admin)
        with self.settings(HIRENEST_API_BASE_URL='', HIRENEST_ADMIN_API_KEY=TEST_API_KEY):
            with mock.patch('requests.get') as mocked_get:
                response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not configured')
        self.assertContains(response, 'HIRENEST_API_BASE_URL')
        mocked_get.assert_not_called()

    # ------------------------------------------------------------------
    # URL name / namespace consistency (NoReverseMatch regression)
    # ------------------------------------------------------------------
    def test_admin_hirenest_jobs_url_name_and_namespace(self):
        # templates/base.html references {% url 'frontend:admin_hirenest_jobs' %}.
        # The registered URL name must stay in the 'frontend' namespace.
        self.assertEqual(
            reverse('frontend:admin_hirenest_jobs'),
            '/dashboard/admin/hirenest-jobs/',
        )
        self.assertEqual(
            reverse('frontend:admin_hirenest_job_detail', args=[JOB_ID]),
            f'/dashboard/admin/hirenest-jobs/{JOB_ID}/',
        )
        # The existing employer approvals page must keep reversing too.
        self.assertEqual(
            reverse('frontend:admin_hirenest_employer_approvals'),
            '/dashboard/admin/hirenest-employer-approvals/',
        )

    def test_admin_page_renders_sidebar_without_reverse_error(self):
        self.client.force_login(self.admin)
        with self.settings(HIRENEST_API_BASE_URL='', HIRENEST_ADMIN_API_KEY=TEST_API_KEY):
            response = self.client.get('/dashboard/admin/hirenest-jobs/')

        self.assertEqual(response.status_code, 200)
        # The base.html sidebar link resolved (no NoReverseMatch) and rendered.
        self.assertContains(response, 'HireNest Australia Jobs')
        self.assertContains(response, '/dashboard/admin/hirenest-jobs/')

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    def test_list_uses_configured_url_and_admin_key_header(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', return_value=_fake_response({'jobs': [HIRENEST_JOB]})
            ) as mocked_get:
                response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Senior Data Engineer')
        args, kwargs = mocked_get.call_args
        called_url = args[0] if args else ''
        self.assertTrue(called_url.startswith(f'{TEST_BASE_URL}/api/admin/jobs/'))
        self.assertIn('status=ALL', called_url)
        self.assertEqual(kwargs['headers']['X-HireNest-Admin-Key'], TEST_API_KEY)
        # The secret must never be placed in the URL.
        self.assertNotIn(TEST_API_KEY, called_url)

    def test_list_renders_edit_form_prefilled(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', return_value=_fake_response({'jobs': [HIRENEST_JOB]})
            ):
                response = self.client.get(self.list_url + f'?edit={JOB_ID}')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sydney Analytics Group')
        self.assertContains(response, 'Build the Australian data platform.')

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def test_create_posts_job_to_hirenest(self):
        self.client.force_login(self.admin)
        local_jobs_before = Job.objects.count()
        with self._configured():
            with mock.patch(
                'requests.post',
                return_value=_fake_response(
                    {'message': "Job 'Senior Data Engineer' posted to HireNest Australia."},
                    status_code=201,
                ),
            ) as mocked_post:
                response = self.client.post(self.list_url, {
                    'title': 'Senior Data Engineer',
                    'company_name': 'Sydney Analytics Group',
                    'location': 'Sydney NSW',
                    'department': 'Engineering',
                    'job_type': 'FULL_TIME',
                    'work_mode': 'HYBRID',
                    'status': 'ACTIVE',
                    'min_experience': '5',
                    'max_experience': '10',
                    'min_salary': '150000',
                    'max_salary': '190000',
                    'required_skills_text': 'Python, AWS',
                    'preferred_skills_text': '',
                    'description': 'Build the Australian data platform.',
                }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'posted to HireNest Australia')
        args, kwargs = mocked_post.call_args
        self.assertEqual(args[0], f'{TEST_BASE_URL}/api/admin/jobs/')
        self.assertEqual(kwargs['json']['title'], 'Senior Data Engineer')
        self.assertEqual(kwargs['json']['location'], 'Sydney NSW')
        self.assertEqual(kwargs['headers']['X-HireNest-Admin-Key'], TEST_API_KEY)
        # Creating a HireNest job must not create a TalentVault India job.
        self.assertEqual(Job.objects.count(), local_jobs_before)

    def test_create_rejected_by_hirenest_shows_error(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.post',
                return_value=_fake_response({'error': 'title is required.'}, status_code=400),
            ):
                response = self.client.post(self.list_url, {'title': ''}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title is required.')

    # ------------------------------------------------------------------
    # Update / lifecycle / delete
    # ------------------------------------------------------------------
    def test_update_uses_put(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.put',
                return_value=_fake_response({'message': "Job 'Updated' updated."}),
            ) as mocked_put:
                response = self.client.post(self.detail_url, {
                    'action': 'update',
                    'status': 'ALL',
                    'title': 'Updated',
                    'location': 'Sydney NSW',
                    'description': 'Updated description.',
                }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'updated')
        args, kwargs = mocked_put.call_args
        self.assertEqual(args[0], f'{TEST_BASE_URL}/api/admin/jobs/{JOB_ID}/')
        self.assertEqual(kwargs['json']['title'], 'Updated')

    def test_pause_uses_action_post(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.post',
                return_value=_fake_response({'message': "Job 'X' paused."}),
            ) as mocked_post:
                response = self.client.post(self.detail_url, {
                    'action': 'pause', 'status': 'ALL',
                }, follow=True)

        self.assertEqual(response.status_code, 200)
        args, kwargs = mocked_post.call_args
        self.assertEqual(args[0], f'{TEST_BASE_URL}/api/admin/jobs/{JOB_ID}/')
        self.assertEqual(kwargs['json'], {'action': 'pause'})

    def test_delete_uses_delete(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.delete',
                return_value=_fake_response({'message': "Job 'X' deleted."}),
            ) as mocked_delete:
                response = self.client.post(self.detail_url, {
                    'action': 'delete', 'status': 'ALL',
                }, follow=True)

        self.assertEqual(response.status_code, 200)
        args, _ = mocked_delete.call_args
        self.assertEqual(args[0], f'{TEST_BASE_URL}/api/admin/jobs/{JOB_ID}/')

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------
    def test_only_admins_can_access(self):
        # Anonymous
        self.assertIn(self.client.get(self.list_url).status_code, (302, 403))

        # Recruiter
        self.client.force_login(self.recruiter)
        with self._configured():
            with mock.patch('requests.get') as mocked_get:
                response = self.client.get(self.list_url)
        self.assertIn(response.status_code, (302, 403))
        mocked_get.assert_not_called()

    # ------------------------------------------------------------------
    # Error handling / secret safety
    # ------------------------------------------------------------------
    def test_api_unavailable_shows_message(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', side_effect=requests.exceptions.ConnectionError()
            ):
                response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API unavailable')

    def test_api_auth_error_shows_message_and_hides_secret(self):
        secret = 'tv-super-secret-9f3c1d-never-log-me'
        self.client.force_login(self.admin)
        with self._configured(api_key=secret):
            with mock.patch('apps.core.views.logger') as mocked_logger:
                with mock.patch('requests.get', return_value=_fake_response(status_code=401)):
                    response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'authentication failed')
        self.assertNotIn(secret, response.content.decode('utf-8'))
        self.assertNotIn(secret, str(mocked_logger.call_args_list))
