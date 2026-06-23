import requests
import re
import os

def debug_candidates():
    session = requests.Session()
    login_url = "https://talentvault-1.onrender.com/accounts/login/"
    
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
    session.post(login_url, data=payload, headers={"Referer": login_url})
    
    candidates_url = "https://talentvault-1.onrender.com/candidates/"
    print("Fetching candidates list page...")
    r_candidates = session.get(candidates_url)
    
    print("\n--- CANDIDATE ENTRIES FOUND ---")
    # Let's extract names and links from the candidates list page
    # Workable-style ATS list layout contains name in bold, e.g. <span class="fw-bold">Ramanjeet Maurya</span>
    matches = re.findall(r'href="(/candidates/[0-9a-fA-F-]+/)"[^>]*>(.*?)</a>', r_candidates.text, re.DOTALL)
    for path, name in matches:
         name_clean = re.sub(r'<[^>]+>', '', name).strip()
         print(f"Path: {path} | Name: {name_clean}")
         
    # Let's find Ramanjeet specifically
    ramanjeet_path = None
    for path, name in matches:
         if "Ramanjeet" in name or "Maurya" in name:
              ramanjeet_path = path
              break
              
    if not ramanjeet_path:
         print("\nRamanjeet Maurya not found in list. Finding first candidate to print experience section...")
         if matches:
              ramanjeet_path = matches[0][0]
         else:
              print("No candidate links found at all.")
              # Print part of the candidates list html to debug
              print(r_candidates.text[:1000])
              return
              
    detail_url = f"https://talentvault-1.onrender.com{ramanjeet_path}"
    print(f"\nFetching detail page: {detail_url}")
    r_detail = session.get(detail_url)
    html = r_detail.text
    
    print("\n--- EXPERIENCES RENDERED ON DETAIL PAGE ---")
    # Print the lines containing work experience or timeline from the detail page
    experience_section = False
    for line in html.split('\n'):
         if "Experience" in line or "timeline" in line.lower() or "Concentrix" in line or "Amazon" in line or "Company" in line:
              print(line.strip())

if __name__ == "__main__":
    debug_candidates()
