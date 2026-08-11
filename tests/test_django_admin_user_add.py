import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.mark.django_db
def test_django_admin_add_user_form_csrf_and_creation(client):
    """Test Django Admin user creation form submission with CSRF and SSL proxy headers."""
    admin_user = User.objects.create_superuser(
        email="superadmin_test@talentvault.in",
        password="SuperPassword2026!"
    )
    client.force_login(admin_user)
    
    # GET the add user page
    add_url = reverse('admin:accounts_user_add')
    response_get = client.get(add_url, HTTP_X_FORWARDED_PROTO='https', HTTP_HOST='talent-vault.in')
    assert response_get.status_code == 200
    assert b'csrfmiddlewaretoken' in response_get.content
    
    # POST the add user form
    post_data = {
        'email': 'new_recruiter_admin_created@talentvault.in',
        'password1': 'SecurePassword2026!',
        'password2': 'SecurePassword2026!',
        'role': 'RECRUITER',
        'recruiter_status': 'ACTIVE',
        'is_active': 'on',
        '_save': 'Save'
    }
    
    response_post = client.post(
        add_url,
        post_data,
        HTTP_X_FORWARDED_PROTO='https',
        HTTP_HOST='talent-vault.in',
        HTTP_ORIGIN='https://talent-vault.in'
    )
    
    # Should redirect (302) or succeed without 403 Forbidden
    assert response_post.status_code != 403
    assert response_post.status_code in (200, 302)
    
    created = User.objects.filter(email='new_recruiter_admin_created@talentvault.in').first()
    assert created is not None
    assert created.role == User.Role.RECRUITER
    assert created.is_active is True
