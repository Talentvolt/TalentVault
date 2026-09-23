import pytest
from datetime import datetime, timedelta
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from utils.date_helpers import KOLKATA_TZ


def _utc_for_kolkata_date_noon(date_obj):
    """Return an aware UTC datetime corresponding to 12:00 IST on the given date."""
    naive_midnight = datetime.combine(date_obj, datetime.min.time())
    aware_ist_midnight = timezone.make_aware(naive_midnight, KOLKATA_TZ)
    return aware_ist_midnight + timedelta(hours=12)


def _create_candidate(candidate_user, owner, created_utc):
    profile = CandidateProfile.objects.create(
        user=candidate_user,
        full_name=candidate_user.email,
        location='Test',
        uploaded_by=owner,
        created_by=owner,
    )
    CandidateProfile.objects.filter(pk=profile.pk).update(created_at=created_utc)
    return profile


@pytest.fixture
def upload_activity_data(db):
    admin = User.objects.create_superuser(
        email='activity_admin@example.com', role=User.Role.SUPER_ADMIN
    )
    garima = User.objects.create_user(
        email='garima@example.com', role=User.Role.RECRUITER,
        first_name='Garima', last_name='Sharma', recruiter_status=User.RecruiterStatus.ACTIVE,
    )
    rahul = User.objects.create_user(
        email='rahul@example.com', role=User.Role.RECRUITER,
        first_name='Rahul', last_name='Verma', recruiter_status=User.RecruiterStatus.ACTIVE,
    )

    today_kolkata = timezone.localtime(timezone.now(), KOLKATA_TZ).date()
    d0 = _utc_for_kolkata_date_noon(today_kolkata)
    d1 = _utc_for_kolkata_date_noon(today_kolkata - timedelta(days=1))
    d2 = _utc_for_kolkata_date_noon(today_kolkata - timedelta(days=2))

    # Garima: 3 today, 2 yesterday, 1 two-days-ago
    for _ in range(3):
        u = User.objects.create_user(
            email=f'g.today.{_}@example.com', role=User.Role.CANDIDATE
        )
        _create_candidate(u, garima, d0)
    for _ in range(2):
        u = User.objects.create_user(
            email=f'g.yest.{_}@example.com', role=User.Role.CANDIDATE
        )
        _create_candidate(u, garima, d1)
    u = User.objects.create_user(email='g.d2@example.com', role=User.Role.CANDIDATE)
    _create_candidate(u, garima, d2)

    # Rahul: 1 today
    u = User.objects.create_user(email='r.today@example.com', role=User.Role.CANDIDATE)
    _create_candidate(u, rahul, d0)

    # Unassigned: 1 yesterday
    u = User.objects.create_user(email='unassigned@example.com', role=User.Role.CANDIDATE)
    p = CandidateProfile.objects.create(
        user=u, full_name='Unassigned Person', location='Test',
        uploaded_by=None, created_by=None,
    )
    CandidateProfile.objects.filter(pk=p.pk).update(created_at=d1)

    return {
        'admin': admin,
        'garima': garima,
        'rahul': rahul,
        'today_kolkata': today_kolkata,
    }


@pytest.mark.django_db
def test_upload_activity_counts_grouped_by_recruiter(upload_activity_data):
    from django.test import Client
    client = Client()
    client.force_login(upload_activity_data['admin'])

    response = client.get(reverse('frontend:recruiter_dashboard'))
    assert response.status_code == 200

    context = response.context
    rows = context['recruiter_upload_rows']

    by_name = {r['name']: r for r in rows}
    assert 'Garima Sharma' in by_name
    assert 'Rahul Verma' in by_name
    assert 'Unassigned' in by_name

    assert by_name['Garima Sharma']['total'] == 6
    assert by_name['Rahul Verma']['total'] == 1
    assert by_name['Unassigned']['total'] == 1

    # Newest date first
    dates = [d['date'] for d in context['recruiter_upload_dates']]
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == upload_activity_data['today_kolkata']

    # Garima today count == 3
    today = upload_activity_data['today_kolkata']
    assert by_name['Garima Sharma']['counts'][today] == 3


@pytest.mark.django_db
def test_upload_activity_renders_names_and_empty_state(db):
    admin = User.objects.create_superuser(
        email='empty_admin@example.com', role=User.Role.SUPER_ADMIN
    )
    from django.test import Client
    client = Client()
    client.force_login(admin)

    response = client.get(reverse('frontend:recruiter_dashboard'))
    assert response.status_code == 200
    html = response.content.decode('utf-8')
    assert 'Recruiter Candidate Upload Activity' in html
    assert 'No candidate uploads recorded yet.' in html
