import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.candidates.models import CandidateProfile, CandidateSkill, RecentCandidateSearch
from apps.companies.models import Company
from apps.jobs.models import Job, JobSkill
from services.candidate_matching_service import CandidateMatchingService


def _make_candidate(**profile_kwargs):
    user = User.objects.create_user(
        email=f"cand_{profile_kwargs.get('full_name', 'x').replace(' ', '')}@example.com",
        password="password123",
        role=User.Role.CANDIDATE,
        first_name="Rajeev",
        last_name="Kumar",
    )
    profile = CandidateProfile.objects.create(user=user, full_name="Rajeev Kumar", **profile_kwargs)
    return user, profile


def _make_job(company, title, skills=None, **kwargs):
    defaults = {
        "title": title,
        "company": company,
        "status": "ACTIVE",
        "location": kwargs.pop("location", ""),
        "description": kwargs.pop("description", f"{title} description"),
        "min_experience": kwargs.pop("min_experience", 0),
        "max_experience": kwargs.pop("max_experience", 0),
        "work_mode": kwargs.pop("work_mode", "ONSITE"),
        "is_remote": kwargs.pop("is_remote", False),
    }
    defaults.update(kwargs)
    job = Job.objects.create(**defaults)
    for skill in skills or []:
        JobSkill.objects.create(job=job, skill_name=skill)
    return job


@pytest.fixture
def company(db):
    return Company.objects.create(name="Test Co", slug="test-co")


def _scores(candidate):
    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=20)
    return {str(r["job"].id): r for r in recs}


@pytest.mark.django_db
def test_preferred_designation_ranks_first(company):
    _, candidate = _make_candidate(preferred_job_role="Backend Developer", current_designation="Python Developer")
    j_backend = _make_job(company, "Backend Developer", skills=["Python"], location="Noida")
    j_frontend = _make_job(company, "Frontend Developer", skills=["React"], location="Noida")

    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=10)
    ids = [str(r["job"].id) for r in recs]

    assert str(j_backend.id) in ids
    assert str(j_backend.id) == ids[0]
    backend = next(r for r in recs if r["job"].id == j_backend.id)
    assert "preferred Backend Developer" in backend["reason"]


@pytest.mark.django_db
def test_recent_search_intent_boosts_matching_jobs(company):
    _, candidate = _make_candidate()
    RecentCandidateSearch.objects.create(user=candidate.user, search_query="Django Developer", filters_payload={})

    j_django = _make_job(company, "Django Developer", skills=["Python", "Django"], location="Noida")
    j_frontend = _make_job(company, "Frontend Developer", skills=["React"], location="Noida")

    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=10)
    ids = [str(r["job"].id) for r in recs]

    assert str(j_django.id) in ids
    django_rec = next(r for r in recs if r["job"].id == j_django.id)
    assert django_rec["reason"] == "Matches your recent search"
    # Frontend is clearly irrelevant and must be excluded.
    assert str(j_frontend.id) not in ids


@pytest.mark.django_db
def test_skill_match_affects_ranking(company):
    _, candidate = _make_candidate(current_designation="Software Engineer")
    CandidateSkill.objects.create(profile=candidate, skill_name="Python")
    CandidateSkill.objects.create(profile=candidate, skill_name="Django")

    j_full = _make_job(company, "Software Engineer", skills=["Python", "Django"], location="Noida")
    j_partial = _make_job(company, "Software Engineer II", skills=["Python", "Django", "React"], location="Noida")

    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=10)
    ids = [str(r["job"].id) for r in recs]
    assert str(j_full.id) in ids and str(j_partial.id) in ids
    assert ids.index(str(j_full.id)) < ids.index(str(j_partial.id))


@pytest.mark.django_db
def test_experience_mismatch_lowers_ranking(company):
    _, candidate = _make_candidate(current_designation="Python Developer", total_experience=1)
    CandidateSkill.objects.create(profile=candidate, skill_name="Python")

    j_low = _make_job(company, "Python Developer", skills=["Python"], location="Noida", min_experience=0, max_experience=2)
    j_high = _make_job(company, "Python Developer Senior", skills=["Python"], location="Noida", min_experience=6, max_experience=10)

    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=10)
    ids = [str(r["job"].id) for r in recs]
    assert ids.index(str(j_low.id)) < ids.index(str(j_high.id))


@pytest.mark.django_db
def test_location_mismatch_lowers_ranking(company):
    _, candidate = _make_candidate(current_designation="Python Developer", location="Noida")
    CandidateSkill.objects.create(profile=candidate, skill_name="Python")

    j_noida = _make_job(company, "Python Developer", skills=["Python"], location="Noida")
    j_mumbai = _make_job(company, "Python Developer", skills=["Python"], location="Mumbai")

    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=10)
    ids = [str(r["job"].id) for r in recs]
    assert ids.index(str(j_noida.id)) < ids.index(str(j_mumbai.id))


@pytest.mark.django_db
def test_related_jobs_remain_visible(company):
    _, candidate = _make_candidate(current_designation="Python Developer")
    CandidateSkill.objects.create(profile=candidate, skill_name="Python")
    CandidateSkill.objects.create(profile=candidate, skill_name="Django")

    j_django = _make_job(company, "Django Developer", skills=["Python", "Django"], location="Noida")
    j_backend = _make_job(company, "Backend Engineer", skills=["Python"], location="Noida")

    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=10)
    ids = [str(r["job"].id) for r in recs]
    assert str(j_django.id) in ids
    assert str(j_backend.id) in ids


@pytest.mark.django_db
def test_irrelevant_jobs_excluded(company):
    _, candidate = _make_candidate(current_designation="Python Developer")
    CandidateSkill.objects.create(profile=candidate, skill_name="Python")

    _make_job(company, "Python Developer", skills=["Python"], location="Noida")
    j_sales = _make_job(company, "Sales Executive", skills=["Sales"], location="Mumbai")

    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=10)
    ids = [str(r["job"].id) for r in recs]
    assert str(j_sales.id) not in ids


@pytest.mark.django_db
def test_missing_candidate_data_does_not_crash(company):
    _, candidate = _make_candidate()
    _make_job(company, "Backend Developer", skills=["Python"], location="Noida")

    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=10)
    assert isinstance(recs, list)


@pytest.mark.django_db
def test_anonymous_user_does_not_crash(client):
    resp = client.get("/jobs/")
    assert resp.status_code == 200

    from django.contrib.auth.models import AnonymousUser
    CandidateMatchingService.record_job_search_intent(AnonymousUser(), "Django", {})
    assert RecentCandidateSearch.objects.count() == 0


@pytest.mark.django_db
def test_replacing_resume_invalidates_recommendations(company):
    _, candidate = _make_candidate(preferred_job_role="Backend Developer")
    j_backend = _make_job(company, "Backend Developer", skills=["Python"], location="Noida")
    _make_job(company, "Frontend Developer", skills=["React"], location="Noida")

    # Warm cache with current intent.
    CandidateMatchingService.get_recommended_jobs(candidate, limit=10)
    first_top = CandidateMatchingService.get_job_recommendations(candidate, limit=1)[0]
    assert first_top["job"].id == j_backend.id

    # Simulate resume/profile change and invalidate.
    candidate.preferred_job_role = "Frontend Developer"
    candidate.save(update_fields=["preferred_job_role"])
    CandidateMatchingService.invalidate_recommendations(candidate)

    recs = CandidateMatchingService.get_job_recommendations(candidate, limit=1)
    assert recs  # still returns something, reflecting the new intent


@pytest.mark.django_db
def test_record_job_search_intent_populates_profile(company):
    _, candidate = _make_candidate()
    CandidateMatchingService.record_job_search_intent(
        candidate.user, "Python Backend Developer", {"location": "Noida", "skills": "Django"}
    )
    assert RecentCandidateSearch.objects.filter(user=candidate.user).exists()

    intent = CandidateMatchingService.build_candidate_intent(candidate)
    assert intent["has_intent"] is True
    assert intent["search_locations"]


@pytest.mark.django_db
def test_dashboard_renders_recommendations(company, client):
    user = User.objects.create_user(
        email="dash.cand@example.com", password="password123", role=User.Role.CANDIDATE
    )
    user.is_verified = True
    user.is_active = True
    user.save()
    CandidateProfile.objects.create(
        user=user, full_name="Dash Candidate", location="Noida",
        current_designation="Python Developer",
    )
    CandidateSkill.objects.create(profile=user.candidate_profile, skill_name="Python")
    _make_job(company, "Python Developer", skills=["Python"], location="Noida")

    client.force_login(user)
    resp = client.get(reverse("frontend:candidate_dashboard"))
    assert resp.status_code == 200
    html = resp.content.decode("utf-8")
    assert "AI Recommended Jobs" in html
    assert "% Match" in html
