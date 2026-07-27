import pytest
from django.urls import reverse
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile, Project
from apps.applications.models import Application
from apps.jobs.models import Job, Company
from utils.url_helpers import normalize_external_url
from apps.core.templatetags.core_tags import external_url

def test_normalize_external_url_cases():
    assert normalize_external_url("linkedin.com/in/john") == "https://linkedin.com/in/john"
    assert normalize_external_url("www.linkedin.com/in/john") == "https://www.linkedin.com/in/john"
    assert normalize_external_url("https://linkedin.com/in/john") == "https://linkedin.com/in/john"
    assert normalize_external_url("http://myportfolio.com") == "http://myportfolio.com"
    assert normalize_external_url("/internal/path/") == "/internal/path/"
    assert normalize_external_url("#section") == "#section"
    assert normalize_external_url("") == ""
    assert normalize_external_url(None) is None

def test_external_url_template_filter():
    assert external_url("github.com/developer") == "https://github.com/developer"
    assert external_url("https://github.com/developer") == "https://github.com/developer"
    assert external_url(None) == ""

@pytest.mark.django_db
def test_candidate_profile_normalizes_urls_on_save():
    user = User.objects.create_user(email="social.candidate@example.com", role=User.Role.CANDIDATE)
    profile = CandidateProfile.objects.create(
        user=user,
        full_name="Social User",
        location="Remote",
        linkedin_url="linkedin.com/in/socialuser",
        portfolio_url="www.socialportfolio.com"
    )
    
    profile.refresh_from_db()
    assert profile.linkedin_url == "https://linkedin.com/in/socialuser"
    assert profile.portfolio_url == "https://www.socialportfolio.com"
    assert profile.normalized_linkedin_url == "https://linkedin.com/in/socialuser"
    assert profile.normalized_portfolio_url == "https://www.socialportfolio.com"

@pytest.mark.django_db
def test_application_normalizes_urls_on_save():
    company = Company.objects.create(name="TechCorp")
    job = Job.objects.create(company=company, title="DevOps Engineer", location="Remote", status=Job.JobStatus.ACTIVE)
    user = User.objects.create_user(email="app.candidate@example.com", role=User.Role.CANDIDATE)
    profile = CandidateProfile.objects.create(user=user, full_name="App Candidate", location="Remote")

    app = Application.objects.create(
        job=job,
        candidate=profile,
        linkedin_url="linkedin.com/in/appcandidate",
        portfolio_url="myportfolio.dev"
    )
    app.refresh_from_db()
    assert app.linkedin_url == "https://linkedin.com/in/appcandidate"
    assert app.portfolio_url == "https://myportfolio.dev"
    assert app.normalized_linkedin_url == "https://linkedin.com/in/appcandidate"
    assert app.normalized_portfolio_url == "https://myportfolio.dev"

@pytest.mark.django_db
def test_project_normalizes_link_on_save():
    user = User.objects.create_user(email="proj.candidate@example.com", role=User.Role.CANDIDATE)
    profile = CandidateProfile.objects.create(user=user, full_name="Proj Candidate", location="Remote")

    project = Project.objects.create(
        profile=profile,
        title="Cool App",
        link="github.com/candidate/cool-app"
    )
    project.refresh_from_db()
    assert project.link == "https://github.com/candidate/cool-app"
    assert project.normalized_link == "https://github.com/candidate/cool-app"

@pytest.mark.django_db
def test_candidate_profile_page_renders_external_social_links(client):
    user = User.objects.create_user(email="profile.user@example.com", role=User.Role.CANDIDATE)
    user.set_password("pass1234")
    user.save()

    profile = CandidateProfile.objects.create(
        user=user,
        full_name="Profile User",
        location="Bangalore",
        linkedin_url="linkedin.com/in/profileuser",
        portfolio_url="www.myportfolio.com"
    )

    client.force_login(user)
    url = reverse('frontend:candidate_profile')
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode('utf-8')
    assert 'href="https://linkedin.com/in/profileuser"' in content
    assert 'href="https://www.myportfolio.com"' in content
    assert 'target="_blank"' in content
    assert 'rel="noopener noreferrer"' in content
