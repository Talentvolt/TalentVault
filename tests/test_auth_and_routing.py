import pytest
from django.urls import reverse
from django.test import Client
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile

@pytest.mark.django_db
def test_candidate_login_and_routing():
    user = User.objects.create_user(
        email='candidate_test@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE,
        is_verified=True
    )
    CandidateProfile.objects.create(user=user, full_name='Candidate Test')

    client = Client()
    res = client.post('/accounts/login/candidate/', {'email': 'candidate_test@talentvault.in', 'password': 'Password123!'}, follow=True)
    assert res.status_code == 200
    assert res.redirect_chain[-1][0] == '/dashboard/candidate/'

@pytest.mark.django_db
def test_candidate_login_rejects_recruiter():
    recruiter = User.objects.create_user(
        email='recruiter_test@talentvault.in',
        password='Password123!',
        role=User.Role.RECRUITER,
        is_verified=True
    )
    client = Client()
    res = client.post('/accounts/login/candidate/', {'email': 'recruiter_test@talentvault.in', 'password': 'Password123!'})
    assert res.status_code == 200
    assert 'This workspace is reserved for Candidates' in res.content.decode('utf-8')

@pytest.mark.django_db
def test_recruiter_login_and_routing():
    recruiter = User.objects.create_user(
        email='employer_test@talentvault.in',
        password='Password123!',
        role=User.Role.RECRUITER,
        is_verified=True
    )
    client = Client()
    res = client.post('/accounts/login/employer/', {'email': 'employer_test@talentvault.in', 'password': 'Password123!'}, follow=True)
    assert res.status_code == 200
    assert res.redirect_chain[-1][0] == '/dashboard/recruiter/'

@pytest.mark.django_db
def test_recruiter_login_rejects_candidate():
    candidate = User.objects.create_user(
        email='cand_test@talentvault.in',
        password='Password123!',
        role=User.Role.CANDIDATE,
        is_verified=True
    )
    client = Client()
    res = client.post('/accounts/login/employer/', {'email': 'cand_test@talentvault.in', 'password': 'Password123!'})
    assert res.status_code == 200
    assert 'This workspace is reserved for Recruiters/Employers' in res.content.decode('utf-8')

@pytest.mark.django_db
def test_landing_page_routing():
    client = Client()

    # Unauthenticated -> Landing page
    res = client.get('/')
    assert res.status_code == 200
    assert 'landing.html' in [t.name for t in res.templates]

    # Candidate -> Candidate Dashboard
    cand_user = User.objects.create_user(email='c1@talentvault.in', password='Password123!', role=User.Role.CANDIDATE)
    client.force_login(cand_user)
    res_cand = client.get('/', follow=True)
    assert res_cand.redirect_chain[-1][0] == '/dashboard/candidate/'

    # Recruiter -> Recruiter Dashboard
    rec_user = User.objects.create_user(email='r1@talentvault.in', password='Password123!', role=User.Role.RECRUITER)
    client.force_login(rec_user)
    res_rec = client.get('/', follow=True)
    assert res_rec.redirect_chain[-1][0] == '/dashboard/recruiter/'

@pytest.mark.django_db
def test_cross_portal_access_prevention():
    cand_user = User.objects.create_user(email='cand_cross@talentvault.in', password='Password123!', role=User.Role.CANDIDATE)
    rec_user = User.objects.create_user(email='rec_cross@talentvault.in', password='Password123!', role=User.Role.RECRUITER)

    client = Client()

    # Candidate attempting recruiter dashboard -> redirected to candidate dashboard
    client.force_login(cand_user)
    res1 = client.get('/dashboard/recruiter/', follow=True)
    assert res1.redirect_chain[-1][0] == '/dashboard/candidate/'

    # Candidate attempting clients list -> redirected to candidate dashboard
    res2 = client.get('/clients/', follow=True)
    assert res2.redirect_chain[-1][0] == '/dashboard/candidate/'

    # Recruiter attempting candidate dashboard -> redirected to recruiter dashboard
    client.force_login(rec_user)
    res3 = client.get('/dashboard/candidate/', follow=True)
    assert res3.redirect_chain[-1][0] == '/dashboard/recruiter/'

    # Recruiter attempting saved jobs -> redirected to recruiter dashboard
    res4 = client.get('/jobs/saved/', follow=True)
    assert res4.redirect_chain[-1][0] == '/dashboard/recruiter/'

@pytest.mark.django_db
def test_logout_redirects():
    cand_user = User.objects.create_user(email='cand_logout@talentvault.in', password='Password123!', role=User.Role.CANDIDATE)
    rec_user = User.objects.create_user(email='rec_logout@talentvault.in', password='Password123!', role=User.Role.RECRUITER)

    client = Client()

    # Candidate logout
    client.force_login(cand_user)
    res_c = client.get('/accounts/logout/', follow=True)
    assert res_c.redirect_chain[-1][0] == '/accounts/login/candidate/'

    # Recruiter logout
    client.force_login(rec_user)
    res_r = client.get('/accounts/logout/', follow=True)
    assert res_r.redirect_chain[-1][0] == '/accounts/login/employer/'
