import pytest
from django.urls import reverse
from apps.accounts.models import User

@pytest.mark.django_db
def test_recruiter_approval_workflow_suspend_reactivate(client):
    admin = User.objects.create_superuser(
        email='admin_workflow@company.com',
        password='Password123!',
        role=User.Role.SUPER_ADMIN
    )
    recruiter = User.objects.create_user(
        email='recruiter_workflow@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.PENDING
    )

    client.force_login(admin)
    url = reverse('frontend:admin_recruiter_approvals')

    # 1. Approve Pending Recruiter
    res_approve = client.post(f"{url}?status=PENDING", {
        'user_id': str(recruiter.id),
        'action': 'approve'
    })
    assert res_approve.status_code == 302
    recruiter.refresh_from_db()
    assert recruiter.recruiter_status == User.RecruiterStatus.ACTIVE

    # Check ACTIVE filter view
    res_active = client.get(f"{url}?status=ACTIVE")
    assert res_active.status_code == 200
    assert any(r['user'].id == recruiter.id for r in res_active.context['recruiters'])

    # 2. Suspend Active Recruiter
    res_suspend = client.post(f"{url}?status=ACTIVE", {
        'user_id': str(recruiter.id),
        'action': 'suspend'
    })
    assert res_suspend.status_code == 302
    recruiter.refresh_from_db()
    assert recruiter.recruiter_status == User.RecruiterStatus.SUSPENDED

    # Check ACTIVE filter view (recruiter removed from Active)
    res_active_after = client.get(f"{url}?status=ACTIVE")
    assert not any(r['user'].id == recruiter.id for r in res_active_after.context['recruiters'])

    # Check SUSPENDED filter view (recruiter appears in Suspended)
    res_suspended = client.get(f"{url}?status=SUSPENDED")
    assert res_suspended.status_code == 200
    assert any(r['user'].id == recruiter.id for r in res_suspended.context['recruiters'])

    # 3. Reactivate Suspended Recruiter
    res_reactivate = client.post(f"{url}?status=SUSPENDED", {
        'user_id': str(recruiter.id),
        'action': 'reactivate'
    })
    assert res_reactivate.status_code == 302
    recruiter.refresh_from_db()
    assert recruiter.recruiter_status == User.RecruiterStatus.ACTIVE

    # Check SUSPENDED filter view (recruiter moved back to Active)
    res_suspended_after = client.get(f"{url}?status=SUSPENDED")
    assert not any(r['user'].id == recruiter.id for r in res_suspended_after.context['recruiters'])

    res_active_final = client.get(f"{url}?status=ACTIVE")
    assert any(r['user'].id == recruiter.id for r in res_active_final.context['recruiters'])

@pytest.mark.django_db
def test_suspended_recruiter_login_blocked(client):
    recruiter = User.objects.create_user(
        email='suspended_recruiter@company.com',
        password='Password123!',
        role=User.Role.RECRUITER,
        recruiter_status=User.RecruiterStatus.SUSPENDED,
        is_active=False
    )
    login_url = reverse('employer_login')
    res = client.post(login_url, {
        'email': recruiter.email,
        'password': 'Password123!'
    })
    assert res.status_code == 200
    assert "Your recruiter account has been suspended. Please contact the administrator." in res.content.decode('utf-8')
