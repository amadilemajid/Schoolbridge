import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
import requests, uuid

token = requests.post(
    'https://cybqa.pesapal.com/pesapalv3/api/Auth/RequestToken',
    json={'consumer_key': 'TDpigBOOhs+zAl8cwH2Fl82jJGyD8xev', 'consumer_secret': '1KpqkfsMaihIcOlhnBo/gBZ5smw='},
    headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
).json()['token']

order_ref = str(uuid.uuid4())
r = requests.post(
    'https://cybqa.pesapal.com/pesapalv3/api/Transactions/SubmitOrderRequest',
    json={
        'id': order_ref,
        'currency': 'UGX',
        'amount': 150000,
        'description': 'School fees - Alice Nakato',
        'callback_url': 'https://de14-102-134-149-89.ngrok-free.app/payments/pesapal/callback/',
        'notification_id': 'f5127164-587e-4aed-89db-da533d50b662',
        'billing_address': {
            'email_address': 'guardian@example.com',
            'phone_number': '256708826558',
            'first_name': 'Bob',
            'last_name': 'Nakato'
        }
    },
    headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': f'Bearer {token}'}
)
print('Status:', r.status_code)
print('Response:', r.text)
