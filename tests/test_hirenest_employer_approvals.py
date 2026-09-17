"""
TalentVault Admin Portal — HireNest Australia employer approvals integration.

These tests verify the admin-only proxy view. The view never touches the
HireNest database directly; it calls the HireNest admin API, so the HTTP calls
are mocked here. No real secret is used anywhere in this file.
"""
from unittest import mock

import requests
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


URL_NAME = 'frontend:admin_hirenest_employer_approvals'
TEST_BASE_URL = 'https://hirenest.example'
# Clearly fake value used only by the tests. Not a production secret.
TEST_API_KEY = 'tv-test-key-not-a-real-secret'

EMPLOYER = {
    'id': '11111111-1111-1111-1111-111111111111',
    'company_name': 'Aussie Co Pty Ltd',
    'contact_name': 'Alex Recruiter',
    'email': 'hr@aussieco.com',
    'phone': '+61 2 9000 0000',
    'industry': 'Technology',
    'location': 'Sydney NSW',
    'website': 'https://aussieco.com',
    'status': 'PENDING',
    'registration_date': '2026-01-01T00:00:00+00:00',
}


def _fake_response(payload=None, status_code=200, text=''):
    response = mock.Mock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = payload if payload is not None else {'employers': []}
    response.raise_for_status.return_value = None
    return response


class HireNestEmployerApprovalsTests(TestCase):
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
        self.url = reverse(URL_NAME)

    def _configured(self, api_key=TEST_API_KEY):
        return self.settings(
            HIRENEST_API_BASE_URL=TEST_BASE_URL,
            HIRENEST_ADMIN_API_KEY=api_key,
        )

    # ------------------------------------------------------------------
    # 1 & 2. Missing configuration
    # ------------------------------------------------------------------

    def test_missing_base_url_shows_configuration_warning(self):
        self.client.force_login(self.admin)
        with self.settings(HIRENEST_API_BASE_URL='', HIRENEST_ADMIN_API_KEY=TEST_API_KEY):
            with mock.patch('requests.get') as mocked_get:
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not configured')
        self.assertContains(response, 'HIRENEST_API_BASE_URL')
        mocked_get.assert_not_called()

    def test_missing_api_key_shows_configuration_warning(self):
        self.client.force_login(self.admin)
        with self.settings(HIRENEST_API_BASE_URL=TEST_BASE_URL, HIRENEST_ADMIN_API_KEY=''):
            with mock.patch('requests.get') as mocked_get:
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not configured')
        self.assertContains(response, 'HIRENEST_ADMIN_API_KEY')
        mocked_get.assert_not_called()

    # ------------------------------------------------------------------
    # 3 & 4. Correct configuration / base URL
    # ------------------------------------------------------------------

    def test_correct_configuration_renders_without_warning(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch('requests.get', return_value=_fake_response({'employers': []})):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'not configured')

    def test_uses_configured_api_base_url_and_endpoint(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', return_value=_fake_response({'employers': [EMPLOYER]})
            ) as mocked_get:
                self.client.get(self.url)

        args, _ = mocked_get.call_args
        called_url = args[0] if args else ''
        self.assertTrue(
            called_url.startswith(f'{TEST_BASE_URL}/api/admin/employer-approvals/')
        )
        self.assertIn('status=PENDING', called_url)
        # The secret must never be placed in the URL.
        self.assertNotIn(TEST_API_KEY, called_url)

    # ------------------------------------------------------------------
    # 5. Correct authentication header
    # ------------------------------------------------------------------

    def test_sends_hirenest_admin_key_header(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', return_value=_fake_response({'employers': [EMPLOYER]})
            ) as mocked_get:
                self.client.get(self.url)

        _, kwargs = mocked_get.call_args
        self.assertEqual(kwargs['headers']['X-HireNest-Admin-Key'], TEST_API_KEY)
        self.assertEqual(kwargs['headers']['Accept'], 'application/json')

    # ------------------------------------------------------------------
    # 6 & 7. Admin-only access
    # ------------------------------------------------------------------

    def test_super_admin_can_access(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch('requests.get', return_value=_fake_response({'employers': []})):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'HireNest Australia Approvals')

    def test_normal_recruiter_is_denied(self):
        self.client.force_login(self.recruiter)
        with self._configured():
            with mock.patch('requests.get') as mocked_get:
                response = self.client.get(self.url)

        self.assertIn(response.status_code, (302, 403))
        mocked_get.assert_not_called()

    def test_anonymous_user_is_denied(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 403))

    # ------------------------------------------------------------------
    # 8. Successful GET pending employers
    # ------------------------------------------------------------------

    def test_successful_get_pending_employers(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', return_value=_fake_response({'employers': [EMPLOYER]})
            ):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Aussie Co Pty Ltd')
        self.assertContains(response, 'Alex Recruiter')

    # ------------------------------------------------------------------
    # 9 & 10. Successful approve / reject
    # ------------------------------------------------------------------

    def test_successful_approve(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.post',
                return_value=_fake_response({'message': 'Employer approved.'}),
            ) as mocked_post, mock.patch(
                'requests.get', return_value=_fake_response({'employers': []})
            ):
                response = self.client.post(
                    self.url,
                    {'user_id': EMPLOYER['id'], 'action': 'approve', 'status': 'PENDING'},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Employer approved.')
        args, kwargs = mocked_post.call_args
        self.assertTrue(
            args[0].endswith(f"/api/admin/employer-approvals/{EMPLOYER['id']}/")
        )
        self.assertEqual(kwargs['json'], {'action': 'approve'})
        self.assertEqual(kwargs['headers']['X-HireNest-Admin-Key'], TEST_API_KEY)

    def test_successful_reject(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.post',
                return_value=_fake_response({'message': 'Employer rejected.'}),
            ) as mocked_post, mock.patch(
                'requests.get', return_value=_fake_response({'employers': []})
            ):
                response = self.client.post(
                    self.url,
                    {'user_id': EMPLOYER['id'], 'action': 'reject', 'status': 'PENDING'},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Employer rejected.')
        _, kwargs = mocked_post.call_args
        self.assertEqual(kwargs['json'], {'action': 'reject'})

    # ------------------------------------------------------------------
    # 11. API unauthorized (401/403)
    # ------------------------------------------------------------------

    def test_api_unauthorized_on_get_shows_auth_error(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch('requests.get', return_value=_fake_response(status_code=401)):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'authentication failed')

    def test_api_forbidden_on_get_shows_auth_error(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch('requests.get', return_value=_fake_response(status_code=403)):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'authentication failed')

    def test_api_unauthorized_on_post_shows_auth_error(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.post', return_value=_fake_response(status_code=401)
            ), mock.patch('requests.get', return_value=_fake_response({'employers': []})):
                response = self.client.post(
                    self.url,
                    {'user_id': EMPLOYER['id'], 'action': 'approve', 'status': 'PENDING'},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'authentication failed')

    # ------------------------------------------------------------------
    # 12. API unavailable
    # ------------------------------------------------------------------

    def test_api_unavailable_on_get_shows_unavailable_message(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.get', side_effect=requests.exceptions.ConnectionError()
            ):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API unavailable')

    def test_api_timeout_on_get_shows_unavailable_message(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch('requests.get', side_effect=requests.exceptions.Timeout()):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API unavailable')

    def test_api_unavailable_on_post_shows_unavailable_message(self):
        self.client.force_login(self.admin)
        with self._configured():
            with mock.patch(
                'requests.post', side_effect=requests.exceptions.ConnectionError()
            ), mock.patch('requests.get', return_value=_fake_response({'employers': []})):
                response = self.client.post(
                    self.url,
                    {'user_id': EMPLOYER['id'], 'action': 'approve', 'status': 'PENDING'},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API unavailable')

    # ------------------------------------------------------------------
    # 13. Secret never leaks into responses or logs
    # ------------------------------------------------------------------

    def test_secret_never_appears_in_response_or_logs(self):
        secret = 'tv-super-secret-9f3c1d-never-log-me'
        self.client.force_login(self.admin)
        with self._configured(api_key=secret):
            with mock.patch('apps.core.views.logger') as mocked_logger:
                with mock.patch(
                    'requests.get', return_value=_fake_response({'employers': [EMPLOYER]})
                ):
                    response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(secret, response.content.decode('utf-8'))
        self.assertNotIn(secret, str(mocked_logger.call_args_list))

    def test_secret_never_appears_when_api_rejects_credentials(self):
        secret = 'tv-super-secret-9f3c1d-never-log-me'
        self.client.force_login(self.admin)
        with self._configured(api_key=secret):
            with mock.patch('apps.core.views.logger') as mocked_logger:
                with mock.patch('requests.get', return_value=_fake_response(status_code=401)):
                    response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(secret, response.content.decode('utf-8'))
        self.assertNotIn(secret, str(mocked_logger.call_args_list))
        self.assertTrue(mocked_logger.error.called)
