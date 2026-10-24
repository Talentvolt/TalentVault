import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile


def _mk_candidate(email, full_name, uploaded_by=None, created_by=None):
    u = User.objects.create_user(email=email, role=User.Role.CANDIDATE)
    return CandidateProfile.objects.create(
        user=u,
        full_name=full_name,
        location='Test',
        uploaded_by=uploaded_by,
        created_by=created_by,
    )


@pytest.mark.django_db
def test_candidate_search_filters_by_recruiter_id():
    admin = User.objects.create_superuser(
        email='rf_admin@example.com', role=User.Role.SUPER_ADMIN
    )
    deepak = User.objects.create_user(
        email='deepak@example.com', role=User.Role.RECRUITER,
        first_name='Deepak', last_name='Kumar', recruiter_status=User.RecruiterStatus.ACTIVE,
    )
    rahul = User.objects.create_user(
        email='rahul@example.com', role=User.Role.RECRUITER,
        first_name='Rahul', last_name='Nishad', recruiter_status=User.RecruiterStatus.ACTIVE,
    )

    d1 = _mk_candidate('d1@example.com', 'Deepak One', uploaded_by=deepak, created_by=deepak)
    d2 = _mk_candidate('d2@example.com', 'Deepak Two', uploaded_by=deepak, created_by=deepak)
    r1 = _mk_candidate('r1@example.com', 'Rahul One', uploaded_by=rahul, created_by=rahul)
    u1 = _mk_candidate('u1@example.com', 'Unassigned One')

    from django.test import Client
    client = Client()
    client.force_login(admin)

    resp = client.get(reverse('frontend:candidate_search'), {'recruiter_id': str(deepak.id)})
    assert resp.status_code == 200
    returned_ids = {c.id for c in resp.context['candidates']}
    assert returned_ids == {d1.id, d2.id}

    resp_rahul = client.get(reverse('frontend:candidate_search'), {'recruiter_id': str(rahul.id)})
    assert {c.id for c in resp_rahul.context['candidates']} == {r1.id}

    resp_unassigned = client.get(reverse('frontend:candidate_search'), {'recruiter_id': 'unassigned'})
    assert {c.id for c in resp_unassigned.context['candidates']} == {u1.id}

    resp_all = client.get(reverse('frontend:candidate_search'))
    assert {c.id for c in resp_all.context['candidates']} == {d1.id, d2.id, r1.id, u1.id}


@pytest.mark.django_db
def test_candidate_search_recruiter_filter_respects_uploaded_by_over_created_by():
    admin = User.objects.create_superuser(
        email='rf_admin2@example.com', role=User.Role.SUPER_ADMIN
    )
    deepak = User.objects.create_user(
        email='deepak2@example.com', role=User.Role.RECRUITER,
        first_name='Deepak', last_name='Kumar', recruiter_status=User.RecruiterStatus.ACTIVE,
    )
    rahul = User.objects.create_user(
        email='rahul2@example.com', role=User.Role.RECRUITER,
        first_name='Rahul', last_name='Nishad', recruiter_status=User.RecruiterStatus.ACTIVE,
    )

    # Uploaded by Deepak but created by Rahul: attributed to Deepak.
    c1 = _mk_candidate('mixed1@example.com', 'Uploaded Deepak', uploaded_by=deepak, created_by=rahul)
    # Created by Deepak with no uploader: attributed to Deepak.
    c2 = _mk_candidate('mixed2@example.com', 'Created Deepak', uploaded_by=None, created_by=deepak)

    from django.test import Client
    client = Client()
    client.force_login(admin)

    resp = client.get(reverse('frontend:candidate_search'), {'recruiter_id': str(deepak.id)})
    assert {c.id for c in resp.context['candidates']} == {c1.id, c2.id}

    resp_rahul = client.get(reverse('frontend:candidate_search'), {'recruiter_id': str(rahul.id)})
    assert {c.id for c in resp_rahul.context['candidates']} == set()


@pytest.mark.django_db
def test_candidate_search_recruiter_filter_respects_date_range():
    from datetime import datetime, timedelta
    from django.utils import timezone
    from utils.date_helpers import KOLKATA_TZ

    admin = User.objects.create_superuser(
        email='rf_admin3@example.com', role=User.Role.SUPER_ADMIN
    )
    deepak = User.objects.create_user(
        email='deepak3@example.com', role=User.Role.RECRUITER,
        first_name='Deepak', last_name='Kumar', recruiter_status=User.RecruiterStatus.ACTIVE,
    )

    def _kolkata_noon(date_obj):
        naive = datetime.combine(date_obj, datetime.min.time())
        aware = timezone.make_aware(naive, KOLKATA_TZ)
        return aware + timedelta(hours=12)

    today_kolkata = timezone.localtime(timezone.now(), KOLKATA_TZ).date()

    c_today = _mk_candidate('d3_today@example.com', 'Deepak Today', uploaded_by=deepak, created_by=deepak)
    CandidateProfile.objects.filter(pk=c_today.pk).update(created_at=_kolkata_noon(today_kolkata))

    c_old = _mk_candidate('d3_old@example.com', 'Deepak Old', uploaded_by=deepak, created_by=deepak)
    CandidateProfile.objects.filter(pk=c_old.pk).update(created_at=_kolkata_noon(today_kolkata - timedelta(days=40)))

    from django.test import Client
    client = Client()
    client.force_login(admin)

    start = (today_kolkata - timedelta(days=6)).isoformat()
    end = today_kolkata.isoformat()

    resp_scoped = client.get(reverse('frontend:candidate_search'), {
        'recruiter_id': str(deepak.id), 'start': start, 'end': end,
    })
    assert {c.id for c in resp_scoped.context['candidates']} == {c_today.id}

    resp_all_time = client.get(reverse('frontend:candidate_search'), {
        'recruiter_id': str(deepak.id),
    })
    assert {c.id for c in resp_all_time.context['candidates']} == {c_today.id, c_old.id}

