import pytest
from django.urls import reverse
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile, Project, Education

@pytest.mark.django_db
def test_candidate_profile_renders_modern_modals_without_native_dialogs(client):
    user = User.objects.create_user(email="candidate.modals@example.com", password="password123", role=User.Role.CANDIDATE)
    profile = CandidateProfile.objects.create(user=user, full_name="Modal Candidate")
    
    # Create sample project and education entries
    project = Project.objects.create(
        profile=profile,
        title="AI Chatbot Portal",
        description="Built using Django and React",
        link="https://mychatbot.com"
    )
    education = Education.objects.create(
        profile=profile,
        institution="IIT Delhi",
        degree="M.Tech",
        field_of_study="Computer Science"
    )

    client.force_login(user)
    url = reverse('frontend:candidate_profile') + "?edit=true"
    response = client.get(url)
    assert response.status_code == 200

    html = response.content.decode('utf-8')

    # Verify modern modal elements exist
    assert 'id="projectModal"' in html
    assert 'id="educationModal"' in html
    assert 'id="confirmDeleteModal"' in html
    assert 'id="project_title"' in html
    assert 'id="project_technologies"' in html
    assert 'id="project_github_url"' in html
    assert 'id="edu_degree"' in html
    assert 'id="edu_institution"' in html
    assert 'id="edu_university"' in html

    # Verify absence of native browser dialogs
    assert 'prompt(' not in html
    assert 'confirm(' not in html
    assert 'alert(' not in html

@pytest.mark.django_db
def test_project_api_crud_flow(client):
    user = User.objects.create_user(email="candidate.proj@example.com", password="password123", role=User.Role.CANDIDATE)
    profile = CandidateProfile.objects.create(user=user, full_name="Project Candidate")
    client.force_login(user)

    # 1. Create Project via REST API
    post_url = "/api/v1/candidates/projects/"
    response = client.post(
        post_url,
        data={
            "title": "Recruitment Engine",
            "description": "High performance candidate matching",
            "link": "https://recruitment.example.com"
        },
        content_type="application/json"
    )
    assert response.status_code == 210 or response.status_code == 201
    proj_id = response.json()["id"]

    # 2. Update Project via PATCH
    patch_url = f"/api/v1/candidates/projects/{proj_id}/"
    response = client.patch(
        patch_url,
        data={"title": "Recruitment Engine v2"},
        content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Recruitment Engine v2"

    # 3. Delete Project via DELETE
    response = client.delete(patch_url)
    assert response.status_code == 204
    assert Project.objects.filter(id=proj_id).count() == 0

@pytest.mark.django_db
def test_education_api_crud_flow(client):
    user = User.objects.create_user(email="candidate.edu@example.com", password="password123", role=User.Role.CANDIDATE)
    profile = CandidateProfile.objects.create(user=user, full_name="Education Candidate")
    client.force_login(user)

    # 1. Create Education via REST API
    post_url = "/api/v1/candidates/education/"
    response = client.post(
        post_url,
        data={
            "institution": "BITS Pilani",
            "degree": "B.E. Computer Science",
            "field_of_study": "Computer Science",
            "percentage_or_cgpa": "9.1 CGPA"
        },
        content_type="application/json"
    )
    assert response.status_code == 201
    edu_id = response.json()["id"]

    # 2. Update Education via PATCH
    patch_url = f"/api/v1/candidates/education/{edu_id}/"
    response = client.patch(
        patch_url,
        data={"institution": "BITS Pilani Main Campus"},
        content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["institution"] == "BITS Pilani Main Campus"

    # 3. Delete Education via DELETE
    response = client.delete(patch_url)
    assert response.status_code == 204
    assert Education.objects.filter(id=edu_id).count() == 0
