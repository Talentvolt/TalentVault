import requests
import re

def verify_production():
    print("=" * 60)
    print("Verifying Live Render Production Candidate Profile Details")
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
        # Try extracting from HTML
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
    
    # 3. Fetch Candidates Page
    candidates_url = "https://talentvault-1.onrender.com/candidates/"
    print(f"Fetching candidates page to extract candidate ID...")
    r_candidates = session.get(candidates_url)
    html_list = r_candidates.text
    
    # Match candidate details link
    matches = re.findall(r'href="/candidates/([0-9a-fA-F-]+)/"', html_list)
    if not matches:
        print("No candidate IDs found.")
        return
        
    candidate_id = matches[0]
    print(f"Found Candidate ID: {candidate_id}")
    
    # 4. Fetch Candidate Profile Detail Page
    detail_url = f"https://talentvault-1.onrender.com/candidates/{candidate_id}/"
    print(f"Fetching profile page: {detail_url}")
    r_detail = session.get(detail_url)
    html_detail = r_detail.text
    
    # Verify Work Experience timeline
    has_work_timeline = "work-experience-timeline" in html_detail
    has_exp_entry = "experience-entry" in html_detail
    has_duration = "experience-duration-text" in html_detail
    has_timeline_dot = "Timeline bullet marker" in html_detail
    
    # Verify Preview & Download Resume
    has_preview_tab = 'target="_blank"' in html_detail and 'resume/preview/' in html_detail
    has_download_link = 'resume/download/' in html_detail
    has_missing_warning = "Resume not found. Please re-upload." in html_detail
    
    # Verify Share Link
    has_share_url = "public_share_url" in html_detail or "shareLinkInput" in html_detail
    has_share_btn = "Open shared profile in new tab" in html_detail
    
    print("-" * 60)
    print(f"Work Experience timeline container: {has_work_timeline}")
    print(f"Experience entry layout:           {has_exp_entry}")
    print(f"Duration text calculation tag:      {has_duration}")
    print(f"Timeline bullet marker:            {has_timeline_dot}")
    print(f"Preview Resume opens in new tab:    {has_preview_tab}")
    print(f"Download Resume link present:       {has_download_link}")
    print(f"Missing resume warning present:     {has_missing_warning}")
    print(f"Share Profile link input:           {has_share_url}")
    print(f"Open shared profile button:        {has_share_btn}")
    print("-" * 60)
    
    if (has_work_timeline and has_duration and (has_preview_tab or has_missing_warning) and has_share_url):
        print("VERIFICATION RESULT: SUCCESS! Candidate profile page Work Experience timeline and links are live on Render!")
    else:
        print("VERIFICATION RESULT: FAILURE! Production detail page does not match expected layout changes.")

if __name__ == "__main__":
    verify_production()
