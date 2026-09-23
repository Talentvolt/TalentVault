import pytest
from django.urls import reverse
from apps.accounts.models import User

@pytest.mark.django_db
def test_saas_recruiter_sidebar_structure_and_items(client):
    # Create a super admin user to test the master sidebar
    admin = User.objects.create_superuser(
        email='saas_admin@talentvault.com',
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

    # 1. Existing TalentVault Logo
    assert 'static/images/logo/talentvault-logo.png' in html or 'talentvault-logo' in html
    assert 'Recruiter Workspace' in html
    assert 'Enterprise ATS Platform' in html

    # 2. Main Section
    assert 'MAIN' in html
    assert 'Dashboard' in html
    assert 'TalentVault Recruiters' in html
    assert 'HireNest Australia Employers' in html
    assert 'HireNest Australia Jobs' in html

    # 3. Recruitment Section
    assert 'RECRUITMENT' in html
    assert 'Candidates' in html
    assert 'Jobs' in html
    assert 'Clients' in html
    assert 'Talent Pool' in html
    assert 'Pipeline' in html
    assert 'Interviews' in html

    # Verify Recruitment Section Order
    recruitment_idx = html.find('RECRUITMENT')
    talent_intel_idx = html.find('TALENT INTELLIGENCE')
    assert recruitment_idx != -1
    assert talent_intel_idx != -1
    assert recruitment_idx < talent_intel_idx

    recruitment_section = html[recruitment_idx:talent_intel_idx]
    pos_cand = recruitment_section.find('Candidates')
    pos_jobs = recruitment_section.find('Jobs')
    pos_clients = recruitment_section.find('Clients')
    pos_pool = recruitment_section.find('Talent Pool')
    pos_pipeline = recruitment_section.find('Pipeline')
    pos_interviews = recruitment_section.find('Interviews')

    assert pos_cand < pos_jobs < pos_clients < pos_pool < pos_pipeline < pos_interviews

    # 4. Talent Intelligence Section
    assert 'Talent Search' in html
    assert 'Taxonomy' in html

    # 5. Analytics Section
    assert 'ANALYTICS' in html
    assert 'Campaigns' in html
    assert 'Resume Parser' in html
    assert 'Analytics' in html

    # 6. Settings Section
    assert 'SETTINGS' in html
    assert 'Users' in html
    assert 'Settings' in html

    # 7. Bottom User Area
    assert 'saas_admin@talentvault.com' in html
    assert 'Logout' in html
    assert 'sidebar-footer' in html

@pytest.mark.django_db
def test_saas_recruiter_sidebar_for_recruiter_role(client):
    # Test standard recruiter user
    recruiter = User.objects.create_user(
        email='saas_recruiter@talentvault.com',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    client.force_login(recruiter)
    url = reverse('frontend:recruiter_dashboard')
    res = client.get(url)
    assert res.status_code == 200

    html = res.content.decode('utf-8')

    # Brand header & badge
    assert 'talentvault-logo' in html
    assert 'Recruiter Workspace' in html
    assert 'Enterprise ATS Platform' in html

    # Navigation items present
    assert 'Dashboard' in html
    assert 'Candidates' in html
    assert 'Jobs' in html
    assert 'Clients' in html
    assert 'Talent Pool' in html
    assert 'Pipeline' in html
    assert 'Interviews' in html
    assert 'Talent Search' in html
    assert 'Campaigns' in html
    assert 'Resume Parser' in html
    assert 'Analytics' in html
    assert 'Settings' in html

    # User footer
    assert 'saas_recruiter@talentvault.com' in html
    assert 'Logout' in html
