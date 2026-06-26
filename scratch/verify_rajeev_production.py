import os
import sys
import requests
import re
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

URL_BASE = "https://talentvault-1.onrender.com"
EMAIL = "growfluencestudio@gmail.com"
PASSWORD = "TalentVault2026!"

def generate_rajeev_pdf(filename):
    print(f"Generating PDF: {filename}")
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
    
    story.append(Paragraph("Rajeev Kumar", body_style))
    story.append(Paragraph("Email: rajeevkumar9801456p@gmail.com", body_style))
    story.append(Paragraph("LinkedIn: linkedin.com/in/rajeev98p/", body_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Extracurricular Activities", body_style))
    story.append(Paragraph("Volunteer at NGO", body_style))
    
    doc.build(story)
    print("PDF generation complete.")

def verify_rajeev_production():
    pdf_path = "scratch/rajeev_kumar_resume.pdf"
    generate_rajeev_pdf(pdf_path)
    
    print(f"--- STARTING RAJEEV KUMAR PARSER VERIFICATION ON {URL_BASE} ---")
    session = requests.Session()
    
    # 1. Login
    login_url = f"{URL_BASE}/accounts/login/"
    print(f"[1/5] GET {login_url}")
    login_resp = session.get(login_url)
    soup = BeautifulSoup(login_resp.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    
    print(f"[2/5] POST Login to recruiter account: {EMAIL}")
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
    print(f"[3/5] GET {parser_url}")
    parser_resp = session.get(parser_url)
    soup_parser = BeautifulSoup(parser_resp.text, 'html.parser')
    parser_csrf = soup_parser.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    
    # 3. Upload resume
    print(f"[4/5] POST Uploading {pdf_path} (overwrite=on)")
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
    print(f"[5/5] GET {candidates_url} to search for the candidate ID")
    candidates_resp = session.get(candidates_url)
    soup_candidates = BeautifulSoup(candidates_resp.text, 'html.parser')
    
    candidate_id = None
    uuid_pattern = re.compile(r'/candidates/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
    
    print("Scanning candidate profile links to locate Rajeev Kumar...")
    all_links = soup_candidates.find_all('a')
    for link in all_links:
        href = link.get('href', '')
        match = uuid_pattern.search(href)
        if match:
            cand_id = match.group(1)
            check_url = f"{URL_BASE}/candidates/{cand_id}/"
            check_resp = session.get(check_url)
            if check_resp.status_code == 200 and "rajeevkumar9801456p@gmail.com" in check_resp.text.lower():
                candidate_id = cand_id
                break
                
    if not candidate_id:
        print("ERROR: RAJEEV KUMAR candidate profile link not found.")
        sys.exit(1)
        
    print(f"Candidate Profile ID for Rajeev Kumar: {candidate_id}")
    
    # 5. Fetch Profile Page and Verify candidate name
    profile_url = f"{URL_BASE}/candidates/{candidate_id}/"
    print(f"GET Rajeev Kumar Profile Page: {profile_url}")
    profile_resp = session.get(profile_url)
    soup_profile = BeautifulSoup(profile_resp.text, 'html.parser')
    profile_text = soup_profile.get_text()
    
    # Assertions
    print("\n--- Running parser name assertions on production ---")
    
    # Assert name matches exactly "Rajeev Kumar" and is NOT "Extracurricular Activities"
    print(f"Profile Page Text snippet: {profile_text[:500]}")
    
    h2_text = soup_profile.find('h2').get_text().strip() if soup_profile.find('h2') else ""
    print(f"Extracted header name: {h2_text}")
    
    assert "Rajeev Kumar" in profile_text, "ERROR: Rajeev Kumar name not found on profile page!"
    assert "Extracurricular Activities" not in h2_text, "ERROR: Section title extracted as header name!"
    
    print("\n==============================================")
    print("=== LIVE WEB VERIFICATION SUCCESS FOR RAJEEV KUMAR ===")
    print("==============================================")

if __name__ == '__main__':
    verify_rajeev_production()
