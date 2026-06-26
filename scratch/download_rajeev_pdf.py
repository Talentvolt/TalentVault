import requests, re

s = requests.Session()
r = s.get('https://talentvault-1.onrender.com/accounts/login/')
token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text).group(1)
s.post('https://talentvault-1.onrender.com/accounts/login/', data={
    'email': 'growfluencestudio@gmail.com',
    'password': 'TalentVault2026!',
    'remember_me': 'on',
    'csrfmiddlewaretoken': token
}, headers={'Referer': 'https://talentvault-1.onrender.com/accounts/login/'})

url = "https://talentvault-1.onrender.com/media/resumes/Rajeev_Oct_26th_resume1.pdf"
print(f"Downloading {url}...")
resp = s.get(url)
print("Response status:", resp.status_code)
if resp.status_code == 200:
    with open("scratch/rajeev_resume.pdf", "wb") as f:
        f.write(resp.content)
    print("Saved to scratch/rajeev_resume.pdf successfully.")
else:
    print("Failed to download PDF.")
