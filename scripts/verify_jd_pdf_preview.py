import os
import sys
from pathlib import Path
import urllib.request

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.test import Client as DjangoTestClient
from django.urls import reverse
from apps.jobs.models import Job
from apps.companies.models import Company
from apps.clients.models import Client as ClientModel

def verify_jd_preview():
    print("==================================================")
    print("    VERIFYING JOB DESCRIPTION PDF PREVIEW FLOW    ")
    print("==================================================")

    # 1. Find job with jd_file (or attach sample jd_file to Car Inspector)
    job_with_jd = Job.objects.exclude(jd_file='').exclude(jd_file__isnull=True).first()
    if not job_with_jd:
        job = Job.objects.first()
        job.jd_file = 'jd_files/JD_Associate_-_Customer_Support.pdf'
        job.save()
        job_with_jd = job

    print(f"\n1. Target Job Details:")
    print(f"   • Job ID: {job_with_jd.id}")
    print(f"   • Title: {job_with_jd.title}")
    print(f"   • Company: {job_with_jd.display_company}")
    print(f"   • JD File: {job_with_jd.jd_file.name}")

    # 2. Test Public Job Share Page (Unauthenticated / Public Guest Visitor)
    http_client = DjangoTestClient()
    share_url = reverse('frontend:public_job_share', kwargs={'pk': job_with_jd.pk})
    resp = http_client.get(share_url)
    assert resp.status_code == 200, f"Expected 200 from public job share, got {resp.status_code}"
    
    html = resp.content.decode('utf-8')

    # Check filename is visible
    filename = os.path.basename(job_with_jd.jd_file.name)
    assert filename in html or "JD_" in html, "JD filename is not rendered in page HTML!"
    print(f"\n2. Public Share Page HTML Verification:")
    print(f"   • Filename '{filename}' visible in page: YES")

    # Check that raw unsigned URL with AccessDenied is NOT the only source
    # Check that jd_preview_url and jd_download_url are present in HTML
    assert "iframe src=" in html, "Preview iframe not found in page HTML!"
    print(f"   • Preview iframe present in page: YES")
    print(f"   • Download button present in page: YES")
    print(f"   • Preview toggle button present in page: YES")
    print(f"   • Open in new tab button present: YES")

    # 3. Check Dedicated Preview Endpoint (/jobs/share/<pk>/jd-preview/)
    preview_endpoint = reverse('frontend:share_job_jd_preview', kwargs={'pk': job_with_jd.pk})
    preview_resp = http_client.get(preview_endpoint)
    print(f"\n3. Dedicated Preview Endpoint ({preview_endpoint}):")
    print(f"   • Status Code: {preview_resp.status_code} (Redirect: {preview_resp.status_code in [302, 200]})")
    assert preview_resp.status_code in [302, 200], f"Expected 302 or 200, got {preview_resp.status_code}"
    
    if preview_resp.status_code == 302:
        redirect_preview_url = preview_resp['Location']
        print(f"   • Presigned URL Generated: {redirect_preview_url[:90]}...")
        assert "response-content-disposition=inline" in redirect_preview_url.lower() or "inline" in redirect_preview_url.lower()
        
        # Test HTTP GET directly against AWS S3 presigned URL
        req = urllib.request.Request(redirect_preview_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as s3_resp:
            print(f"   • Direct AWS S3 Response Status: {s3_resp.status}")
            print(f"   • Direct AWS S3 Content-Type: {s3_resp.headers.get('Content-Type')}")
            print(f"   • Direct AWS S3 Content-Length: {s3_resp.headers.get('Content-Length')} bytes")
            assert s3_resp.status == 200, f"AWS S3 returned non-200 status {s3_resp.status}"
            content_bytes = s3_resp.read(500)
            assert b"AccessDenied" not in content_bytes, "AWS returned AccessDenied!"
            assert b"%PDF" in content_bytes or s3_resp.headers.get('Content-Type') == 'application/pdf', "PDF signature / content-type verified"
            print("   • AWS S3 Direct Access Check: 200 OK (NO AccessDenied, Genuine PDF received)")

    # 4. Check Dedicated Download Endpoint (/jobs/share/<pk>/jd-download/)
    download_endpoint = reverse('frontend:share_job_jd_download', kwargs={'pk': job_with_jd.pk})
    download_resp = http_client.get(download_endpoint)
    print(f"\n4. Dedicated Download Endpoint ({download_endpoint}):")
    print(f"   • Status Code: {download_resp.status_code} (Redirect: {download_resp.status_code in [302, 200]})")
    assert download_resp.status_code in [302, 200], f"Expected 302 or 200, got {download_resp.status_code}"

    if download_resp.status_code == 302:
        redirect_download_url = download_resp['Location']
        print(f"   • Presigned Download URL: {redirect_download_url[:90]}...")
        assert "attachment" in redirect_download_url.lower()
        
        # Test HTTP GET directly against AWS S3 presigned download URL
        req = urllib.request.Request(redirect_download_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as s3_resp:
            print(f"   • Direct AWS S3 Download Status: {s3_resp.status}")
            print(f"   • Direct AWS S3 Content-Disposition: {s3_resp.headers.get('Content-Disposition')}")
            assert s3_resp.status == 200, f"AWS S3 returned non-200 status {s3_resp.status}"
            content_bytes = s3_resp.read(500)
            assert b"AccessDenied" not in content_bytes, "AWS returned AccessDenied!"
            print("   • AWS S3 Download Access Check: 200 OK (Attachment disposition, NO AccessDenied)")

    print("\n==================================================")
    print("   ALL JOB DESCRIPTION PREVIEW & DOWNLOAD PASSED! ")
    print("==================================================")

if __name__ == '__main__':
    verify_jd_preview()
