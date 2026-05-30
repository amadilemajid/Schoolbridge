import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
import requests, uuid, base64
from django.conf import settings

credentials = f"{settings.MTN_MOMO_API_USER}:{settings.MTN_MOMO_API_KEY}"
b64 = base64.b64encode(credentials.encode()).decode()

token = requests.post(
    f"{settings.MTN_MOMO_BASE_URL}/collection/token/",
    headers={"Authorization": f"Basic {b64}", "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY}
).json().get("access_token")

ref = str(uuid.uuid4())
r = requests.post(
    f"{settings.MTN_MOMO_BASE_URL}/collection/v1_0/requesttopay",
    headers={"Authorization": f"Bearer {token}", "X-Reference-Id": ref, "X-Target-Environment": "sandbox", "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY, "Content-Type": "application/json"},
    json={"amount": "100", "currency": "EUR", "externalId": "SCH-2026-0002", "payer": {"partyIdType": "MSISDN", "partyId": "256708826558"}, "payerMessage": "School fees", "payeeNote": "Alice Nakato fees"}
)
print("Status:", r.status_code)
print("Ref:", ref)
print("Response:", r.text)
