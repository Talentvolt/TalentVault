import json

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.candidates.models import CandidateProfile


@pytest.fixture
def permission_data(db):
    # Admin portal user without a company affiliation (typical Admin-imported owner)
    admin = User.objects.create_superuser(
        email='admin_candidate_perm@talentvault.in',
        password='Password123!',
        role=User.Role.SUPER_ADMIN,
    )

    company = Company.objects.create(
        name='Permission Recruiters Co',
        slug='permission-recruiters-co',
        industry='Recruiting',
        location='India',
    )
    recruiter = User.objects.create_user(
        email='recruiter_candidate_perm@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.ACTIVE,
    )
    CompanyMember.objects.create(user=recruiter, company=company, designation='Recruiter')

    admin_candidate_user = User.objects.create_user(
        email='admin_owned_candidate@example.com', role=User.Role.CANDIDATE
    )
    admin_candidate = CandidateProfile.objects.create(
        user=admin_candidate_user,
        full_name='Admin Owned Candidate',
        location='Delhi',
        uploaded_by=admin,
        created_by=admin,
    )

    recruiter_candidate_user = User.objects.create_user(
        email='recruiter_owned_candidate@example.com', role=User.Role.CANDIDATE
    )
    recruiter_candidate = CandidateProfile.objects.create(
        user=recruiter_candidate_user,
        full_name='Recruiter Owned Candidate',
        location='Mumbai',
        uploaded_by=recruiter,
        created_by=recruiter,
    )

    return {
        'admin': admin,
        'recruiter': recruiter,
        'admin_candidate': admin_candidate,
        'recruiter_candidate': recruiter_candidate,
    }


def _detail_html(client, candidate):
    response = client.get(reverse('frontend:candidate_detail', kwargs={'pk': candidate.pk}))
    assert response.status_code == 200
    return response.content.decode('utf-8')


# ---------------------------------------------------------------------------
# Scenario A: Admin-created candidate viewed by an External Recruiter
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_scenario_a_recruiter_sees_only_view_profile(permission_data):
    client = Client()
    client.force_login(permission_data['recruiter'])
    html = _detail_html(client, permission_data['admin_candidate'])

    # View control present
    assert 'data-bs-target="#shareProfileModal"' in html
    # Edit / Structured Editor / Delete controls hidden
    assert 'data-bs-target="#editResumeJSONModal"' not in html
    assert reverse('frontend:candidate_edit', kwargs={'pk': permission_data['admin_candidate'].pk}) not in html
    assert 'data-bs-target="#deleteCandidateModal"' not in html


# ---------------------------------------------------------------------------
# Scenario B: External Recruiter's own candidate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_scenario_b_recruiter_own_candidate_can_edit_but_not_delete(permission_data):
    client = Client()
    client.force_login(permission_data['recruiter'])
    html = _detail_html(client, permission_data['recruiter_candidate'])

    assert 'data-bs-target="#editResumeJSONModal"' in html
    assert reverse('frontend:candidate_edit', kwargs={'pk': permission_data['recruiter_candidate'].pk}) in html
    assert 'data-bs-target="#deleteCandidateModal"' not in html

    # Edit Profile page accessible
    edit_response = client.get(
        reverse('frontend:candidate_edit', kwargs={'pk': permission_data['recruiter_candidate'].pk})
    )
    assert edit_response.status_code == 200

    # Structured editor save works for own candidate
    payload = {
        'personal_info': {'name': 'Recruiter Updated Name', 'location': 'Pune'},
        'summary': 'Updated by owner recruiter',
        'skills': ['Python'],
        'experience': [],
        'education': [],
        'projects': [],
        'certifications': [],
    }
    save_response = client.post(
        reverse('frontend:candidate_edit_json', kwargs={'pk': permission_data['recruiter_candidate'].pk}),
        data=json.dumps(payload),
        content_type='application/json',
    )
    assert save_response.status_code == 200
    permission_data['recruiter_candidate'].refresh_from_db()
    assert permission_data['recruiter_candidate'].full_name == 'Recruiter Updated Name'


# ---------------------------------------------------------------------------
# Scenario C: Direct URL / POST bypass attempts on Admin-owned candidate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_scenario_c_recruiter_direct_url_bypass_blocked(permission_data):
    client = Client()
    client.force_login(permission_data['recruiter'])
    admin_candidate = permission_data['admin_candidate']

    # Edit Profile page -> 404
    assert client.get(
        reverse('frontend:candidate_edit', kwargs={'pk': admin_candidate.pk})
    ).status_code == 404

    # Structured Editor save -> 404
    assert client.post(
        reverse('frontend:candidate_edit_json', kwargs={'pk': admin_candidate.pk}),
        data=json.dumps({'personal_info': {'name': 'Hacked'}}),
        content_type='application/json',
    ).status_code == 404

    # Delete -> 403
    assert client.post(
        reverse('frontend:candidate_delete', kwargs={'id': admin_candidate.pk})
    ).status_code == 403

    # Version rollback -> 404
    assert client.post(
        reverse('frontend:candidate_rollback', kwargs={'pk': admin_candidate.pk}),
        data={'version_id': '1'},
    ).status_code == 404

    # AI Assist -> 404
    assert client.post(
        reverse('frontend:candidate_ai_improve', kwargs={'pk': admin_candidate.pk}),
        data={'action': 'preview'},
    ).status_code == 404

    # Candidate must remain untouched
    admin_candidate.refresh_from_db()
    assert admin_candidate.full_name == 'Admin Owned Candidate'


@pytest.mark.django_db
def test_recruiter_can_never_delete_even_own_candidate(permission_data):
    client = Client()
    client.force_login(permission_data['recruiter'])
    candidate = permission_data['recruiter_candidate']

    response = client.post(reverse('frontend:candidate_delete', kwargs={'id': candidate.pk}))
    assert response.status_code == 403
    assert CandidateProfile.objects.filter(id=candidate.pk).exists()


# ---------------------------------------------------------------------------
# Scenario D: Admin behavior unchanged
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_scenario_d_admin_keeps_full_candidate_permissions(permission_data):
    client = Client()
    client.force_login(permission_data['admin'])
    candidate = permission_data['admin_candidate']
    html = _detail_html(client, candidate)

    assert 'data-bs-target="#editResumeJSONModal"' in html
    assert reverse('frontend:candidate_edit', kwargs={'pk': candidate.pk}) in html
    assert 'data-bs-target="#deleteCandidateModal"' in html

    # Admin can open Edit Profile and save via Structured Editor
    assert client.get(reverse('frontend:candidate_edit', kwargs={'pk': candidate.pk})).status_code == 200
    assert client.post(
        reverse('frontend:candidate_edit_json', kwargs={'pk': candidate.pk}),
        data=json.dumps({'personal_info': {'name': 'Admin Updated'}, 'skills': []}),
        content_type='application/json',
    ).status_code == 200


@pytest.mark.django_db
def test_scenario_d_admin_can_delete_candidate(permission_data):
    client = Client()
    client.force_login(permission_data['admin'])
    candidate = permission_data['admin_candidate']

    response = client.post(reverse('frontend:candidate_delete', kwargs={'id': candidate.pk}))
    assert response.status_code == 302
    assert not CandidateProfile.objects.filter(id=candidate.pk).exists()
