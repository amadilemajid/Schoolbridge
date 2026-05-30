import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

import requests
import uuid
from django.conf import settings
import base64

# Get access token
credentials = f"{settings.MTN_MOMO_API_USER}:{settings.MTN_MOMO_API_KEY}"
b64 = base64.b64encode(credentials.encode()).decode()

token_response = requests.post(
    f"{settings.MTN_MOMO_BASE_URL}/collection/token/",
    headers={
        "Authorization": f"Basic {b64}",
        "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY,
    }
)
print("Token status:", token_response.status_code)
token = token_response.json().get("access_token")

# Request payment
ref = str(uuid.uuid4())
payment_response = requests.post(
    f"{settings.MTN_MOMO_BASE_URL}/collection/v1_0/requesttopay",
    headers={
        "Authorization": f"Bearer {token}",
        "X-Reference-Id": ref,
        "X-Target-Environment": "sandbox",
        "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY,
        "Content-Type": "application/json",
    },
    json={
        "amount": "150000",
        "currency": "UGX",
        "externalId": "SCH-2026-0002",
        "payer": {
            "partyIdType": "MSISDN",
            "partyId": "256708826558"
        },
        "payerMessage": "School fees payment",
        "payeeNote": "Alice Nakato fees"
    }
)
print("Payment request status:", payment_response.status_code)
print("Reference ID:", ref)
print("Response:", payment_response.text)
