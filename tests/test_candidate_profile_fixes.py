import io
import tempfile

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile, CandidateSkill, Project


@pytest.fixture
def local_media(settings):
    media_root = tempfile.mkdtemp(prefix="tv_media_")
    settings.MEDIA_ROOT = media_root
    settings.USE_LOCAL_STORAGE = "1"
    settings.MEDIA_URL = "/media/"
    settings.DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    return media_root


@pytest.fixture
def candidate_user(client):
    user = User.objects.create_user(
        email="profile.fixes@example.com",
        password="password123",
        role=User.Role.CANDIDATE,
    )
    user.is_verified = True
    user.is_active = True
    user.save()
    CandidateProfile.objects.create(user=user, full_name="Rajeev Kumar", location="India")
    client.force_login(user)
    return user


@pytest.mark.django_db
def test_project_create_accepts_bare_domain_link(candidate_user, client):
    url = "/api/v1/candidates/projects/"
    response = client.post(
        url,
        data={"title": "Recruitment Engine", "description": "Matching", "link": "github.com/myproject"},
        content_type="application/json",
    )
    assert response.status_code in (200, 201)
    project = Project.objects.get(title="Recruitment Engine")
    assert project.link == "https://github.com/myproject"


@pytest.mark.django_db
def test_skill_create_accepts_uppercase_proficiency(candidate_user, client):
    url = "/api/v1/candidates/skills/"
    response = client.post(
        url,
        data={"skill_name": "Django", "years_of_experience": 1, "proficiency": "INTERMEDIATE"},
        content_type="application/json",
    )
    assert response.status_code in (200, 201)
    assert CandidateSkill.objects.filter(profile__user=candidate_user, skill_name="Django").exists()


@pytest.mark.django_db
def test_skill_create_rejects_titlecase_proficiency(candidate_user, client):
    url = "/api/v1/candidates/skills/"
    response = client.post(
        url,
        data={"skill_name": "React", "years_of_experience": 1, "proficiency": "Intermediate"},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_photo_upload_replace_and_delete(local_media, candidate_user, client):
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile

    profile = candidate_user.candidate_profile

    def make_png(color):
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), color=color).save(buf, format="PNG")
        buf.seek(0)
        return SimpleUploadedFile("photo.png", buf.read(), content_type="image/png")

    upload_url = reverse("frontend:candidate_profile_photo_upload_ajax")

    # Upload
    resp = client.post(upload_url, {"profile_photo": make_png("red")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    profile.refresh_from_db()
    assert profile.has_profile_photo is True
    assert profile.profile_photo and profile.profile_photo.name
    assert profile.profile_photo_url.startswith("/media/")
    assert data["photo_url"].startswith("/media/")

    # Replace
    resp = client.post(upload_url, {"profile_photo": make_png("blue")})
    assert resp.status_code == 200
    profile.refresh_from_db()
    assert profile.has_profile_photo is True

    # Delete
    delete_url = reverse("frontend:candidate_profile_photo_delete_ajax")
    resp = client.post(delete_url)
    assert resp.status_code == 200
    profile.refresh_from_db()
    assert profile.has_profile_photo is False
    assert not profile.profile_photo


@pytest.mark.django_db
def test_photo_upload_rejects_non_image(local_media, candidate_user, client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload_url = reverse("frontend:candidate_profile_photo_upload_ajax")
    bad = SimpleUploadedFile("fake.png", b"not really an image", content_type="image/png")
    resp = client.post(upload_url, {"profile_photo": bad})
    assert resp.status_code == 400
    assert resp.json()["success"] is False


@pytest.mark.django_db
def test_profile_page_renders_avatar_and_resume_actions(local_media, candidate_user, client):
    profile = candidate_user.candidate_profile

    profile_url = reverse("frontend:candidate_profile")
    html = client.get(profile_url).content.decode("utf-8")

    # Avatar initials fallback (no photo yet)
    assert "profile-avatar-initials" in html
    assert "RA" in html

    # Resume action buttons present
    assert "Preview" in html
    assert "Download" in html
    assert "Replace" in html
    assert "Delete" in html


@pytest.mark.django_db
def test_user_initials_filter_safe_for_anonymous():
    from django.contrib.auth.models import AnonymousUser
    from apps.core.templatetags.core_tags import user_initials

    assert user_initials(AnonymousUser()) == "CV"

    user = User.objects.create_user(
        email="anon.safe@example.com",
        password="password123",
        first_name="Rajeev",
        last_name="Kumar",
        role=User.Role.CANDIDATE,
    )
    assert user_initials(user) == "RA"

    # A user with no candidate profile and no name falls back safely
    nameless = User(email="nameless@example.com")
    assert user_initials(nameless) == "CV"


@pytest.mark.django_db
def test_anonymous_jobs_page_renders_without_crash(client):
    resp = client.get("/jobs/")
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert "CV" in html
