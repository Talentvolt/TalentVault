import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from apps.jobs.models import Job
from apps.companies.models import Company

@pytest.mark.django_db
def test_public_job_share_renders_pdf_jd_file(client):
    company = Company.objects.create(name="TechCorp")
    pdf_file = SimpleUploadedFile("Export_Manager_JD.pdf", b"%PDF-1.4 test pdf content", content_type="application/pdf")
    job = Job.objects.create(
        company=company,
        title="Export Manager",
        description="<p>Manual description text</p>",
        location="Mumbai",
        jd_file=pdf_file,
        status=Job.JobStatus.ACTIVE
    )

    url = reverse('frontend:public_job_share', kwargs={'pk': job.pk})
    response = client.get(url)
    assert response.status_code == 200

    # Verify context variables
    assert response.context['jd_file'] is not None
    assert response.context['job_description_file'] is not None
    assert response.context['jd_file_name'].startswith("Export_Manager_JD")
    assert response.context['is_pdf'] is True

    # Verify template rendering
    html = response.content.decode('utf-8')
    assert "Export_Manager_JD" in html
    assert "Preview" in html
    assert "Download" in html
    assert "iframe" in html
    assert "Manual description text" in html

@pytest.mark.django_db
def test_public_job_share_renders_docx_jd_file(client):
    company = Company.objects.create(name="TechCorp")
    docx_file = SimpleUploadedFile("Sales_Director_JD.docx", b"dummy docx bytes", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    job = Job.objects.create(
        company=company,
        title="Sales Director",
        description="<p>Manual description text</p>",
        location="Delhi",
        jd_file=docx_file,
        status=Job.JobStatus.ACTIVE
    )

    url = reverse('frontend:public_job_share', kwargs={'pk': job.pk})
    response = client.get(url)
    assert response.status_code == 200

    # Verify context variables
    assert response.context['jd_file'] is not None
    assert response.context['job_description_file'] is not None
    assert response.context['jd_file_name'].startswith("Sales_Director_JD")
    assert response.context['is_docx'] is True

    # Verify template rendering
    html = response.content.decode('utf-8')
    assert "Sales_Director_JD" in html
    assert "Preview" in html
    assert "Download" in html

@pytest.mark.django_db
def test_public_job_share_without_jd_file(client):
    company = Company.objects.create(name="TechCorp")
    job = Job.objects.create(
        company=company,
        title="Software Engineer",
        description="<p>Only manual description here</p>",
        location="Bangalore",
        status=Job.JobStatus.ACTIVE
    )

    url = reverse('frontend:public_job_share', kwargs={'pk': job.pk})
    response = client.get(url)
    assert response.status_code == 200

    assert response.context['jd_file'] is None
    html = response.content.decode('utf-8')
    assert "Only manual description here" in html

@pytest.mark.django_db
def test_public_job_share_ux_elements(client):
    company = Company.objects.create(name="InnovateTech")
    job = Job.objects.create(
        company=company,
        title="Lead DevOps Engineer",
        description="<p>Full DevOps Responsibilities</p>",
        location="Remote / Mumbai",
        min_experience=4,
        max_experience=8,
        min_salary=15.0,
        max_salary=25.0,
        status=Job.JobStatus.ACTIVE
    )

    url = reverse('frontend:public_job_share', kwargs={'pk': job.pk})
    response = client.get(url)
    assert response.status_code == 200

    html = response.content.decode('utf-8')

    # Checkbox & Disabled Apply button in sidebar
    assert 'id="chk_read_jd"' in html
    assert 'I have read the Job Description.' in html
    assert 'id="btn_sidebar_apply_now"' in html
    assert 'Please confirm that you have read the Job Description.' in html

    # Top summary inside Application Form Modal
    assert 'Lead DevOps Engineer' in html
    assert 'InnovateTech' in html
    assert 'Remote / Mumbai' in html
    assert '4 - 8 Yrs' in html
    assert 'View Job Description' in html

    # Share Buttons
    assert 'btn_copy_link' in html
    assert 'Share on WhatsApp' in html
    assert 'Share via Email' in html
    assert 'Open in New Tab' in html

@pytest.mark.django_db
def test_candidate_find_jobs_renders_view_details_instead_of_direct_easy_apply(client):
    from apps.accounts.models import User
    from apps.candidates.models import CandidateProfile

    company = Company.objects.create(name="AcmeCorp")
    job = Job.objects.create(
        company=company,
        title="Backend Engineer",
        description="Write Django code",
        location="Remote",
        status=Job.JobStatus.ACTIVE
    )

    candidate_user = User.objects.create_user(email="candidate.find@example.com", role=User.Role.CANDIDATE)
    CandidateProfile.objects.create(user=candidate_user, full_name="Candidate Find", location="Remote")

    client.force_login(candidate_user)
    url = reverse('frontend:jobs')
    response = client.get(url)
    assert response.status_code == 200

    html = response.content.decode('utf-8')

    # Verify direct "Easy Apply" is removed from job card and replaced with "View Details"
    assert "Easy Apply" not in html
    assert "View Details" in html
    assert reverse('frontend:public_job_share', kwargs={'pk': job.pk}) in html
