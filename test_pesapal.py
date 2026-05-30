import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
import requests

response = requests.post(
    'https://cybqa.pesapal.com/pesapalv3/api/Auth/RequestToken',
    json={
        'consumer_key': 'TDpigBOOhs+zAl8cwH2Fl82jJGyD8xev',
        'consumer_secret': '1KpqkfsMaihIcOlhnBo/gBZ5smw='
    },
    headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
)
print('Status:', response.status_code)
print('Response:', response.text)
