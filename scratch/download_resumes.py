import requests
from bs4 import BeautifulSoup
import re
import os

URL_BASE = "https://talentvault-1.onrender.com"
EMAIL = "growfluencestudio@gmail.com"
PASSWORD = "TalentVault2026!"

def download_resumes():
    session = requests.Session()
    login_url = f"{URL_BASE}/accounts/login/"
    print(f"GET {login_url}")
    login_resp = session.get(login_url)
    soup = BeautifulSoup(login_resp.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    
    print(f"Login to recruiter account: {EMAIL}")
    login_data = {
        'email': EMAIL,
        'password': PASSWORD,
        'csrfmiddlewaretoken': csrf_token
    }
    login_post_resp = session.post(login_url, data=login_data, headers={'Referer': login_url})
    if "dashboard" not in login_post_resp.url:
        print("Login failed!")
        return
    print("Logged in successfully.")
    
    candidates_url = f"{URL_BASE}/candidates/"
    print(f"GET {candidates_url}")
    candidates_resp = session.get(candidates_url)
    soup_candidates = BeautifulSoup(candidates_resp.text, 'html.parser')
    
    uuid_pattern = re.compile(r'/candidates/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
    
    # Let's inspect the page links
    all_links = soup_candidates.find_all('a')
    candidates_found = []
    
    for link in all_links:
        href = link.get('href', '')
        match = uuid_pattern.search(href)
        if match:
            cand_id = match.group(1)
            # Find the text in this link or nearby cells
            text_val = link.get_text(strip=True)
            candidates_found.append((cand_id, text_val))
            
    print(f"Found {len(candidates_found)} candidate profile links on live site:")
    for cid, text in candidates_found:
        print(f"  ID: {cid}, Text: {text}")
        
    # We want to find the ones matching "Anant", "Zaveri", "Finance Head", "Shreya", "Vikke"
    # Let's visit each candidate profile page to inspect their details and download the resume
    os.makedirs("scratch", exist_ok=True)
    for cid, text in candidates_found:
        check_url = f"{URL_BASE}/candidates/{cid}/"
        profile_resp = session.get(check_url)
        profile_soup = BeautifulSoup(profile_resp.text, 'html.parser')
        profile_text = profile_soup.get_text()
        
        # Check if matches Shreya Chavda / Anant Zaveri Pvt Ltd
        is_shreya = "shreya" in profile_text.lower() or "zaveri" in profile_text.lower() or "chavda" in profile_text.lower()
        is_vikke = "vikke" in profile_text.lower() or "finance head" in profile_text.lower() or "minda" in profile_text.lower()
        
        if is_shreya or is_vikke:
            name_label = "shreya_chavda" if is_shreya else "vikke_gupta"
            print(f"MATCH: Candidate {cid} matches {name_label}!")
            
            # Download the resume
            download_url = f"{URL_BASE}/candidates/{cid}/resume/download/"
            dl_resp = session.get(download_url)
            if dl_resp.status_code == 200:
                # Find filename from Content-Disposition if present
                cd = dl_resp.headers.get('Content-Disposition', '')
                filename = f"{name_label}_resume.pdf"
                if "filename=" in cd:
                    filename = cd.split('filename=')[-1].strip('"')
                
                dest_path = f"scratch/{name_label}_{filename}"
                with open(dest_path, 'wb') as f:
                    f.write(dl_resp.content)
                print(f"Downloaded resume successfully to {dest_path}!")
            else:
                print(f"Failed to download resume for {cid}, status: {dl_resp.status_code}")

if __name__ == '__main__':
    download_resumes()
