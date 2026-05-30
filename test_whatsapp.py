import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from messaging.services import WhatsAppService
import requests

phone = '256708826558'
text = 'Test from SchoolBridge - BALANCE test'

print('TOKEN being used:', WhatsAppService.TOKEN[:40])
print('PHONE_ID:', WhatsAppService.PHONE_ID)
print('BASE_URL:', WhatsAppService.BASE_URL)

payload = {
    'messaging_product': 'whatsapp',
    'to': phone,
    'type': 'text',
    'text': {'body': text},
}
response = requests.post(
    f'{WhatsAppService.BASE_URL}/{WhatsAppService.PHONE_ID}/messages',
    headers={
        'Authorization': f'Bearer {WhatsAppService.TOKEN}',
        'Content-Type': 'application/json',
    },
    json=payload,
    timeout=10,
)
print('Status:', response.status_code)
print('Response:', response.text)
