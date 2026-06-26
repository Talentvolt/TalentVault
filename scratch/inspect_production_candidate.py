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

r_api = s.get('https://talentvault-1.onrender.com/api/v1/candidates/profiles/db5cfc6b-b100-45c8-b099-14001315f8dc/')
print("STATUS CODE:", r_api.status_code)
if r_api.status_code == 200:
    print(json.dumps(r_api.json(), indent=2))
else:
    print(r_api.text[:2000])
