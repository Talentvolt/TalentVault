import pytest
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from apps.jobs.models import Job
from apps.companies.models import Company
from apps.applications.models import Application
from utils.date_helpers import format_relative_time, format_registration_date

@pytest.mark.django_db
def test_format_relative_time():
    now = timezone.now()
    
    assert format_relative_time(None) == "Never logged in"
    assert format_relative_time(now) == "Just now"
    assert format_relative_time(now - timedelta(seconds=10)) == "Just now"
    assert format_relative_time(now - timedelta(minutes=2)) == "2 minutes ago"
    assert format_relative_time(now - timedelta(minutes=10)) == "10 minutes ago"
    assert format_relative_time(now - timedelta(hours=1)) == "1 hour ago"
    assert format_relative_time(now - timedelta(days=2)) == "2 days ago"
    assert format_relative_time(now - timedelta(days=7)) == "1 week ago"
    assert format_relative_time(now - timedelta(days=14)) == "2 weeks ago"

@pytest.mark.django_db
def test_format_registration_date():
    now = timezone.now()
    local_now = timezone.localtime(now)
    
    today_formatted = format_registration_date(now)
    assert "Today" in today_formatted
    
    yesterday_dt = now - timedelta(days=1)
    yesterday_formatted = format_registration_date(yesterday_dt)
    assert "Yesterday" in yesterday_formatted or (local_now.date() - timezone.localtime(yesterday_dt).date()).days == 1

@pytest.mark.django_db
def test_admin_dashboard_candidate_signup_analytics_empty(client):
    admin = User.objects.create_superuser(email="admin_test@example.com", role=User.Role.SUPER_ADMIN)
    client.force_login(admin)
    
    url = reverse('frontend:recruiter_dashboard')
    response = client.get(url)
    
    assert response.status_code == 200

@pytest.mark.django_db
def test_admin_dashboard_candidate_signup_analytics_with_data(client):
    admin = User.objects.create_superuser(email="admin_analytics@example.com", role=User.Role.SUPER_ADMIN)
    company = Company.objects.create(name="Analytics Corp")
    job = Job.objects.create(title="Backend Dev", company=company, status=Job.JobStatus.ACTIVE)
    
    cand_user = User.objects.create_user(email="rahul.sharma@example.com", role=User.Role.CANDIDATE)
    cand_user.last_login = timezone.now() - timedelta(minutes=2)
    cand_user.save()
    
    profile = CandidateProfile.objects.create(
        user=cand_user,
        full_name="Rahul Sharma",
        location="Bangalore"
    )
    
    Application.objects.create(
        job=job,
        candidate=profile,
        stage=Application.ApplicationStage.OPEN
    )
    
    client.force_login(admin)
    url = reverse('frontend:recruiter_dashboard')
    response = client.get(url)
    
    assert response.status_code == 200
