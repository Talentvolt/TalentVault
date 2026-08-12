from django.test import TestCase, Client as DjangoTestClient
from django.urls import reverse
from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.clients.models import Client

class ClientCreatedByTest(TestCase):
    def setUp(self):
        # Create a shared company for multi-tenant recruiters
        self.company = Company.objects.create(name='Acme Recruiting Agency', slug='acme-recruiting')

        # Create User A (Roshni)
        self.user_roshni = User.objects.create_user(
            email='roshni@talentvault.in',
            password='password123',
            first_name='Roshni',
            last_name='HR',
            role=User.Role.RECRUITER
        )
        CompanyMember.objects.create(user=self.user_roshni, company=self.company, designation='Senior Recruiter')

        # Create User B (Rahul)
        self.user_rahul = User.objects.create_user(
            email='rahul@talentvault.in',
            password='password123',
            first_name='Rahul',
            last_name='Recruiter',
            role=User.Role.RECRUITER
        )
        CompanyMember.objects.create(user=self.user_rahul, company=self.company, designation='Recruiter')

        self.client_roshni = DjangoTestClient()
        self.client_rahul = DjangoTestClient()

    def test_1_client_creation_captures_roshni(self):
        """TEST 1: Login as Roshni and create Client A. Verify Created By = Roshni."""
        self.client_roshni.force_login(self.user_roshni)
        response = self.client_roshni.post(reverse('clients:client_create'), {
            'company_name': 'Tech Mahindra Test A',
            'spoc_name': 'Roshni SPOC',
            'email': 'hr@techmahindra.com',
            'industry': 'IT_SERVICES',
            'company_size': '500+',
            'status': 'ACTIVE'
        })
        self.assertEqual(response.status_code, 302)

        client_a = Client.objects.get(company_name='Tech Mahindra Test A')
        self.assertEqual(client_a.created_by, self.user_roshni)
        self.assertEqual(client_a.created_by_display, 'Roshni HR')

    def test_2_client_creation_captures_rahul(self):
        """TEST 2: Login as User B (Rahul) and create Client B. Verify Created By = Rahul."""
        self.client_rahul.force_login(self.user_rahul)
        response = self.client_rahul.post(reverse('clients:client_create'), {
            'company_name': 'Infosys Test B',
            'spoc_name': 'Rahul SPOC',
            'email': 'hr@infosys.com',
            'industry': 'IT_SERVICES',
            'company_size': '500+',
            'status': 'ACTIVE'
        })
        self.assertEqual(response.status_code, 302)

        client_b = Client.objects.get(company_name='Infosys Test B')
        self.assertEqual(client_b.created_by, self.user_rahul)
        self.assertEqual(client_b.created_by_display, 'Rahul Recruiter')

    def test_3_client_edit_does_not_overwrite_creator(self):
        """TEST 3: Roshni creates a client. Rahul edits it. Created By must remain Roshni."""
        client = Client.objects.create(
            company_name='Original Roshni Client',
            spoc_name='Roshni',
            industry='SOFTWARE_PRODUCT',
            created_by=self.user_roshni
        )

        self.client_rahul.force_login(self.user_rahul)
        response = self.client_rahul.post(reverse('clients:client_edit', kwargs={'pk': client.pk}), {
            'company_name': 'Edited Roshni Client',
            'spoc_name': 'Updated SPOC',
            'industry': 'SOFTWARE_PRODUCT',
            'company_size': '1-50',
            'status': 'ACTIVE'
        })
        self.assertEqual(response.status_code, 302)

        client.refresh_from_db()
        self.assertEqual(client.company_name, 'Edited Roshni Client')
        self.assertEqual(client.created_by, self.user_roshni)
        self.assertEqual(client.updated_by, self.user_rahul)
        self.assertEqual(client.created_by_display, 'Roshni HR')

    def test_4_older_existing_client_without_creator(self):
        """TEST 4: Open an old existing client created before feature. Created By shows '—'."""
        old_client = Client.objects.create(
            company_name='Legacy Client Corp',
            spoc_name='Legacy SPOC',
            industry='OTHERS',
            created_by=None
        )

        self.assertEqual(old_client.created_by, None)
        self.assertEqual(old_client.created_by_display, '—')

        self.client_roshni.force_login(self.user_roshni)
        response = self.client_roshni.get(reverse('clients:client_detail', kwargs={'pk': old_client.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '—')
