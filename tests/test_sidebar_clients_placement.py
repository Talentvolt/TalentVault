import pytest
from django.urls import reverse
from apps.accounts.models import User

@pytest.mark.django_db
def test_clients_sidebar_item_in_recruitment_section(client):
    admin = User.objects.create_superuser(
        email='admin_sidebar@company.com',
        password='Password123!',
        role=User.Role.SUPER_ADMIN,
        is_staff=True,
        is_superuser=True
    )
    client.force_login(admin)
    url = reverse('frontend:admin_recruiter_approvals')
    res = client.get(url)
    assert res.status_code == 200

    html = res.content.decode('utf-8')
    recruitment_idx = html.find('RECRUITMENT')
    analytics_idx = html.find('ANALYTICS')

    assert recruitment_idx != -1
    assert analytics_idx != -1
    assert recruitment_idx < analytics_idx

    recruitment_section = html[recruitment_idx:analytics_idx]

    candidates_pos = recruitment_section.find('Candidates')
    jobs_pos = recruitment_section.find('Jobs')
    clients_pos = recruitment_section.find('Clients')
    talent_pool_pos = recruitment_section.find('Talent Pool')
    pipeline_pos = recruitment_section.find('Pipeline')
    interviews_pos = recruitment_section.find('Interviews')

    assert candidates_pos != -1
    assert jobs_pos != -1
    assert clients_pos != -1
    assert talent_pool_pos != -1
    assert pipeline_pos != -1
    assert interviews_pos != -1

    assert candidates_pos < jobs_pos < clients_pos < talent_pool_pos < pipeline_pos < interviews_pos
