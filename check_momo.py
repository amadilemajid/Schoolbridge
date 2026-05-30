import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
import requests, base64
from django.conf import settings

credentials = f"{settings.MTN_MOMO_API_USER}:{settings.MTN_MOMO_API_KEY}"
b64 = base64.b64encode(credentials.encode()).decode()

token = requests.post(
    f"{settings.MTN_MOMO_BASE_URL}/collection/token/",
    headers={"Authorization": f"Basic {b64}", "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY}
).json().get("access_token")

ref = "5bc25720-fe5d-4f6f-9bb2-651ea3b5454e"
r = requests.get(
    f"{settings.MTN_MOMO_BASE_URL}/collection/v1_0/requesttopay/{ref}",
    headers={"Authorization": f"Bearer {token}", "X-Target-Environment": "sandbox", "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY}
)
print("Status:", r.status_code)
print("Response:", r.text)
