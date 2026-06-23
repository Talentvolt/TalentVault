import requests
import re
import os

def test_production_parser():
    print("=" * 60)
    print("Verifying Live Resume Parser in Production")
    print("=" * 60)
    
    session = requests.Session()
    login_url = "https://talentvault-1.onrender.com/accounts/login/"
    
    # 1. Get CSRF Token
    print("GET login page...")
    r = session.get(login_url)
    if r.status_code != 200:
        print(f"Failed to GET login page. Status: {r.status_code}")
        return
        
    csrf_token = session.cookies.get('csrftoken')
    if not csrf_token:
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
        if match:
            csrf_token = match.group(1)
            
    # 2. Login
    payload = {
        "email": "growfluencestudio@gmail.com",
        "password": "TalentVault2026!",
        "csrfmiddlewaretoken": csrf_token,
        "remember_me": "on"
    }
    
    print("POSTing login credentials...")
    r_post = session.post(login_url, data=payload, headers={"Referer": login_url})
    if "dashboard" not in r_post.url.lower():
        print("Login failed.")
        return
    print("Login successful!")
    
    # Get new CSRF token for authenticated session
    parser_url = "https://talentvault-1.onrender.com/resume-parser/"
    print("GET parser page to fetch CSRF token and current stats...")
    r_parser = session.get(parser_url)
    
    csrf_token = session.cookies.get('csrftoken')
    if not csrf_token or csrf_token == payload["csrfmiddlewaretoken"]:
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r_parser.text)
        if match:
            csrf_token = match.group(1)
            
    # Print duplicate counter
    dup_match = re.search(r'Total Duplicates Found Today[^\d]*(\d+)', r_parser.text)
    if dup_match:
         print("Current duplicates count today in production:", dup_match.group(1))
    else:
         print("Could not find duplicates count in parser HTML.")

    # 3. Post a resume file
    # We will upload Laxmi_Sudharshan_DA_resume_Jan15th.pdf
    pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Laxmi_Sudharshan_DA_resume_Jan15th.pdf')
    print("Uploading file to production parser:", pdf_path)
    
    # We'll use a unique email by editing user if they already exist, or we can use overwrite=on
    # To test new creation, we'll run with overwrite=on first or just check the result redirect URL
    with open(pdf_path, 'rb') as f:
         files = {'resume': ('Laxmi_Sudharshan_DA_resume_Jan15th.pdf', f, 'application/pdf')}
         post_data = {
             'csrfmiddlewaretoken': csrf_token,
             'overwrite': 'on'  # Use overwrite to ensure it proceeds and does not block if already uploaded
         }
         print("Posting file...")
         r_upload = session.post(parser_url, data=post_data, files=files, headers={"Referer": parser_url})
         
    print("Response URL after upload:", r_upload.url)
    print("Response Status Code:", r_upload.status_code)
    
    # Check messages in response (redirects to candidate search page)
    # Search for Django success messages in response HTML
    success_match = re.search(r'class="[^"]*success[^"]*"[^>]*>(.*?)</div>', r_upload.text, re.DOTALL | re.I)
    if success_match:
         print("Success alert message found:", success_match.group(1).strip())
    else:
         # Try printing any alert messages
         alert_matches = re.findall(r'class="[^"]*alert[^"]*"[^>]*>(.*?)</div>', r_upload.text, re.DOTALL | re.I)
         for alert in alert_matches:
              print("Alert message found:", alert.strip())
              
    # Fetch candidate list page to verify if Laxmi Sudharshan is listed
    candidates_url = "https://talentvault-1.onrender.com/candidates/"
    print("Fetching candidates list page...")
    r_candidates = session.get(candidates_url)
    if "Laxmi" in r_candidates.text or "Sudharshan" in r_candidates.text:
         print("VERIFICATION RESULT: SUCCESS! Candidate profile is now visible on the Candidates List page in production!")
    else:
         print("VERIFICATION RESULT: FAILURE! Candidate was not found in the candidates list.")

if __name__ == "__main__":
    test_production_parser()
