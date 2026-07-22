import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount, SocialLogin
from apps.accounts.adapters import CandidateSocialAccountAdapter
from apps.candidates.models import CandidateProfile

User = get_user_model()

@pytest.mark.django_db
def test_candidate_social_account_adapter_populate_user():
    adapter = CandidateSocialAccountAdapter()
    sociallogin = MagicMock()
    
    # Mock user creation
    user = User(email="newcandidate@example.com")
    
    # Populate user using the adapter
    populated_user = adapter.populate_user(None, sociallogin, {})
    
    assert populated_user.role == User.Role.CANDIDATE
    assert populated_user.is_verified is True
    assert populated_user.is_active is True


@pytest.mark.django_db
def test_candidate_social_account_adapter_populate_user_profile():
    adapter = CandidateSocialAccountAdapter()
    
    # Create user with role candidate
    user = User.objects.create(
        email="profilecand@example.com",
        role=User.Role.CANDIDATE,
        first_name="First",
        last_name="Last"
    )
    
    sociallogin = MagicMock()
    sociallogin.account.extra_data = {
        'name': 'First Last',
        'given_name': 'First',
        'family_name': 'Last',
        'picture': 'https://example.com/avatar.jpg'
    }
    
    # Mock requests.get for image download
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake image bytes"
    
    with patch('requests.get', return_value=mock_response) as mock_get:
        adapter.populate_user_profile(user, sociallogin)
        mock_get.assert_called_once_with('https://example.com/avatar.jpg', timeout=10)
        
    # Verify User profile picture url is stored
    user.refresh_from_db()
    assert user.profile_picture == 'https://example.com/avatar.jpg'
    
    # Verify CandidateProfile was created
    profile = CandidateProfile.objects.get(user=user)
    assert profile.full_name == "First Last"
    assert profile.location == "Bangalore, India"
    assert profile.profile_photo is not None
    assert profile.profile_photo.read() == b"fake image bytes"


@pytest.mark.django_db
def test_candidate_social_account_adapter_pre_social_login_linking():
    adapter = CandidateSocialAccountAdapter()
    
    # 1. Create an existing user with email/password (no social account linked)
    existing_user = User.objects.create_user(
        email="existing@example.com",
        password="password123",
        first_name="Existing",
        last_name="User",
        role=User.Role.CANDIDATE
    )
    
    # Ensure no social account exists initially
    assert SocialAccount.objects.filter(user=existing_user).count() == 0
    
    # 2. Mock sociallogin object for google login with same email
    sociallogin = MagicMock()
    sociallogin.is_existing = False
    sociallogin.user = User(email="existing@example.com")
    sociallogin.account.provider = "google"
    sociallogin.account.uid = "google-uid-123"
    sociallogin.account.extra_data = {
        'name': 'Existing User',
        'picture': 'https://example.com/avatar.jpg'
    }
    
    # Call pre_social_login
    adapter.pre_social_login(None, sociallogin)
    
    # Check that sociallogin.user has been set to the existing user
    assert sociallogin.user == existing_user
    
    # Check that SocialAccount has been created and linked to the existing user
    social_account = SocialAccount.objects.get(user=existing_user)
    assert social_account.provider == "google"
    assert social_account.uid == "google-uid-123"


@pytest.mark.django_db
def test_google_oauth_initiate_params(client):
    from urllib.parse import urlparse, parse_qs
    response = client.get('/accounts/login/google/')
    assert response.status_code == 302
    parsed_url = urlparse(response.url)
    query_params = parse_qs(parsed_url.query)
    
    assert query_params.get('prompt', [None])[0] == 'select_account'
    assert query_params.get('access_type', [None])[0] == 'offline'
    assert query_params.get('include_granted_scopes', [None])[0] == 'true'


@pytest.mark.django_db
def test_adapter_pre_social_login_account_switching():
    adapter = CandidateSocialAccountAdapter()
    
    user1 = User.objects.create_user(
        email="user1@example.com",
        password="password123",
        role=User.Role.CANDIDATE
    )
    
    request = MagicMock()
    request.user = user1
    
    sociallogin = MagicMock()
    sociallogin.is_existing = False
    sociallogin.user = User(email="user2@example.com")
    sociallogin.account.provider = "google"
    sociallogin.account.uid = "google-uid-user2"
    sociallogin.account.extra_data = {'email': 'user2@example.com'}
    
    with patch('django.contrib.auth.logout') as mock_logout:
        adapter.pre_social_login(request, sociallogin)
        mock_logout.assert_called_once_with(request)

