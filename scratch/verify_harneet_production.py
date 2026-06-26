import os
import sys
import requests
import re
from bs4 import BeautifulSoup

URL_BASE = "https://talentvault-1.onrender.com"
EMAIL = "growfluencestudio@gmail.com"
PASSWORD = "TalentVault2026!"

def verify_harneet_production():
    pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'harneet_resume.pdf'))
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found!")
        sys.exit(1)
        
    print(f"--- STARTING HARNEET RESUME PARSER VERIFICATION ON {URL_BASE} ---")
    session = requests.Session()
    
    # 1. Login
    login_url = f"{URL_BASE}/accounts/login/"
    print(f"[1/6] GET {login_url}")
    login_resp = session.get(login_url)
    soup = BeautifulSoup(login_resp.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    
    print(f"[2/6] POST Login to recruiter account: {EMAIL}")
    login_data = {
        'email': EMAIL,
        'password': PASSWORD,
        'remember_me': 'on',
        'csrfmiddlewaretoken': csrf_token
    }
    login_post_resp = session.post(login_url, data=login_data, headers={'Referer': login_url})
    if "dashboard" not in login_post_resp.url:
        print("Login failed!")
        sys.exit(1)
    print("Logged in successfully.")
    
    # 2. Get parser CSRF token
    parser_url = f"{URL_BASE}/resume-parser/"
    print(f"[3/6] GET {parser_url}")
    parser_resp = session.get(parser_url)
    soup_parser = BeautifulSoup(parser_resp.text, 'html.parser')
    parser_csrf = soup_parser.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    
    # 3. Upload resume
    print(f"[4/6] POST Uploading {pdf_path} (overwrite=on)")
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
    print(f"[5/6] GET {candidates_url} to find the candidate profile ID")
    candidates_resp = session.get(candidates_url)
    soup_candidates = BeautifulSoup(candidates_resp.text, 'html.parser')
    
    candidate_id = None
    uuid_pattern = re.compile(r'/candidates/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
    
    print("Scanning candidate profile links to locate Harneet Singh Chhabra...")
    all_links = soup_candidates.find_all('a')
    for link in all_links:
        href = link.get('href', '')
        match = uuid_pattern.search(href)
        if match:
            cand_id = match.group(1)
            # Fetch profile page to check if it's Harneet
            check_url = f"{URL_BASE}/candidates/{cand_id}/"
            check_resp = session.get(check_url)
            if check_resp.status_code == 200 and "harneet" in check_resp.text.lower():
                candidate_id = cand_id
                break
                
    if not candidate_id:
        print("ERROR: Harneet Singh candidate profile link not found.")
        sys.exit(1)
        
    print(f"Candidate Profile ID for Harneet: {candidate_id}")
    
    # 5. Fetch Profile and Verify parsing accuracy
    profile_url = f"{URL_BASE}/candidates/{candidate_id}/"
    print(f"[6/6] GET Harneet Profile: {profile_url}")
    profile_resp = session.get(profile_url)
    soup_profile = BeautifulSoup(profile_resp.text, 'html.parser')
    
    # Parse experiences, educations, skills
    # Check Work Experience entries
    experience_entries = soup_profile.find_all(class_='experience-entry')
    print(f"\nFound {len(experience_entries)} experience entries on production candidate page.")
    
    assert len(experience_entries) == 6, f"Expected 6 experience entries, but found {len(experience_entries)}"
    
    # Let's inspect the names of the companies to verify them
    expected_companies = [
        "Hero MotoCorp. Ltd",
        "Akums Lifesciences Ltd",
        "Adani Power Rajasthan Ltd",
        "L&T – MHPS Boilers Pvt. Ltd",
        "Jindal Drilling & Industries Ltd",
        "Grant Thornton"
    ]
    expected_designations = [
        "Finance Head",
        "Manager",
        "Deputy Manager",
        "Assistant Manager",
        "Deputy Manager",
        "Senior Auditor"
    ]
    
    for idx, entry in enumerate(experience_entries):
        text = entry.get_text()
        print(f"Job {idx+1}: {text.strip().replace('\n', ' ')}")
        desig = expected_designations[idx]
        comp = expected_companies[idx]
        assert desig.lower() in text.lower(), f"Expected designation '{desig}' not found in entry {idx+1}"
        # For L&T, we normalize hyphens or similar, just checking L&T is enough
        check_comp = "L&T" if "L&T" in comp else comp
        assert check_comp.lower() in text.lower(), f"Expected company '{check_comp}' not found in entry {idx+1}"
        
    # Check Education history
    # Let's locate education section card
    # In template, education entries are inside row columns and rendered under the Education card
    # We can search for text 'Education' in cards, and count sub-elements
    education_section = None
    cards = soup_profile.find_all(class_='card')
    for card in cards:
        card_title = card.find('h5')
        if card_title and 'education' in card_title.get_text().lower():
            education_section = card
            break
            
    assert education_section is not None, "Education section card not found!"
    
    # Within education section, count entries
    edu_entries = education_section.find_all(class_='row')
    print(f"Found {len(edu_entries)} education entries in Education section.")
    assert len(edu_entries) == 2, f"Expected 2 education entries, but found {len(edu_entries)}"
    
    edu_text = education_section.get_text()
    assert "Chartered Accountant" in edu_text
    assert "ICAI" in edu_text
    assert "Icai" not in edu_text # Verify title-cased "Icai" is corrected back to "ICAI"
    assert "Bachelor of Commerce (Hons.)" in edu_text
    assert "Sambalpur University" in edu_text
    
    # Verify no work experience in education
    assert "Hero" not in edu_text
    assert "Akums" not in edu_text
    
    # Check Skills
    skills_section = None
    for card in cards:
        card_title = card.find('h5')
        if card_title and 'skills' in card_title.get_text().lower():
            skills_section = card
            break
    assert skills_section is not None, "Skills section card not found!"
    skills_badges = skills_section.find_all(class_='badge')
    skills_list = [b.get_text().strip() for b in skills_badges]
    print(f"Found skills: {skills_list}")
    assert len(skills_list) > 0, "Technical skills should be populated"
    assert "Practices" not in skills_list
    assert "Practices." not in skills_list
    assert "Inventory For Action." not in skills_list
    
    # Check Projects
    projects_section = None
    for card in cards:
        card_title = card.find('h5')
        if card_title and 'projects' in card_title.get_text().lower():
            projects_section = card
            break
    assert projects_section is not None, "Projects section card not found!"
    proj_entries = projects_section.find_all('li')
    proj_texts = [p.get_text().strip() for p in proj_entries]
    print(f"Found projects: {proj_texts}")
    assert len(proj_texts) == 1 and "No projects listed" in proj_texts[0], "Projects section should show no projects listed."
    
    print("\n==============================================")
    print("=== PRODUCTION RESUME PARSER VERIFY SUCCESS ===")
    print("==============================================")

if __name__ == '__main__':
    verify_harneet_production()
