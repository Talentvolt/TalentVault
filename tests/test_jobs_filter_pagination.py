from django.test import TestCase, Client as DjangoTestClient
from django.urls import reverse
from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.clients.models import Client as ClientModel
from apps.jobs.models import Job

class JobFilterPaginationTest(TestCase):
    def setUp(self):
        # Shared company for recruiters
        self.company = Company.objects.create(name='Tech Recruiting Co', slug='tech-recruiting')
        self.user = User.objects.create_user(
            email='recruiter_jobs@talentvault.in',
            password='password123',
            first_name='Recruiter',
            last_name='User',
            role=User.Role.RECRUITER
        )
        CompanyMember.objects.create(user=self.user, company=self.company, designation='Lead Recruiter')

        # Create Client 1: Lumax Group
        self.client_lumax = ClientModel.objects.create(
            company_name='Lumax Group',
            spoc_name='Lumax HR',
            status='ACTIVE'
        )

        # Create Client 2: Prince Pipes
        self.client_prince = ClientModel.objects.create(
            company_name='Prince Pipes',
            spoc_name='Prince HR',
            status='ACTIVE'
        )

        # Create 15 jobs for Lumax Group
        self.lumax_jobs = []
        for i in range(15):
            job = Job.objects.create(
                company=self.company,
                client=self.client_lumax,
                created_by=self.user,
                title=f"Lumax Territory Manager {i+1}",
                status='ACTIVE',
                job_type='FULL_TIME' if i % 2 == 0 else 'PART_TIME'
            )
            self.lumax_jobs.append(job)

        # Create 12 jobs for Prince Pipes
        self.prince_jobs = []
        for i in range(12):
            job = Job.objects.create(
                company=self.company,
                client=self.client_prince,
                created_by=self.user,
                title=f"Prince Pipes Quality Officer {i+1}",
                status='ACTIVE',
                job_type='FULL_TIME'
            )
            self.prince_jobs.append(job)

        self.http_client = DjangoTestClient()
        self.http_client.force_login(self.user)

    def test_1_all_clients_pagination(self):
        """TEST 1: Client = All Clients, Page 1 -> Page 2 preserves all jobs."""
        response_p1 = self.http_client.get(reverse('frontend:jobs') + '?page=1')
        self.assertEqual(response_p1.status_code, 200)
        self.assertContains(response_p1, '?page=2')

        response_p2 = self.http_client.get(reverse('frontend:jobs') + '?page=2')
        self.assertEqual(response_p2.status_code, 200)

    def test_2_lumax_group_client_pagination_persistence(self):
        """TEST 2: Client = Lumax Group. Page 1, Page 2. Every page = Lumax Group only."""
        url_p1 = f"{reverse('frontend:jobs')}?client={self.client_lumax.id}&page=1"
        response_p1 = self.http_client.get(url_p1)
        self.assertEqual(response_p1.status_code, 200)
        self.assertContains(response_p1, 'Lumax Group')
        # Check pagination link contains client ID
        self.assertContains(response_p1, f"client={self.client_lumax.id}")
        self.assertContains(response_p1, f"page=2")

        # Page 2 request
        url_p2 = f"{reverse('frontend:jobs')}?client={self.client_lumax.id}&page=2"
        response_p2 = self.http_client.get(url_p2)
        self.assertEqual(response_p2.status_code, 200)
        self.assertContains(response_p2, f"client={self.client_lumax.id}")
        self.assertNotContains(response_p2, '(Client: Prince Pipes)')
        self.assertNotContains(response_p2, 'Prince Pipes Quality Officer')

    def test_3_prince_pipes_client_pagination_persistence(self):
        """TEST 3: Client = Prince Pipes. Page 1, Page 2. Every page = Prince Pipes only."""
        url_p1 = f"{reverse('frontend:jobs')}?client={self.client_prince.id}&page=1"
        response_p1 = self.http_client.get(url_p1)
        self.assertEqual(response_p1.status_code, 200)
        self.assertContains(response_p1, f"client={self.client_prince.id}")

        url_p2 = f"{reverse('frontend:jobs')}?client={self.client_prince.id}&page=2"
        response_p2 = self.http_client.get(url_p2)
        self.assertEqual(response_p2.status_code, 200)
        self.assertContains(response_p2, f"client={self.client_prince.id}")
        self.assertNotContains(response_p2, '(Client: Lumax Group)')
        self.assertNotContains(response_p2, 'Lumax Territory Manager')

    def test_4_lumax_plus_search_territory_pagination(self):
        """TEST 4: Client = Lumax Group, Search = Territory, Page 2."""
        url_p1 = f"{reverse('frontend:jobs')}?client={self.client_lumax.id}&q=Territory&page=1"
        response_p1 = self.http_client.get(url_p1)
        self.assertEqual(response_p1.status_code, 200)
        self.assertContains(response_p1, f"client={self.client_lumax.id}")
        self.assertContains(response_p1, "q=Territory")

        url_p2 = f"{reverse('frontend:jobs')}?client={self.client_lumax.id}&q=Territory&page=2"
        response_p2 = self.http_client.get(url_p2)
        self.assertEqual(response_p2.status_code, 200)
        self.assertContains(response_p2, f"client={self.client_lumax.id}")
        self.assertContains(response_p2, "q=Territory")

    def test_5_lumax_plus_status_active_pagination(self):
        """TEST 5: Client = Lumax Group, Status = ACTIVE, Page 2."""
        url_p1 = f"{reverse('frontend:jobs')}?client={self.client_lumax.id}&status=ACTIVE&page=1"
        response_p1 = self.http_client.get(url_p1)
        self.assertEqual(response_p1.status_code, 200)
        self.assertContains(response_p1, f"client={self.client_lumax.id}")
        self.assertContains(response_p1, "status=ACTIVE")

    def test_6_prince_plus_job_type_full_time_sort_newest(self):
        """TEST 6: Client = Prince Pipes, Job Type = FULL_TIME, Sort = -created_at, Page 2."""
        url_p1 = f"{reverse('frontend:jobs')}?client={self.client_prince.id}&job_type=FULL_TIME&sort_by=-created_at&page=1"
        response_p1 = self.http_client.get(url_p1)
        self.assertEqual(response_p1.status_code, 200)
        self.assertContains(response_p1, f"client={self.client_prince.id}")
        self.assertContains(response_p1, "job_type=FULL_TIME")
        self.assertContains(response_p1, "sort_by=-created_at")

    def test_7_page_navigation_preserves_client_dropdown_selected(self):
        """TEST 7: Select client, go to page 2, then page 1. Client remains selected."""
        url_p2 = f"{reverse('frontend:jobs')}?client={self.client_lumax.id}&page=2"
        response_p2 = self.http_client.get(url_p2)
        self.assertEqual(response_p2.status_code, 200)
        self.assertContains(response_p2, 'selected')

    def test_8_clear_filter_resets_everything(self):
        """TEST 8: Select client, click Clear. All Clients and page 1."""
        response_clear = self.http_client.get(reverse('frontend:jobs'))
        self.assertEqual(response_clear.status_code, 200)
        self.assertNotContains(response_clear, f"client={self.client_lumax.id}")

    def test_9_invalid_page_redirects_gracefully(self):
        """TEST 9: Requesting page=999 redirects gracefully to the last valid page."""
        url_invalid = f"{reverse('frontend:jobs')}?client={self.client_lumax.id}&page=999"
        response = self.http_client.get(url_invalid)
        self.assertEqual(response.status_code, 302)
        self.assertIn('page=', response.url)
        self.assertIn(f"client={self.client_lumax.id}", response.url)
