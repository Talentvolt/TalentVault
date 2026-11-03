import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import User
from apps.candidates.models import CandidateProfile, CandidateSkill
from apps.notifications.models import EmailTemplate, EmailLog
from apps.notifications.services import seed_default_email_templates, render_email_content, send_ats_email


@pytest.mark.django_db
class TestATSEmailCenter:
    
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.recruiter = User.objects.create_user(
            email="recruiter@talentvault.com",
            password="password123",
            role=User.Role.RECRUITER,
            recruiter_status=User.RecruiterStatus.ACTIVE
        )
        from apps.notifications.models import RecruiterEmailAccount
        RecruiterEmailAccount.objects.create(
            recruiter=self.recruiter,
            account_type='SMTP',
            provider='SMTP',
            email_address='recruiter@talentvault.com',
            smtp_host='smtp.mailprovider.com',
            is_verified=True,
            is_default=True
        )
        self.candidate_user = User.objects.create_user(
            email="candidate@talentvault.com",
            password="password123",
            role=User.Role.CANDIDATE
        )
        self.candidate = CandidateProfile.objects.create(
            user=self.candidate_user,
            full_name="Rajesh Kumar",
            total_experience=5,
            location="Bangalore",
            resume=SimpleUploadedFile("resume.pdf", b"PDF dummy content", content_type="application/pdf")
        )
        CandidateSkill.objects.create(profile=self.candidate, skill_name="Python")
        CandidateSkill.objects.create(profile=self.candidate, skill_name="Django")

    def test_seed_and_15_templates(self):
        seed_default_email_templates()
        templates = EmailTemplate.objects.all()
        assert templates.count() >= 15
        
        # Verify specific templates exist
        assert EmailTemplate.objects.filter(name="Candidate Shortlist to Client").exists()
        assert EmailTemplate.objects.filter(name="Candidate Rejection").exists()
        assert EmailTemplate.objects.filter(name="Candidate Invitation").exists()

    def test_placeholder_replacement(self):
        tpl_body = "Hello {{client_name}}, Candidate {{candidate_name}} has {{skills}} with {{experience}} experience at {{location}}. Profile: {{candidate_profile_url}}."
        rendered = render_email_content(
            tpl_body,
            candidate=self.candidate,
            client_name="Acme Corp",
            recruiter=self.recruiter
        )
        assert "Acme Corp" in rendered
        assert "Rajesh Kumar" in rendered
        assert "Python" in rendered
        assert "5" in rendered
        assert "Bangalore" in rendered
        assert "https://talentvault.in/candidates/" in rendered

    def test_send_ats_email_with_tracking_and_attachments(self, client):
        seed_default_email_templates()
        
        # Test sending ATS email service function
        email_log, success, msg = send_ats_email(
            sender=self.recruiter,
            recipient_email="client@acme.com",
            subject="Shortlist for Python Developer",
            body="Dear Hiring Manager,\nPlease find candidate profile attached.",
            cc="manager@talentvault.com",
            bcc="audit@talentvault.com",
            template_name="Candidate Shortlist to Client",
            candidate_ids=[str(self.candidate.id)],
            attachments=[self.candidate.resume]
        )
        
        assert success is True
        assert email_log.status == 'SENT'
        assert email_log.recipient_email == "client@acme.com"
        assert email_log.has_attachment is True
        assert email_log.tracking_uuid is not None

    def test_email_tracking_endpoints(self, client):
        # Create an email log entry
        log = EmailLog.objects.create(
            sender=self.recruiter,
            recipient_email="tracktest@acme.com",
            subject="Tracking Test",
            body="Test body",
            status='SENT'
        )
        
        # Test Open Tracking Pixel Endpoint
        open_url = reverse('notifications:track_open', kwargs={'uuid': log.tracking_uuid})
        response = client.get(open_url)
        assert response.status_code == 200
        assert response['Content-Type'] == 'image/gif'
        
        log.refresh_from_db()
        assert log.open_count == 1
        assert log.status == 'OPENED'

        # Test Click Tracking Endpoint
        click_url = reverse('notifications:track_click', kwargs={'uuid': log.tracking_uuid}) + "?url=https://google.com"
        response = client.get(click_url)
        assert response.status_code == 302
        
        log.refresh_from_db()
        assert log.click_count == 1
        assert log.status == 'CLICKED'

    def test_duplicate_sending_protection(self):
        # Send first email
        _, success1, _ = send_ats_email(
            sender=self.recruiter,
            recipient_email="dupe@acme.com",
            subject="Same Subject",
            body="Body content"
        )
        assert success1 is True

        # Attempt sending duplicate within window via view logic
        client = pytest.importorskip("django.test").Client()
        client.force_login(self.recruiter)
        
        response = client.post(reverse('frontend:email_campaigns'), {
            'action': 'send',
            'subject': 'Same Subject',
            'body': 'Body content',
            'recipients': [str(self.candidate.id)]
        })
        assert response.status_code == 302
        
        # Check that duplicate log was not created (only 1 log should exist for dupe@acme.com with Same Subject within 5 mins)
        logs_count = EmailLog.objects.filter(recipient_email="dupe@acme.com", subject="Same Subject").count()
        assert logs_count == 1

    def test_template_api_crud(self, client):
        client.force_login(self.recruiter)
        api_url = reverse('notifications:email_templates_api')
        
        # Get templates
        res = client.get(api_url)
        assert res.status_code == 200
        data = res.json()
        assert data['success'] is True
        assert len(data['templates']) >= 15

        # Create custom template
        create_res = client.post(api_url, {
            'action': 'create',
            'name': 'Custom Test Template',
            'category': 'CLIENT',
            'subject': 'Custom Subject',
            'body': 'Custom Body {{candidate_name}}'
        }, HTTP_X_CSRFTOKEN='testtoken')
        assert create_res.status_code == 200
        assert create_res.json()['success'] is True
        
        tpl = EmailTemplate.objects.get(name='Custom Test Template')
        
        # Duplicate template
        dup_res = client.post(api_url, {
            'action': 'duplicate',
            'template_id': str(tpl.id)
        }, HTTP_X_CSRFTOKEN='testtoken')
        assert dup_res.status_code == 200
        assert EmailTemplate.objects.filter(name='Custom Test Template (Copy)').exists()

        # Delete template
        del_res = client.post(api_url, {
            'action': 'delete',
            'template_id': str(tpl.id)
        }, HTTP_X_CSRFTOKEN='testtoken')
        assert del_res.status_code == 200
        assert not EmailTemplate.objects.filter(id=tpl.id).exists()
