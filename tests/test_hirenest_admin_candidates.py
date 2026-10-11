"""
TalentVault Admin Portal — HireNest candidates integration.

These tests verify the admin-only proxy views that list HireNest candidate
applications. The views never touch the HireNest database directly; they call
the HireNest admin API, so the HTTP calls are mocked here. No real secret is
used anywhere in this file.
"""
from unittest import mock

import requests
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


LIST_URL_NAME = 'frontend:admin_hirenest_candidates'
DETAIL_URL_NAME = 'frontend:admin_hirenest_candidate_detail'
TEST_BASE_URL = 'https://hirenest.example'
TEST_API_KEY = 'tv-test-key-not-a-real-secret'
APPLICATION_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'

CANDIDATE_APPLICATION = {
    'id': APPLICATION_ID,
    'candidate_name': 'Jane Doe',
    'email': 'jane@example.com',
    'phone': '+61 400 111 222',
    'job_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'job_title': 'Data Engineer',
    'location': 'Sydney NSW',
    'expected_salary': '150000.00',
    'expected_salary_currency': 'AUD',
    'salary_period': 'ANNUALLY',
    'expected_salary_display': 'A$150,000 / year',
    'application_date': '2026-01-01T00:00:00+00:00',
    'stage': 'OPEN',
    'status_display': 'Applied',
    'screening_answers': [
        {'question': 'Are you eligible?', 'answer': 'Yes', 'type': 'YES_NO', 'required': True}
    ],
    'cover_letter': '',
    'linkedin_url': '',
    'has_resume': True,
    'resume_url': 'https://hirenest.example/resume?sign=download',
    'resume_preview_url': 'https://hirenest.example/resume?sign=preview',
}

HIRENEST_JOB = {
    'id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'title': 'Data Engineer',
}


def _fake_response(payload=None, status_code=200, text=''):
    response = mock.Mock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = payload if payload is not None else {}
    response.raise_for_status.return_value = None
    return response


def _fake_get(url, *args, **kwargs):
    if '/api/admin/applications/' in url:
        return _fake_response({'applications': [CANDIDATE_APPLICATION]})
    if '/api/admin/jobs/' in url:
        return _fake_response({'jobs': [HIRENEST_JOB]})
    return _fake_response({})


class HireNestAdminCandidatesTests(TestCase):
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
        self.detail_url = reverse(DETAIL_URL_NAME, args=[APPLICATION_ID])

    def _configured(self, api_key=TEST_API_KEY):
        return self.settings(
            HIRENEST_API_BASE_URL=TEST_BASE_URL,
            HIRENEST_ADMIN_API_KEY=api_key,
        )

    def test_urls_reverse(self):
        self.assertEqual(self.list_url, '/dashboard/admin/hirenest-candidates/')
        self.assertEqual(
            self.detail_url,
            f'/dashboard/admin/hirenest-candidates/{APPLICATION_ID}/',
        )

    def test_missing_configuration_shows_warning_without_http_call(self):
        self.client.force_login(self.admin)
        with self.settings(HIRENEST_API_BASE_URL='', HIRENEST_ADMIN_API_KEY=TEST_API_KEY):
            with mock.patch('requests.get') as mocked_get:
                response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not configured')
        self.assertContains(response, 'HIRENEST_API_BASE_URL')
        mocked_get.assert_not_called()

    def test_list_renders_candidates_and_uses_admin_key(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch('requests.get', side_effect=_fake_get) as mocked_get:
                response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Jane Doe')
        self.assertContains(response, 'Data Engineer')

        calls = [c for c in mocked_get.call_args_list]
        apps_url = next(
            str(c.args[0]) for c in calls if '/api/admin/applications/' in str(c.args[0])
        )
        self.assertTrue(apps_url.startswith(f'{TEST_BASE_URL}/api/admin/applications/'))
        self.assertIn('status=ALL', apps_url)
        headers = next(
            c.kwargs['headers'] for c in calls if '/api/admin/applications/' in str(c.args[0])
        )
        self.assertEqual(headers['X-HireNest-Admin-Key'], TEST_API_KEY)
        self.assertNotIn(TEST_API_KEY, apps_url)

    def test_list_passes_filters_to_api(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch('requests.get', side_effect=_fake_get) as mocked_get:
                response = self.client.get(
                    self.list_url, {'status': 'INTERVIEW', 'job': HIRENEST_JOB['id'], 'q': 'Jane'}
                )

        self.assertEqual(response.status_code, 200)
        apps_url = next(
            str(c.args[0]) for c in mocked_get.call_args_list if '/api/admin/applications/' in str(c.args[0])
        )
        self.assertIn('status=INTERVIEW', apps_url)
        self.assertIn('q=Jane', apps_url)
        self.assertIn(f"job={HIRENEST_JOB['id']}", apps_url)

    def test_detail_fetches_single_application(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get',
                return_value=_fake_response({'application': CANDIDATE_APPLICATION}),
            ) as mocked_get:
                response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Jane Doe')
        self.assertContains(response, 'Are you eligible?')
        self.assertContains(response, CANDIDATE_APPLICATION['resume_url'])
        args, kwargs = mocked_get.call_args
        self.assertEqual(args[0], f'{TEST_BASE_URL}/api/admin/applications/{APPLICATION_ID}/')
        self.assertEqual(kwargs['headers']['X-HireNest-Admin-Key'], TEST_API_KEY)

    def test_empty_state(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get',
                side_effect=lambda url, *a, **k: (
                    _fake_response({'applications': []}) if '/api/admin/applications/' in url
                    else _fake_response({'jobs': []})
                ),
            ):
                response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No HireNest candidate applications found')

    def test_only_admins_can_access(self):
        self.assertIn(self.client.get(self.list_url).status_code, (302, 403))
        self.client.force_login(self.recruiter)
        with self._configured():
            with mock.patch('requests.get') as mocked_get:
                response = self.client.get(self.list_url)
        self.assertIn(response.status_code, (302, 403))
        mocked_get.assert_not_called()

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

    def test_api_unavailable_shows_message(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', side_effect=requests.exceptions.ConnectionError()
            ):
                response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API unavailable')
