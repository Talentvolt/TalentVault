from django.test import TestCase
from django.urls import reverse


class PrivacyPolicyPageTest(TestCase):
    def test_privacy_policy_returns_200_without_login(self):
        response = self.client.get('/privacy-policy/')
        self.assertEqual(response.status_code, 200)

    def test_privacy_policy_by_name_returns_200_without_login(self):
        response = self.client.get(reverse('frontend:privacy_policy'))
        self.assertEqual(response.status_code, 200)

    def test_privacy_policy_renders_full_policy_content(self):
        response = self.client.get('/privacy-policy/')
        content = response.content.decode('utf-8')

        for phrase in (
            'Privacy Policy',
            'TalentVault Candidate Importer',
            'Extract Candidate Data',
            'candidates/import',
            'enrichment/person',
            'chrome.storage.local',
            'LinkedIn',
            'Naukri',
            'https://talent-vault.in',
            'Chrome Web Store User Data Policy',
            'Limited Use',
            'Deletion requests',
        ):
            self.assertIn(phrase, content, f'Missing "{phrase}" in privacy policy page')

    def test_privacy_policy_link_in_footer(self):
        response = self.client.get(reverse('frontend:dashboard'))
        content = response.content.decode('utf-8')
        self.assertIn('/privacy-policy/', content)
