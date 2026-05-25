"""
Custom password validators.
US-004: Password must differ from last 3.
"""
from django.core.exceptions import ValidationError


class PasswordHistoryValidator:
    """Reject passwords that match any of the user's last 3 passwords."""

    def validate(self, password, user=None):
        if user and user.pk:
            from authentication.models import PasswordHistory
            if PasswordHistory.is_reused(user, password):
                raise ValidationError(
                    "You cannot reuse any of your last 3 passwords.",
                    code='password_reused',
                )

    def get_help_text(self):
        return "Your password must be different from your last 3 passwords."
