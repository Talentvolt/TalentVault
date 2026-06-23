import requests
import re
import sys

def verify_edit_flow():
    print("=" * 60)
    print("Verifying Candidate CTC Edit and View Flow in Production")
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
    r_login = session.post(login_url, data=payload, headers={"Referer": login_url})
    if r_login.status_code != 200 and not any(c.name == 'sessionid' for c in session.cookies):
        print("Login failed!")
        sys.exit(1)
    print("Login successful.")

    # 2. Get Candidates List to find Ramanjeet Maurya
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
         print("Ramanjeet profile link not found. Searching first candidate profile.")
         match = re.search(r'href="(/candidates/[0-9a-fA-F-]+/)"', r_candidates.text)
         if match:
              detail_path = match.group(1)
               
    if not detail_path:
         print("No candidate profiles found.")
         sys.exit(1)
         
    candidate_id = detail_path.strip("/").split("/")[-1]
    detail_url = f"https://talentvault-1.onrender.com{detail_path}"
    edit_url = f"https://talentvault-1.onrender.com/candidates/{candidate_id}/edit/"
    api_url = f"https://talentvault-1.onrender.com/api/v1/candidates/profiles/{candidate_id}/"
    
    print(f"Candidate ID: {candidate_id}")
    print(f"Detail URL: {detail_url}")
    print(f"Edit URL: {edit_url}")
    print(f"API URL: {api_url}")

    # 3. GET the edit page to parse existing form values and CSRF token
    print("\nGET candidate edit page...")
    r_edit_get = session.get(edit_url)
    edit_html = r_edit_get.text
    
    # Extract CSRF token from form
    csrf_match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', edit_html)
    form_csrf = csrf_match.group(1) if csrf_match else csrf_token
    
    # Simple regex to extract current values from input fields
    # Inputs look like: <input type="number" name="current_salary" value="X.XX" ...>
    def get_input_value(name, html):
        m = re.search(rf'name="{name}"\s+value="([^"]*)"', html)
        if not m:
            m = re.search(rf'value="([^"]*)"\s+name="{name}"', html)
        return m.group(1) if m else ""

    # Also extract other fields because django form requires them or they'll be overwritten/cleared
    full_name = get_input_value("full_name", edit_html)
    summary = get_input_value("summary", edit_html)
    location = get_input_value("location", edit_html)
    total_experience = get_input_value("total_experience", edit_html)
    current_company = get_input_value("current_company", edit_html)
    current_designation = get_input_value("current_designation", edit_html)
    notice_period = get_input_value("notice_period", edit_html)
    linkedin_url = get_input_value("linkedin_url", edit_html)
    portfolio_url = get_input_value("portfolio_url", edit_html)

    # If textarea/summary is empty from get_input_value (as textareas don't use value attribute)
    if not summary:
        textarea_match = re.search(r'<textarea[^>]*name="summary"[^>]*>(.*?)</textarea>', edit_html, re.DOTALL)
        if textarea_match:
            summary = textarea_match.group(1).strip()

    print(f"Extracted Current Form Values:")
    print(f"  full_name: '{full_name}'")
    print(f"  location: '{location}'")
    print(f"  current_salary: '{get_input_value('current_salary', edit_html)}'")
    print(f"  expected_salary: '{get_input_value('expected_salary', edit_html)}'")

    # 4. POST update to set current_salary = 8.00 and expected_salary = 7.50
    post_data = {
        "csrfmiddlewaretoken": form_csrf,
        "full_name": full_name or "Ramanjeet Maurya",
        "summary": summary,
        "location": location or "Delhi",
        "total_experience": total_experience or "1.0",
        "current_company": current_company,
        "current_designation": current_designation,
        "current_salary": "8.00",
        "expected_salary": "7.50",
        "notice_period": notice_period or "30",
        "linkedin_url": linkedin_url,
        "portfolio_url": portfolio_url,
    }
    
    print("\nPOST candidate edit form with Expected Salary = 7.50 and Current Salary = 8.00...")
    r_edit_post = session.post(edit_url, data=post_data, headers={"Referer": edit_url})
    
    if r_edit_post.url.endswith('/edit/') or r_edit_post.url.endswith('/edit'):
        print("POST stayed on edit page (validation errors!). Saving HTML response to scratch/post_response.html...")
        with open("scratch/post_response.html", "w", encoding="utf-8") as f:
            f.write(r_edit_post.text)
        errs = re.findall(r'<p[^>]*class="invalid-feedback"[^>]*>(.*?)</p>', r_edit_post.text, re.DOTALL)
        if not errs:
            errs = re.findall(r'class="invalid-feedback"[^>]*>(.*?)<', r_edit_post.text, re.DOTALL)
        for err in errs:
            print("  Form Error:", re.sub(r'\s+', ' ', err).strip())
        sys.exit(1)
        
    print("Form POST completed successfully! Final URL:", r_edit_post.url)

    # 5. Verify values on Edit Form (should be 8.00 and 7.50)
    print("\nGET candidate edit page again to verify edit form value...")
    r_edit_verify = session.get(edit_url)
    current_val_in_form = get_input_value("current_salary", r_edit_verify.text)
    expected_val_in_form = get_input_value("expected_salary", r_edit_verify.text)
    print(f"Edit Form Current Salary Value: '{current_val_in_form}'")
    print(f"Edit Form Expected Salary Value: '{expected_val_in_form}'")

    # 6. Verify values on Candidate Detail Page
    print("\nGET candidate detail page to verify header card rendering...")
    r_detail_verify = session.get(detail_url)
    detail_html = r_detail_verify.text
    
    ctc_matches = re.findall(r'(Current CTC|Expected CTC)\s*</div>\s*<div[^>]*>₹([\d.]+)</div>', detail_html, re.I | re.DOTALL)
    print("Detail Page Rendered CTCs:")
    for title, val in ctc_matches:
         print(f"  {title}: ₹{val}")
         
    # 7. Verify API Response
    print("\nGET Candidate API response to verify JSON values...")
    r_api = session.get(api_url)
    api_json = r_api.json()
    print(f"API Current Salary: {api_json.get('current_salary')}")
    print(f"API Expected Salary: {api_json.get('expected_salary')}")

    # Validation Checks
    success = True
    if current_val_in_form not in ("8.00", "8.0", "8"):
        print("FAILURE: Current Salary in edit form is not 8.00")
        success = False
    if expected_val_in_form not in ("7.50", "7.5"):
        print("FAILURE: Expected Salary in edit form is not 7.50")
        success = False
        
    found_current = False
    found_expected = False
    for title, val in ctc_matches:
        if "current" in title.lower():
            found_current = True
            if val != "8.0":
                print(f"FAILURE: Header Current CTC rendered as '{val}' instead of '8.0'")
                success = False
        if "expected" in title.lower():
            found_expected = True
            if val != "7.5":
                print(f"FAILURE: Header Expected CTC rendered as '{val}' instead of '7.5'")
                success = False
                
    if not found_current or not found_expected:
        print("FAILURE: Header CTC fields not found on Candidate Detail page HTML structure")
        success = False

    if str(api_json.get('current_salary')) not in ("8.00", "8.0", "8"):
        print("FAILURE: API Current Salary is not 8.00/8.0")
        success = False
    if str(api_json.get('expected_salary')) not in ("7.50", "7.5"):
        print("FAILURE: API Expected Salary is not 7.50/7.5")
        success = False

    if success:
        print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
        print("Database/API = 7.5 & 8.0")
        print("Edit page = 7.50 & 8.00")
        print("Header card = ₹7.5 & ₹8.0")
    else:
        print("\nVERIFICATION FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    verify_edit_flow()
