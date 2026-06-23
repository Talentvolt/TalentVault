import requests
import re
import os

def verify_experience_parsing():
    print("=" * 60)
    print("Verifying Experience Parsing & Timeline Rendering in Production")
    print("=" * 60)
    
    session = requests.Session()
    login_url = "https://talentvault-1.onrender.com/accounts/login/"
    
    # 1. Login
    print("GET login page...")
    r = session.get(login_url)
    csrf_token = session.cookies.get('csrftoken')
    if not csrf_token:
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
        if match:
            csrf_token = match.group(1)
            
    payload = {
        "email": "growfluencestudio@gmail.com",
        "password": "TalentVault2026!",
        "csrfmiddlewaretoken": csrf_token,
        "remember_me": "on"
    }
    print("Logging in...")
    session.post(login_url, data=payload, headers={"Referer": login_url})
    
    # 2. Get fresh CSRF token
    parser_url = "https://talentvault-1.onrender.com/resume-parser/"
    r_parser = session.get(parser_url)
    csrf_token = session.cookies.get('csrftoken')
    if not csrf_token:
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r_parser.text)
        if match:
            csrf_token = match.group(1)
            
    # 3. Upload Ramanjeet's resume with overwrite=on to parse experience again
    pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Resume_Ramanjeet.pdf')
    print("Uploading resume to parse experience:", pdf_path)
    
    with open(pdf_path, 'rb') as f:
         files = {'resume': ('Resume_Ramanjeet.pdf', f, 'application/pdf')}
         post_data = {
             'csrfmiddlewaretoken': csrf_token,
             'overwrite': 'on'
         }
         r_upload = session.post(parser_url, data=post_data, files=files, headers={"Referer": parser_url})
         
    print("Upload Response Code:", r_upload.status_code)
    
    # 4. Get Candidate List page and find Ramanjeet's detail link
    candidates_url = "https://talentvault-1.onrender.com/candidates/"
    print("Fetching candidates list page...")
    r_candidates = session.get(candidates_url)
    
    # Precise match
    matches = re.findall(r'href="(/candidates/[0-9a-fA-F-]+/)"[^>]*>(.*?)</a>', r_candidates.text, re.DOTALL)
    detail_path = None
    for path, name in matches:
         if "Ramanjeet" in name or "Maurya" in name:
              detail_path = path
              break
              
    if not detail_path:
         print("Ramanjeet profile link not found.")
         return
         
    detail_url = f"https://talentvault-1.onrender.com{detail_path}"
    print(f"Fetching Candidate Detail page: {detail_url}")
    
    r_detail = session.get(detail_url)
    detail_html = r_detail.text
    
    # 5. Verify parsed work experiences on Candidate Detail page
    print("\n--- Live Production Experience Rendering Verification ---")
    
    # Verify we don't have many jobs with Company name = "Company"
    has_company_placeholder = re.search(r'at\s+Company\b', detail_html, re.I)
    
    # Verify presence of real company names
    has_concentrix = "Concentrix" in detail_html
    has_amazon = "Amazon" in detail_html
    
    print(f"Found 'Concentrix' experience: {has_concentrix}")
    print(f"Found 'Amazon' experience:     {has_amazon}")
    print(f"Found 'Company' placeholder:   {bool(has_company_placeholder)}")
    
    if has_concentrix and has_amazon and not has_company_placeholder:
         print("\nVERIFICATION RESULT: SUCCESS! Live production Candidate Profile shows correctly structured experiences and real company names without placeholder jobs!")
    else:
         print("\nVERIFICATION RESULT: FAILURE! Production Candidate Profile experiences do not render correctly or still contain placeholder 'Company' values.")

if __name__ == "__main__":
    verify_experience_parsing()
