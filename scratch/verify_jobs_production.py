import requests
import re
import json

def verify_production_jobs():
    print("=" * 60)
    print("Verifying Jobs Fixes + Improvements on Production")
    print("=" * 60)
    
    session = requests.Session()
    login_url = "https://talentvault-1.onrender.com/accounts/login/"
    
    # 1. Login
    print("Fetching login page...")
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
    print("Logging in to Production...")
    login_resp = session.post(login_url, data=payload, headers={"Referer": login_url})
    if login_resp.status_code == 200 and "login" in login_resp.url:
         print("ERROR: Login failed!")
         return
    print("Login successful!")
    
    # 2. Verify Job List Page UI & LPA Salary Format
    jobs_url = "https://talentvault-1.onrender.com/jobs/"
    print(f"Fetching Jobs List Page: {jobs_url} ...")
    r_jobs = session.get(jobs_url)
    
    # Let's search for the salary range display in the table
    # Expected format: e.g. <span class="fw-bold text-success small">5 LPA - 7.5 LPA</span>
    salaries = re.findall(r'<span class="fw-bold text-success small">([^<]+)</span>', r_jobs.text)
    print(f"Found salary ranges on page: {salaries}")
    
    if salaries:
        has_lpa = all("LPA" in s for s in salaries)
        has_raw = any(len(part) > 6 and part.isdigit() for s in salaries for part in s.replace('-', ' ').split())
        
        if has_lpa and not has_raw:
            print("[SUCCESS] Verified: Salary ranges are correctly formatted in LPA on the Job List page!")
        else:
            print("[FAILED] Failed: Salary formatting verification on Job List page failed.")
    else:
        print("[INFO] No jobs found on the page to verify salary ranges. We will create one if needed or verify via API.")
        
    # Check if the 3-dot dropdown contains View Job, Edit Job, Share Job, Duplicate Job, Close Job, Delete Job
    dropdown_html = r_jobs.text
    actions_to_check = [
        "View Job", "Edit Job", "Share Job", "Duplicate Job", "Close Job", "Delete Job"
    ]
    for action in actions_to_check:
        if action in dropdown_html:
            print(f"[SUCCESS] Verified: Dropdown contains action '{action}'")
        else:
            print(f"[FAILED] Failed: Dropdown is missing action '{action}'")
            
    # 3. Find a Job ID to verify Share Link and Public Share Page
    job_match = re.search(r'data-share-url="(/jobs/share/([0-9a-fA-F-]+)/)"', r_jobs.text)
    if not job_match:
        # Fallback: search for edit URL or other links to extract a Job ID
        job_match = re.search(r'/jobs/([0-9a-fA-F-]+)/edit/', r_jobs.text)
        if job_match:
            job_id = job_match.group(1)
            share_url_path = f"/jobs/share/{job_id}/"
        else:
            print("No jobs found on page. We will fetch the API to check if jobs exist.")
            # Fetch jobs API to find any jobs
            jobs_api_url = "https://talentvault-1.onrender.com/api/v1/jobs/"
            r_api_list = session.get(jobs_api_url)
            if r_api_list.status_code == 200:
                results = r_api_list.json().get('results', [])
                if results:
                    job_id = results[0]['id']
                    share_url_path = f"/jobs/share/{job_id}/"
                    print(f"Found job ID {job_id} from API list.")
                else:
                    print("No jobs exist in the system at all.")
                    return
            else:
                print("Failed to access API list.")
                return
    else:
        share_url_path = job_match.group(1)
        job_id = job_match.group(2)
        
    public_share_url = f"https://talentvault-1.onrender.com{share_url_path}"
    print(f"Testing Public Share Page (unauthenticated): {public_share_url}")
    
    # Create a new session without authentication to test the public page
    public_session = requests.Session()
    r_public = public_session.get(public_share_url)
    
    if r_public.status_code == 200:
        print("[SUCCESS] Verified: Public share page is accessible without login!")
        public_html = r_public.text
        
        # Verify required details on the public page
        title_match = re.search(r'<h2 class="fw-bold mb-2"[^>]*>([^<]+)</h2>', public_html)
        company_match = re.search(r'<h4 class="text-primary fw-semibold mb-4">([^<]+)</h4>', public_html)
        location_match = re.search(r'<div class="text-secondary small text-uppercase fw-bold mb-1">.*?Location.*?</div>.*?<div[^>]*>([^<]+)</div>', public_html, re.DOTALL)
        exp_match = re.search(r'<div class="text-secondary small text-uppercase fw-bold mb-1">.*?Experience.*?</div>.*?<div[^>]*>([^<]+)</div>', public_html, re.DOTALL)
        salary_match = re.search(r'<div class="text-secondary small text-uppercase fw-bold mb-1">.*?Salary.*?</div>.*?<div[^>]*>([^<]+)</div>', public_html, re.DOTALL)
        
        print("Public Share Page parsed fields:")
        if title_match: print(f"  Title: {title_match.group(1).strip()}")
        if company_match: print(f"  Company: {company_match.group(1).strip()}")
        if location_match: print(f"  Location: {location_match.group(1).strip()}")
        if exp_match: print(f"  Experience: {exp_match.group(1).strip()}")
        if salary_match: print(f"  Salary Range: {salary_match.group(1).strip()}")
        
        # Verify no raw numbers in salary
        if salary_match and "LPA" in salary_match.group(1) and not any(len(part) > 6 and part.isdigit() for part in salary_match.group(1).split()):
            print("[SUCCESS] Verified: Salary Range is correctly displayed in LPA format on Public Page!")
        else:
            print("[FAILED] Failed: Salary Range formatting error on Public Page.")
            
        # Verify description and share links exist
        if "Job Description" in public_html:
            print("[SUCCESS] Verified: Description is present on Public Page!")
        else:
            print("[FAILED] Failed: Description missing on Public Page.")
            
        if "api.whatsapp.com/send" in public_html:
            print("[SUCCESS] Verified: WhatsApp share link is present on Public Page!")
        else:
            print("[FAILED] Failed: WhatsApp share link missing on Public Page.")
            
        if "mailto:" in public_html:
            print("[SUCCESS] Verified: Email share link is present on Public Page!")
        else:
            print("[FAILED] Failed: Email share link missing on Public Page.")
    else:
        print(f"[FAILED] Failed: Public share page returned status code {r_public.status_code}")
        
    # 4. Verify API response
    api_url = f"https://talentvault-1.onrender.com/api/v1/jobs/{job_id}/"
    print(f"Fetching Job API: {api_url} ...")
    r_api = session.get(api_url)
    if r_api.status_code == 200:
        api_data = r_api.json()
        print("API Response salary fields:")
        print(f"  min_salary: {api_data.get('min_salary')}")
        print(f"  max_salary: {api_data.get('max_salary')}")
        
        if "LPA" in str(api_data.get('min_salary')) and "LPA" in str(api_data.get('max_salary')):
            print("[SUCCESS] Verified: API correctly returns formatted LPA strings for salary fields!")
        else:
            print("[FAILED] Failed: API returns raw numbers or unformatted salaries.")
    else:
        print(f"[FAILED] Failed: API returned status code {r_api.status_code}")

if __name__ == "__main__":
    verify_production_jobs()
