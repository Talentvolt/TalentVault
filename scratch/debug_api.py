import requests, re, json
s = requests.Session()
r = s.get('https://talentvault-1.onrender.com/accounts/login/')
token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text).group(1)
s.post('https://talentvault-1.onrender.com/accounts/login/', data={
    'email': 'growfluencestudio@gmail.com',
    'password': 'TalentVault2026!',
    'remember_me': 'on',
    'csrfmiddlewaretoken': token
}, headers={'Referer': 'https://talentvault-1.onrender.com/accounts/login/'})

r_api = s.get('https://talentvault-1.onrender.com/api/v1/candidates/profiles/')
print("STATUS CODE:", r_api.status_code)
if r_api.status_code == 200:
    results = r_api.json().get('results', [])
    print(f"TOTAL RESULTS: {len(results)}")
    for c in results:
        print(f"ID: {c.get('id')}, Name: {c.get('full_name')}, Email: {c.get('user', {}).get('email')}")
else:
    print(r_api.text[:1000])
