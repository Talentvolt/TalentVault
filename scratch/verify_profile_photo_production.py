import requests
import re
import os
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

URL_BASE = "https://talentvault-1.onrender.com"
EMAIL = "growfluencestudio@gmail.com"
PASSWORD = "TalentVault2026!"

def verify_profile_photo_production():
    print("=" * 60)
    print("Verifying Candidate Profile Photo Feature on Production")
    print("=" * 60)

    session = requests.Session()
    
    # 1. Login
    login_url = f"{URL_BASE}/accounts/login/"
    print(f"GETting login page: {login_url}")
    login_resp = session.get(login_url)
    if login_resp.status_code != 200:
        print(f"FAILED to fetch login page: {login_resp.status_code}")
        sys.exit(1)
        
    soup = BeautifulSoup(login_resp.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
    if not csrf_input:
        print("CSRF token not found in login form")
        sys.exit(1)
        
    csrf_token = csrf_input['value']
    print(f"Found CSRF Token: {csrf_token[:10]}...")
    
    login_data = {
        'email': EMAIL,
        'password': PASSWORD,
        'remember_me': 'on',
        'csrfmiddlewaretoken': csrf_token
    }
    
    print(f"POSTing login with: {EMAIL}")
    login_post_resp = session.post(login_url, data=login_data, headers={'Referer': login_url}, allow_redirects=True)
    print(f"Login Response code: {login_post_resp.status_code}")
    print(f"Current URL: {login_post_resp.url}")
    
    if "dashboard" not in login_post_resp.url:
        print("ERROR: Login authentication failed.")
        sys.exit(1)
    print("Login successful!")

    # Helper to parse resume
    def upload_resume(filename, filepath):
        parser_url = f"{URL_BASE}/resume-parser/"
        print(f"\nUploading {filename} to {parser_url}...")
        r_parser = session.get(parser_url)
        csrf_token_parser = session.cookies.get('csrftoken')
        if not csrf_token_parser:
            match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r_parser.text)
            if match:
                csrf_token_parser = match.group(1)

        files = {
            'resume': (filename, open(filepath, 'rb'), 'application/pdf' if filename.endswith('.pdf') else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        }
        data = {
            'csrfmiddlewaretoken': csrf_token_parser,
            'overwrite': 'on'
        }
        
        resp = session.post(parser_url, data=data, files=files, headers={"Referer": parser_url}, allow_redirects=True)
        print(f"Upload response status: {resp.status_code}")
        if resp.status_code == 200 and "Resume Parsed Successfully" in resp.text:
            print(f"[SUCCESS] Parsed {filename} successfully.")
            return True, resp.text
        else:
            print(f"[FAILED] Failed to parse {filename}. Status: {resp.status_code}")
            return False, resp.text

    # Resumes path
    media_resumes_dir = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes')
    photo_resume_path = os.path.join(media_resumes_dir, 'Resume_Ramanjeet.pdf')
    no_photo_resume_path = os.path.join(media_resumes_dir, 'Laxmi_Sudharshan_DA_resume_Jan15th.pdf')

    # Verify BOTH exist locally
    if not os.path.exists(photo_resume_path):
        print(f"Error: {photo_resume_path} not found")
        sys.exit(1)
    if not os.path.exists(no_photo_resume_path):
        print(f"Error: {no_photo_resume_path} not found")
        sys.exit(1)

    # 2. Upload Candidate WITHOUT profile photo
    ok, _ = upload_resume('Laxmi_Sudharshan_DA_resume_Jan15th.pdf', no_photo_resume_path)
    if not ok:
        print("Verification Failed: Upload of resume without photo failed.")
        sys.exit(1)

    # Fetch candidate info using API
    api_url = f"{URL_BASE}/api/v1/candidates/profiles/"
    print(f"Calling API to find Laxmi: {api_url}")
    api_resp = session.get(api_url)
    laxmi_id = None
    if api_resp.status_code == 200:
        results = api_resp.json().get('results', [])
        for c in results:
            if c.get('user', {}).get('email') == 'laxmisudharshan10@gmail.com':
                laxmi_id = c.get('id')
                print(f"Found Laxmi Candidate ID: {laxmi_id}")
                # Check profile_photo from API JSON
                print(f"API profile_photo field: {c.get('profile_photo')}")
                break

    if not laxmi_id:
        print("ERROR: Could not find candidate Laxmi in API response")
        sys.exit(1)

    # Visit Laxmi detail page and check for placeholder avatar / no image
    laxmi_detail_url = f"{URL_BASE}/candidates/{laxmi_id}/"
    print(f"Fetching detail page: {laxmi_detail_url}")
    laxmi_detail_resp = session.get(laxmi_detail_url)
    laxmi_soup = BeautifulSoup(laxmi_detail_resp.text, 'html.parser')
    
    # Check if there is an <img> tag for profile photo in header or details
    # The header has style="width: 100px; height: 100px; border: 2px solid #dee2e6;" or class="avatar-xl"
    img_tags = laxmi_soup.find_all('img')
    has_candidate_photo = False
    for img in img_tags:
        if 'candidate_photos' in img.get('src', ''):
            has_candidate_photo = True
            print(f"Found unexpected profile image for Laxmi: {img.get('src')}")
            
    if has_candidate_photo:
        print("ERROR: Laxmi profile should NOT have a profile photo image.")
        sys.exit(1)
    else:
        print("[SUCCESS] Laxmi profile details correctly lack a profile photo image.")

    # Check for letter avatar removal (should not be any single letter text inside avatars)
    avatar_xl = laxmi_soup.find(class_='avatar-xl')
    if avatar_xl:
        avatar_text = avatar_xl.get_text(strip=True)
        print(f"Laxmi avatar-xl content: '{avatar_text}'")
        if len(avatar_text) == 1 and avatar_text.isalpha():
            print("ERROR: Laxmi profile contains a single letter avatar!")
            sys.exit(1)
        else:
            print("[SUCCESS] Laxmi profile correctly does not show letter avatar.")
    else:
        print("[SUCCESS] avatar-xl container check pass.")

    # 3. Upload Candidate WITH profile photo
    ok, _ = upload_resume('Resume_Ramanjeet.pdf', photo_resume_path)
    if not ok:
        print("Verification Failed: Upload of resume with photo failed.")
        sys.exit(1)

    # Fetch candidate info using API
    api_url = f"{URL_BASE}/api/v1/candidates/profiles/"
    print(f"Calling API to find Ramanjeet: {api_url}")
    api_resp = session.get(api_url)
    ramanjeet_id = None
    photo_url = None
    if api_resp.status_code == 200:
        results = api_resp.json().get('results', [])
        for c in results:
            if c.get('user', {}).get('email') == 'mauryaraman13@gmail.com':
                ramanjeet_id = c.get('id')
                photo_url = c.get('profile_photo')
                print(f"Found Ramanjeet Candidate ID: {ramanjeet_id}")
                print(f"API profile_photo field: {photo_url}")
                break

    if not ramanjeet_id:
        print("ERROR: Could not find candidate Ramanjeet in API response")
        sys.exit(1)

    if not photo_url:
        print("ERROR: Ramanjeet API profile_photo field is empty!")
        sys.exit(1)

    # Visit Ramanjeet detail page and check for photo image tag
    ramanjeet_detail_url = f"{URL_BASE}/candidates/{ramanjeet_id}/"
    print(f"Fetching detail page: {ramanjeet_detail_url}")
    ramanjeet_detail_resp = session.get(ramanjeet_detail_url)
    ramanjeet_soup = BeautifulSoup(ramanjeet_detail_resp.text, 'html.parser')
    
    img_tags = ramanjeet_soup.find_all('img')
    has_photo_img = False
    photo_img_src = None
    for img in img_tags:
        src = img.get('src', '')
        if 'candidate_photos' in src or photo_url in src:
            has_photo_img = True
            photo_img_src = src
            print(f"Found profile photo image tag: {src}")
            break

    if not has_photo_img:
        print("ERROR: Ramanjeet detail page does not contain candidate profile photo img tag!")
        sys.exit(1)
    else:
        print("[SUCCESS] Ramanjeet detail page correctly contains candidate profile photo.")

    # Request the profile photo URL and assert it returns status 200
    if not photo_img_src.startswith('http'):
        photo_img_src = URL_BASE + photo_img_src
    print(f"GETting profile photo URL: {photo_img_src}")
    photo_resp = session.get(photo_img_src)
    print(f"Photo response status: {photo_resp.status_code}")
    if photo_resp.status_code != 200:
        print(f"ERROR: Profile photo URL returned {photo_resp.status_code} status instead of 200.")
        sys.exit(1)
    else:
        print("[SUCCESS] Profile photo URL loads successfully with status 200.")

    # Check Candidate Search / List Page
    search_url = f"{URL_BASE}/candidates/?search=Ramanjeet"
    print(f"GETting search page: {search_url}")
    search_resp = session.get(search_url)
    search_soup = BeautifulSoup(search_resp.text, 'html.parser')
    
    # Check that Ramanjeet's avatar is displayed on search page as image
    search_imgs = search_soup.find_all('img')
    has_search_photo = False
    for img in search_imgs:
        src = img.get('src', '')
        if 'candidate_photos' in src:
            has_search_photo = True
            print(f"Found candidate profile photo in search result row: {src}")
            break
            
    if not has_search_photo:
        print("ERROR: Candidate search list page does not show profile photo for Ramanjeet.")
        sys.exit(1)
    else:
        print("[SUCCESS] Candidate search list page correctly shows candidate profile photo.")

    print("\n" + "=" * 60)
    print("ALL PRODUCTION PROFILE PHOTO VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 60 + "\n")

if __name__ == '__main__':
    verify_profile_photo_production()
