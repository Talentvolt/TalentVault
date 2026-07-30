import pytest
from django.urls import reverse
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile
from apps.notifications.models import CandidateMessage

@pytest.mark.django_db
def test_send_candidate_message(client):
    recruiter = User.objects.create_user(
        email='recruiter_msg@company.com',
        password='Password123!',
        role=User.Role.RECRUITER
    )
    cand_user = User.objects.create_user(
        email='candidate_msg@company.com',
        password='Password123!',
        role=User.Role.CANDIDATE
    )
    cand_profile = CandidateProfile.objects.create(
        user=cand_user,
        full_name="Candidate Tester"
    )

    client.force_login(recruiter)
    url = reverse('frontend:candidate_message_api')

    # Test GET threads
    res_get = client.get(url)
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get['success'] is True

    # Test POST message using recipient_id
    res_post = client.post(url, {
        'recipient_id': str(cand_user.id),
        'candidate_id': str(cand_profile.id),
        'message_text': 'Hello candidate!'
    })
    print("\nPOST RES STATUS:", res_post.status_code)
    print("POST RES DATA:", res_post.content.decode('utf-8'))
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert data_post['success'] is True
    assert CandidateMessage.objects.filter(sender=recruiter, recipient=cand_user).exists()

    # Test POST message using only candidate_id
    res_post2 = client.post(url, {
        'candidate_id': str(cand_profile.id),
        'message_text': 'Second message!'
    })
    assert res_post2.status_code == 200
    assert res_post2.json()['success'] is True

    # Test GET thread for this candidate
    res_thread = client.get(f"{url}?candidate_id={cand_profile.id}")
    assert res_thread.status_code == 200
    data_thread = res_thread.json()
    assert len(data_thread['messages']) == 2
