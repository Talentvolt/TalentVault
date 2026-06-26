import requests
import re

def get_traceback():
    session = requests.Session()
    login_url = "https://talentvault-1.onrender.com/accounts/login/"
    
    # 1. Login
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
    
    # Get the endpoint
    resp = session.get("https://talentvault-1.onrender.com/api/v1/jobs/8e46da93-65d7-42db-9240-850be5707b09/")
    print("Status code:", resp.status_code)
    
    html = resp.text
    # Search for the exception value
    exc_val = re.findall(r'<pre class="exception_value">(.*?)</pre>', html, re.DOTALL)
    print("Exception Value:", exc_val)
    
    # Search for files and lines in traceback
    frames = re.findall(r'<td class="code">.*?</td>', html, re.DOTALL)
    # Print the source code context around the exception
    lines = re.findall(r'<th>(\d+)</th>\s*<td><pre>(.*?)</pre></td>', html)
    print("\nSome traceback lines:")
    for num, code in lines[:40]:
        print(f"L{num}: {code}")

if __name__ == "__main__":
    get_traceback()
