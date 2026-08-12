from django.test import TestCase, Client as DjangoTestClient
from django.urls import reverse
from apps.accounts.models import User
from apps.clients.models import Client

class ClientPaginationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            email='admin_test_pag@example.com',
            password='password123'
        )
        self.client = DjangoTestClient()
        self.client.force_login(self.user)

        # Create 15 test clients to produce 2 pages (paginate_by = 10)
        for i in range(15):
            Client.objects.create(
                company_name=f"Test Client Company {i+1:02d}",
                spoc_name=f"SPOC {i+1}",
                email=f"spoc{i+1}@test.com",
                industry="IT_SERVICES",
                created_by=self.user
            )

    def test_valid_page_1(self):
        response = self.client.get(reverse('clients:client_list') + '?page=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['clients']), 10)
        self.assertEqual(response.context['paginator'].num_pages, 2)
        self.assertEqual(response.context['page_obj'].number, 1)

    def test_valid_page_2(self):
        response = self.client.get(reverse('clients:client_list') + '?page=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['clients']), 5)
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_out_of_bounds_page_overflow(self):
        # Page 999 should redirect to page 2 (the last valid page)
        response = self.client.get(reverse('clients:client_list') + '?page=999', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_invalid_page_string(self):
        # Invalid string page parameter should redirect to page 1
        response = self.client.get(reverse('clients:client_list') + '?page=abc', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 1)

    def test_search_and_pagination_filter_preservation(self):
        # Filter for Company 01 to 05 (5 results -> 1 page)
        response = self.client.get(reverse('clients:client_list') + '?company_name=Test Client Company 0&page=999', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 1)
        self.assertIn('&company_name=Test+Client+Company+0', response.context['filter_params'])
