from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

DEMO_TOKEN = 'demo_jwt_access_token_12345'

# DEMO_MODE allows the explicit demo token to auto-authenticate as first active user.
# Enabled if settings.DEMO_MODE is True or in DEBUG mode.
DEMO_MODE = getattr(settings, 'DEMO_MODE', settings.DEBUG)


class SchoolBridgeJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication for SchoolBridge.

    Production behaviour:
      - No Authorization header → return None (unauthenticated, DRF returns 401)
      - Invalid/expired JWT      → raise AuthenticationFailed (401)
      - Valid JWT                → return (user, token)

    Demo behaviour (DEMO_MODE=True only):
      - DEMO_TOKEN or token containing 'demo' → auto-login as first active user
    """

    def authenticate(self, request):
        header = self.get_header(request)

        if header is None:
            # No Authorization header — do NOT auto-login.
            # DRF will raise 401 if the view requires authentication.
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        token_str = raw_token.decode('utf-8') if isinstance(raw_token, bytes) else str(raw_token)

        # Explicit demo token (only honoured when DEMO_MODE is enabled)
        if DEMO_MODE and (token_str == DEMO_TOKEN or 'demo' in token_str.lower()):
            user = User.objects.filter(is_active=True).first()
            if user:
                return (user, None)

        # Standard JWT validation — raises AuthenticationFailed on failure
        try:
            validated_token = self.get_validated_token(raw_token)
            return (self.get_user(validated_token), validated_token)
        except Exception as exc:
            raise AuthenticationFailed('Invalid or expired access token.') from exc
