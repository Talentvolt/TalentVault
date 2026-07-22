import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from apps.candidates.models import CandidateProfile

User = get_user_model()

@pytest.mark.django_db
def test_candidate_normal_signup(client):
    import uuid
    unique_id = uuid.uuid4().hex[:8]
    email = f'normal_{unique_id}@example.com'
    phone = f'99{uuid.uuid4().int % 100000000:08d}'
    url = reverse('candidate_signup')
    signup_data = {
        'first_name': 'Normal',
        'last_name': 'Candidate',
        'email': email,
        'role': User.Role.CANDIDATE,
        'password': 'Password123!',
        'confirm_password': 'Password123!',
        'phone_number': phone,
        'location': 'Bangalore',
        'experience': 'fresher',
        'accept_terms': True,
    }
    response = client.post(url, signup_data)
    user = User.objects.filter(email=email).first()
    if user is None and hasattr(response, 'context') and response.context and 'form' in response.context:
        print("SIGNUP FORM ERRORS:", response.context['form'].errors)
    assert response.status_code in [200, 302]
    assert user is not None
    assert user.role == User.Role.CANDIDATE


@pytest.mark.django_db
def test_existing_candidate_login(client):
    user = User.objects.create_user(
        email='loginuser@example.com',
        password='Password123!',
        first_name='Login',
        last_name='User',
        role=User.Role.CANDIDATE
    )
    user.is_verified = True
    user.is_active = True
    user.save()
    CandidateProfile.objects.create(user=user, full_name='Login User')
    
    login_url = reverse('candidate_login')
    response = client.post(login_url, {'email': 'loginuser@example.com', 'password': 'Password123!'})
    assert response.status_code == 302


@pytest.mark.django_db
def test_candidate_profile_page_missing_resume(client):
    user = User.objects.create_user(
        email='missingresume@example.com',
        password='Password123!',
        first_name='Missing',
        last_name='Resume',
        role=User.Role.CANDIDATE
    )
    user.is_verified = True
    user.is_active = True
    user.save()
    
    profile = CandidateProfile.objects.create(
        user=user,
        full_name='Missing Resume',
        resume='resumes/non_existent_file.pdf'
    )
    
    client.force_login(user)
    profile_url = reverse('frontend:candidate_profile')
    
    # Profile page should load with status 200 without raising FileNotFoundError
    response = client.get(profile_url)
    assert response.status_code == 200
    assert b"Resume not available" in response.content or b"No Resume Uploaded" in response.content


@pytest.mark.django_db
def test_candidate_profile_page_existing_resume(client):
    user = User.objects.create_user(
        email='withresume@example.com',
        password='Password123!',
        first_name='With',
        last_name='Resume',
        role=User.Role.CANDIDATE
    )
    user.is_verified = True
    user.is_active = True
    user.save()
    
    profile = CandidateProfile.objects.create(
        user=user,
        full_name='With Resume'
    )
    profile.resume.save("test_valid_resume.pdf", ContentFile(b"%PDF-1.4 test resume content"))
    
    client.force_login(user)
    profile_url = reverse('frontend:candidate_profile')
    
    response = client.get(profile_url)
    assert response.status_code == 200
    assert profile.has_resume is True
    assert "KB" in profile.resume_size_display
