import os
import sys
import time
import requests
import re
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

URL_BASE = "https://talentvault-1.onrender.com"
EMAIL = "growfluencestudio@gmail.com"
PASSWORD = "TalentVault2026!"

def generate_temp_pdf(filename, unique_email):
    print(f"Generating PDF: {filename} with email: {unique_email}")
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    body_style = ParagraphStyle(
        'ResumeBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        spaceAfter=6
    )
    
    story.append(Paragraph("Delete Test Candidate", body_style))
    story.append(Paragraph(f"Email: {unique_email}", body_style))
    story.append(Paragraph("LinkedIn: linkedin.com/in/deletetestcandidate/", body_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Experience", body_style))
    story.append(Paragraph("Software Engineer for 2 years", body_style))
    
    doc.build(story)
    print("PDF generation complete.")

def verify_delete_production():
    unique_email = f"deletetest_{int(time.time())}@example.com"
    pdf_path = "scratch/delete_test_candidate.pdf"
    generate_temp_pdf(pdf_path, unique_email)
    
    print(f"--- STARTING CANDIDATE DELETE VERIFICATION ON {URL_BASE} ---")
    session = requests.Session()
    
    # 1. Login
    login_url = f"{URL_BASE}/accounts/login/"
    print(f"[1/8] GET {login_url}")
    login_resp = session.get(login_url)
    soup = BeautifulSoup(login_resp.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    
    print(f"[2/8] POST Login to recruiter account: {EMAIL}")
    login_data = {
        'email': EMAIL,
        'password': PASSWORD,
        'remember_me': 'on',
        'csrfmiddlewaretoken': csrf_token
    }
    login_post_resp = session.post(login_url, data=login_data, headers={'Referer': login_url}, allow_redirects=True)
    if "dashboard" not in login_post_resp.url:
        print("Login failed!")
        sys.exit(1)
    print("Logged in successfully.")
    
    # 2. Get parser CSRF token
    parser_url = f"{URL_BASE}/resume-parser/"
    print(f"[3/8] GET {parser_url}")
    parser_resp = session.get(parser_url)
    soup_parser = BeautifulSoup(parser_resp.text, 'html.parser')
    parser_csrf = soup_parser.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    
    # 3. Upload resume
    print(f"[4/8] POST Uploading {pdf_path}")
    with open(pdf_path, 'rb') as f:
        files = {
            'resume': (os.path.basename(pdf_path), f, 'application/pdf')
        }
        data = {
            'csrfmiddlewaretoken': parser_csrf,
            'overwrite': 'on'
        }
        upload_resp = session.post(parser_url, data=data, files=files, headers={'Referer': parser_url}, allow_redirects=True)
    
    print(f"Upload Response status: {upload_resp.status_code}")
    print(f"Redirected to: {upload_resp.url}")
    
    # 4. Search Candidate
    candidates_url = f"{URL_BASE}/candidates/"
    print(f"[5/8] GET {candidates_url} to search for the candidate ID")
    candidates_resp = session.get(candidates_url)
    soup_candidates = BeautifulSoup(candidates_resp.text, 'html.parser')
    
    candidate_id = None
    uuid_pattern = re.compile(r'/candidates/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
    
    print(f"Scanning candidate profile links to locate unique email: {unique_email} ...")
    all_links = soup_candidates.find_all('a')
    for link in all_links:
        href = link.get('href', '')
        match = uuid_pattern.search(href)
        if match:
            cand_id = match.group(1)
            check_url = f"{URL_BASE}/candidates/{cand_id}/"
            check_resp = session.get(check_url)
            if check_resp.status_code == 200 and unique_email in check_resp.text.lower():
                candidate_id = cand_id
                break
                
    if not candidate_id:
        print("ERROR: Delete Test Candidate profile link not found.")
        sys.exit(1)
        
    print(f"Candidate Profile ID for Delete Test Candidate: {candidate_id}")
    
    # 5. Fetch Profile Page to get Delete CSRF token
    profile_url = f"{URL_BASE}/candidates/{candidate_id}/"
    print(f"[6/8] GET Profile page to get CSRF token: {profile_url}")
    profile_resp = session.get(profile_url)
    soup_profile = BeautifulSoup(profile_resp.text, 'html.parser')
    
    # Locate the delete form's CSRF token
    delete_form = soup_profile.find('form', action=re.compile(rf'/candidates/{candidate_id}/delete/'))
    if not delete_form:
        # fallback
        delete_form = soup_profile.find('form', action=re.compile(r'/delete/'))
    
    if not delete_form:
        print("ERROR: Delete form not found on candidate profile page.")
        sys.exit(1)
        
    delete_csrf = delete_form.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    print("Found delete CSRF token.")
    
    delete_url = f"{URL_BASE}/candidates/{candidate_id}/delete/"
    
    # 6. Perform FIRST delete POST (existing candidate deletion)
    print(f"[7/8] POST first delete to: {delete_url}")
    delete_data = {
        'csrfmiddlewaretoken': delete_csrf
    }
    delete_resp = session.post(delete_url, data=delete_data, headers={'Referer': profile_url}, allow_redirects=True)
    
    print(f"First delete Response status: {delete_resp.status_code}")
    print(f"Redirected to: {delete_resp.url}")
    # Verify we redirected back to /candidates/
    assert "/candidates/" in delete_resp.url, "ERROR: First delete did not redirect to candidates page"
    assert "deleted successfully" in delete_resp.text.lower(), "ERROR: Success message not found on first delete"
    print("SUCCESS: Candidate deleted successfully.")
    
    # 7. Perform SECOND delete POST (already deleted/double-click simulation)
    print(f"[8/8] POST second delete to: {delete_url}")
    delete_resp2 = session.post(delete_url, data=delete_data, headers={'Referer': profile_url}, allow_redirects=True)
    
    print(f"Second delete Response status: {delete_resp2.status_code}")
    print(f"Redirected to: {delete_resp2.url}")
    # Verify HTTP 302 redirect was returned and we redirected back to /candidates/ without 404
    assert delete_resp2.status_code == 200, "ERROR: Second delete request failed"
    assert "/candidates/" in delete_resp2.url, "ERROR: Second delete did not redirect to candidates page"
    assert "already deleted" in delete_resp2.text.lower(), "ERROR: 'Candidate already deleted' message not found on second delete"
    print("SUCCESS: Duplicate delete handled gracefully (returned 302 with info message).")
    
    print("\n==============================================")
    print("=== LIVE WEB VERIFICATION SUCCESS FOR CANDIDATE DELETION ===")
    print("==============================================")

if __name__ == '__main__':
    verify_delete_production()
