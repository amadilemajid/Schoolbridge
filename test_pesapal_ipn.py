import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
import requests

# Step 1: Get token
token_response = requests.post(
    'https://cybqa.pesapal.com/pesapalv3/api/Auth/RequestToken',
    json={
        'consumer_key': 'TDpigBOOhs+zAl8cwH2Fl82jJGyD8xev',
        'consumer_secret': '1KpqkfsMaihIcOlhnBo/gBZ5smw='
    },
    headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
)
token = token_response.json()['token']
print('Token OK')

# Step 2: Register IPN URL
ipn_response = requests.post(
    'https://cybqa.pesapal.com/pesapalv3/api/URLSetup/RegisterIPN',
    json={
        'url': 'https://de14-102-134-149-89.ngrok-free.app/payments/pesapal/ipn/',
        'ipn_notification_type': 'POST'
    },
    headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
)
print('IPN Status:', ipn_response.status_code)
print('IPN Response:', ipn_response.text)
