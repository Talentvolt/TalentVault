import requests
import re

def verify_ctc():
    print("=" * 60)
    print("Verifying Expected CTC rendering in Production")
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
    
    # 2. Get Candidate List page and find Ramanjeet's detail link
    candidates_url = "https://talentvault-1.onrender.com/candidates/"
    print("Fetching candidates list page...")
    r_candidates = session.get(candidates_url)
    
    matches = re.findall(r'href="(/candidates/[0-9a-fA-F-]+/)"[^>]*>(.*?)</a>', r_candidates.text, re.DOTALL)
    detail_path = None
    for path, name in matches:
         if "Ramanjeet" in name or "Maurya" in name:
              detail_path = path
              break
              
    if not detail_path:
         print("Ramanjeet profile link not found. Will search first candidate profile.")
         match = re.search(r'href="(/candidates/[0-9a-fA-F-]+/)"', r_candidates.text)
         if match:
              detail_path = match.group(1)
              
    if not detail_path:
         print("No candidate profiles found.")
         return
         
    detail_url = f"https://talentvault-1.onrender.com{detail_path}"
    print(f"Fetching Candidate Detail page: {detail_url}")
    
    r_detail = session.get(detail_url)
    detail_html = r_detail.text
    
    # Check current and expected CTC elements in Candidate Detail page
    ctc_matches = re.findall(r'(Current CTC|Expected CTC)\s*</div>\s*<div[^>]*>₹([\d.]+)</div>', detail_html, re.I | re.DOTALL)
    print("Parsed CTC entries from HTML:")
    for title, val in ctc_matches:
         print(f"{title}: ₹{val}")
         
    # Check if they have a decimal point (one decimal rendering)
    success = True
    for title, val in ctc_matches:
         if "." not in val:
              print(f"FAILED: {title} is rendered as '{val}' (missing decimal place)")
              success = False
              
    if success and len(ctc_matches) > 0:
         print("\nVERIFICATION RESULT: SUCCESS! Candidate Detail page correctly renders current and expected CTCs with one decimal place in production!")
    else:
         print("\nVERIFICATION RESULT: FAILURE! Decimals are missing or parsing failed.")

if __name__ == "__main__":
    verify_ctc()
