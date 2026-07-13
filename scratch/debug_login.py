import os
import sys
import django
from django.test import Client
from django.urls import reverse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

def debug_login():
    client = Client()
    login_url = reverse('employer_login')
    client.get(login_url)
    
    email = "growfluencestudio@gmail.com"
    password = "TalentVault2026!"
    
    response = client.post(login_url, {
        'email': email,
        'password': password,
        'remember_me': 'on'
    })
    
    print(f"Status Code: {response.status_code}")
    content = response.content.decode('utf-8')
    idx = content.find('class="alert-error"')
    if idx != -1:
        print(content[idx:idx+400])
    else:
        print("No class='alert-error' found, printing first 1000 chars:")
        print(content[:1000])

if __name__ == '__main__':
    debug_login()
