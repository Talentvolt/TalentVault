import pytest
from django.urls import reverse
from apps.accounts.models import User
from apps.companies.models import Company
from apps.clients.models import Client
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile
from apps.applications.models import Application

@pytest.mark.django_db
def test_candidate_listing_displays_client_name(client):
    recruiter = User.objects.create_user(
        email='recruiter_list@company.com',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    comp, _ = Company.objects.get_or_create(name="TalentVault Test Company")
    client_obj = Client.objects.create(
        company_name="Tech Mahindra",
        spoc_name="Rahul HR"
    )

    # Job with Client assigned
    job_with_client = Job.objects.create(
        company=comp,
        client=client_obj,
        title="Customer Support",
        location="Dehradun",
        work_mode="ONSITE",
        status="ACTIVE"
    )

    cand_user = User.objects.create_user(
        email='candidate_client@company.com',
        password='Password123!',
        role=User.Role.CANDIDATE
    )
    cand_profile = CandidateProfile.objects.create(
        user=cand_user,
        full_name="Rajeev Kumar"
    )

    app = Application.objects.create(
        job=job_with_client,
        candidate=cand_profile,
        created_by=recruiter
    )

    client.force_login(recruiter)
    url = reverse('frontend:candidate_search')
    response = client.get(url)
    assert response.status_code == 200

    html = response.content.decode('utf-8')
    assert "Customer Support" in html
    assert "Tech Mahindra" in html


@pytest.mark.django_db
def test_candidate_pagination_safe_fallbacks(client):
    recruiter = User.objects.create_user(
        email='recruiter_page_test@company.com',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    client.force_login(recruiter)
    url = reverse('frontend:candidate_search')

    # 1. Base URL
    resp1 = client.get(url)
    assert resp1.status_code == 200

    # 2. page=2 (when only 0 or 1 page exists)
    resp2 = client.get(url + '?page=2')
    assert resp2.status_code == 200

    # 3. page=999 (large out of bounds page)
    resp3 = client.get(url + '?page=999')
    assert resp3.status_code == 200

    # 4. tab=modified
    resp4 = client.get(url + '?tab=modified')
    assert resp4.status_code == 200

    # 5. tab=modified&tags=Sales Manager&sort_by=relevance
    resp5 = client.get(url + '?tab=modified&tags=Sales%20Manager&sort_by=relevance')
    assert resp5.status_code == 200

    # 6. Exact previously failing URL: page=2&tab=modified&tags=Sales Manager&sort_by=relevance
    resp6 = client.get(url + '?page=2&tab=modified&tags=Sales%20Manager&sort_by=relevance')
    assert resp6.status_code == 200


@pytest.mark.django_db
def test_candidate_uploader_and_relative_timestamps(client):
    from django.utils import timezone
    import datetime
    from apps.candidates.models import CandidateSkill

    recruiter = User.objects.create_user(
        email='anamika.shukla@company.com',
        first_name='Anamika',
        last_name='Shukla',
        password='Password123!',
        role=User.Role.RECRUITER
    )

    now = timezone.now()

    # Candidate 1: Uploaded by Anamika Shukla today (2 hours ago)
    cand_user1 = User.objects.create_user(email='vishal.mali@test.com', password='Password123!', role=User.Role.CANDIDATE)
    c1 = CandidateProfile.objects.create(
        user=cand_user1,
        full_name='Vishal Mali',
        current_designation='Program Guide',
        current_company='Itvedant Education',
        uploaded_by=recruiter
    )
    CandidateProfile.objects.filter(id=c1.id).update(created_at=now - datetime.timedelta(hours=2))
    c1.refresh_from_db()

    # Candidate 2: Uploaded yesterday by TalentVault Recruiter
    recruiter2 = User.objects.create_user(
        email='recruiter@company.com',
        first_name='TalentVault',
        last_name='Recruiter',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    cand_user2 = User.objects.create_user(email='vishal.kumar@test.com', password='Password123!', role=User.Role.CANDIDATE)
    c2 = CandidateProfile.objects.create(
        user=cand_user2,
        full_name='Vishal Kumar',
        current_designation='Data Analyst',
        current_company='ABC Company',
        uploaded_by=recruiter2
    )
    CandidateProfile.objects.filter(id=c2.id).update(created_at=now - datetime.timedelta(days=1))
    c2.refresh_from_db()

    # Candidate 3: Old candidate with no uploader
    cand_user3 = User.objects.create_user(email='old.cand@test.com', password='Password123!', role=User.Role.CANDIDATE)
    c3 = CandidateProfile.objects.create(
        user=cand_user3,
        full_name='Rahul Nishad',
        current_designation='React Developer',
        current_company='Tech Corp',
        uploaded_by=None,
        created_by=None
    )
    CandidateProfile.objects.filter(id=c3.id).update(created_at=now - datetime.timedelta(days=3))
    c3.refresh_from_db()

    client.force_login(recruiter)
    url = reverse('frontend:candidate_search')
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode('utf-8')

    assert "Anamika Shukla" in html
    assert "TalentVault Recruiter" in html
    assert "System Import" in html
    assert "hour" in html or "Yesterday" in html or "days ago" in html


@pytest.mark.django_db
def test_candidate_live_autocomplete_queries(client):
    from apps.candidates.models import CandidateSkill

    recruiter = User.objects.create_user(
        email='recruiter_auto@company.com',
        first_name='Auto',
        last_name='Recruiter',
        password='Password123!',
        role=User.Role.RECRUITER
    )

    # Cand 1: Vishal Mali - Program Guide, Itvedant Education
    u1 = User.objects.create_user(email='vishalmali@company.com', password='Password123!', role=User.Role.CANDIDATE)
    c1 = CandidateProfile.objects.create(
        user=u1,
        full_name='Vishal Mali',
        current_designation='Program Guide',
        current_company='Itvedant Education'
    )

    # Cand 2: Data Analyst with React skill
    u2 = User.objects.create_user(email='data.dev@company.com', password='Password123!', role=User.Role.CANDIDATE)
    c2 = CandidateProfile.objects.create(
        user=u2,
        full_name='Vishal Kumar',
        current_designation='Data Analyst',
        current_company='Analytics Inc'
    )
    CandidateSkill.objects.create(profile=c2, skill_name='React')

    # Cand 3: Sales Manager
    u3 = User.objects.create_user(email='sales.lead@company.com', password='Password123!', role=User.Role.CANDIDATE)
    c3 = CandidateProfile.objects.create(
        user=u3,
        full_name='Neha Sharma',
        current_designation='Sales Manager',
        current_company='Enterprise Global'
    )
    CandidateSkill.objects.create(profile=c3, skill_name='B2B Sales')

    client.force_login(recruiter)
    auto_url = reverse('frontend:candidate_autocomplete')

    # 1. Query: "vish" -> should return Vishal Mali and Vishal Kumar
    r_vish = client.get(f"{auto_url}?q=vish")
    assert r_vish.status_code == 200
    d_vish = r_vish.json()
    assert d_vish['count'] >= 2
    names_vish = [item['name'] for item in d_vish['results']]
    assert 'Vishal Mali' in names_vish
    assert 'Vishal Kumar' in names_vish

    # 2. Query: "data" -> should return candidate with Data Analyst designation
    r_data = client.get(f"{auto_url}?q=data")
    assert r_data.status_code == 200
    d_data = r_data.json()
    assert d_data['count'] >= 1
    assert any('Data Analyst' in item['designation'] for item in d_data['results'])

    # 3. Query: "react" -> should return candidate with React skill
    r_react = client.get(f"{auto_url}?q=react")
    assert r_react.status_code == 200
    d_react = r_react.json()
    assert d_react['count'] >= 1
    assert any('React' in item.get('matched_skill', '') or 'React' in str(item.get('skills', [])) for item in d_react['results'])

    # 4. Query: "sales" -> should return Sales Manager
    r_sales = client.get(f"{auto_url}?q=sales")
    assert r_sales.status_code == 200
    d_sales = r_sales.json()
    assert d_sales['count'] >= 1
    assert any('Sales Manager' in item['designation'] for item in d_sales['results'])


@pytest.mark.django_db
def test_candidate_chronological_sequence_newest_first(client):
    import datetime
    from django.utils import timezone
    import zoneinfo

    tz = zoneinfo.ZoneInfo('Asia/Kolkata')
    recruiter = User.objects.create_user(
        email='recruiter_chrono@company.com',
        first_name='Anamika',
        last_name='Shukla',
        password='Password123!',
        role=User.Role.RECRUITER
    )

    recruiter_rahul = User.objects.create_user(
        email='rahul.nishad@company.com',
        first_name='Rahul',
        last_name='Nishad',
        password='Password123!',
        role=User.Role.RECRUITER
    )

    # 20 Aug 04:49 PM
    t1 = datetime.datetime(2026, 8, 20, 16, 49, 0, tzinfo=tz)
    u1 = User.objects.create_user(email='c_aug20_449@test.com', password='Password123!', role=User.Role.CANDIDATE)
    c1 = CandidateProfile.objects.create(user=u1, full_name='Candidate Aug20 Late', uploaded_by=recruiter)
    CandidateProfile.objects.filter(id=c1.id).update(created_at=t1)

    # 20 Aug 02:15 PM
    t2 = datetime.datetime(2026, 8, 20, 14, 15, 0, tzinfo=tz)
    u2 = User.objects.create_user(email='c_aug20_215@test.com', password='Password123!', role=User.Role.CANDIDATE)
    c2 = CandidateProfile.objects.create(user=u2, full_name='Candidate Aug20 Mid', uploaded_by=recruiter_rahul)
    CandidateProfile.objects.filter(id=c2.id).update(created_at=t2)

    # 20 Aug 11:30 AM
    t3 = datetime.datetime(2026, 8, 20, 11, 30, 0, tzinfo=tz)
    u3 = User.objects.create_user(email='c_aug20_1130@test.com', password='Password123!', role=User.Role.CANDIDATE)
    c3 = CandidateProfile.objects.create(user=u3, full_name='Candidate Aug20 Early')
    CandidateProfile.objects.filter(id=c3.id).update(created_at=t3)

    # 19 Aug 07:16 PM
    t4 = datetime.datetime(2026, 8, 19, 19, 16, 0, tzinfo=tz)
    u4 = User.objects.create_user(email='c_aug19_716@test.com', password='Password123!', role=User.Role.CANDIDATE)
    c4 = CandidateProfile.objects.create(user=u4, full_name='Candidate Aug19 Eve')
    CandidateProfile.objects.filter(id=c4.id).update(created_at=t4)

    # 18 Aug 10:00 AM
    t5 = datetime.datetime(2026, 8, 18, 10, 0, 0, tzinfo=tz)
    u5 = User.objects.create_user(email='c_aug18@test.com', password='Password123!', role=User.Role.CANDIDATE)
    c5 = CandidateProfile.objects.create(user=u5, full_name='Candidate Aug18')
    CandidateProfile.objects.filter(id=c5.id).update(created_at=t5)

    # 17 Aug 10:00 AM
    t6 = datetime.datetime(2026, 8, 17, 10, 0, 0, tzinfo=tz)
    u6 = User.objects.create_user(email='c_aug17@test.com', password='Password123!', role=User.Role.CANDIDATE)
    c6 = CandidateProfile.objects.create(user=u6, full_name='Candidate Aug17')
    CandidateProfile.objects.filter(id=c6.id).update(created_at=t6)

    client.force_login(recruiter)
    url = reverse('frontend:candidate_search')
    response = client.get(url)
    assert response.status_code == 200

    candidates_returned = list(response.context['candidates'])
    returned_ids = [c.id for c in candidates_returned]

    # Verify exact chronological ordering: newest first (c1, c2, c3, c4, c5, c6)
    expected_order = [c1.id, c2.id, c3.id, c4.id, c5.id, c6.id]
    assert returned_ids == expected_order

    # Verify uploader resolution
    c1_ret = next(c for c in candidates_returned if c.id == c1.id)
    c2_ret = next(c for c in candidates_returned if c.id == c2.id)
    c3_ret = next(c for c in candidates_returned if c.id == c3.id)

    assert c1_ret.uploader_name == "Anamika Shukla"
    assert c2_ret.uploader_name == "Rahul Nishad"
    assert c3_ret.uploader_name is None
    assert c3_ret.effective_uploader_name == "System Import"



