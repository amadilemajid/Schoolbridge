"""
Custom Fernet-encrypted Django model fields.
US-070: AES-256 PII encryption at rest.

Replaces django-fernet-fields (incompatible with Django 4.x).
Uses the `cryptography` library directly (already a project dependency).
Keys are sourced from settings.FERNET_KEYS (list of base64-encoded Fernet keys).
MultiFernet supports key rotation: the first key encrypts, all keys can decrypt.

IMPORTANT: Encrypted fields cannot be filtered via Django ORM.
           Always pair with a SHA-256 hash field for DB lookups.
"""
import datetime

from cryptography.fernet import MultiFernet, Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _get_fernet() -> MultiFernet:
    """Return a MultiFernet instance from settings.FERNET_KEYS."""
    keys = getattr(settings, 'FERNET_KEYS', [])
    if not keys:
        raise ValueError(
            'settings.FERNET_KEYS must be set. '
            'Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return MultiFernet([
        Fernet(k.encode() if isinstance(k, str) else k)
        for k in keys
    ])


def _is_encrypted(value: str) -> bool:
    """Heuristic: Fernet tokens start with 'gAAAAA' (version byte 0x80 in base64)."""
    return isinstance(value, str) and value.startswith('gAAAAA')


class EncryptedCharField(models.TextField):
    """
    A CharField stored encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).
    Stored as TextField because ciphertext is longer than plaintext.
    NOT filterable by value — add a separate phone_hash / hash field for lookups.
    max_length is accepted for API compatibility but not enforced on the DB column.
    """

    def __init__(self, *args, max_length=None, **kwargs):
        # Accept max_length for field declaration compat; store for form validation only
        self._plaintext_max_length = max_length
        super().__init__(*args, **kwargs)

    def decrypt(self, value):
        if value is None or value == '':
            return value
        if not _is_encrypted(value):
            return value  # Plaintext (e.g. un-migrated row)
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            return value  # Return raw if key mismatch (key rotation in progress)

    def encrypt(self, value):
        if value is None or value == '':
            return value
        if _is_encrypted(str(value)):
            return value  # Already encrypted
        return _get_fernet().encrypt(str(value).encode()).decode()

    # ---- ORM hooks ----

    def from_db_value(self, value, expression, connection):
        return self.decrypt(value)

    def to_python(self, value):
        if isinstance(value, str) and _is_encrypted(value):
            return self.decrypt(value)
        return value

    def get_prep_value(self, value):
        return self.encrypt(value)


class EncryptedDateField(models.TextField):
    """
    A DateField stored encrypted at rest.
    Date is serialised as ISO-8601 string, encrypted, then stored as TextField.
    """

    def decrypt(self, value) -> datetime.date | None:
        if value is None or value == '':
            return None
        raw = value
        if _is_encrypted(value):
            try:
                raw = _get_fernet().decrypt(value.encode()).decode()
            except InvalidToken:
                raw = value
        try:
            return datetime.date.fromisoformat(raw)
        except (ValueError, TypeError):
            return None

    def encrypt(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime.date):
            value = value.isoformat()
        if _is_encrypted(str(value)):
            return value
        return _get_fernet().encrypt(str(value).encode()).decode()

    # ---- ORM hooks ----

    def from_db_value(self, value, expression, connection):
        return self.decrypt(value)

    def to_python(self, value):
        if isinstance(value, datetime.date):
            return value
        return self.decrypt(value)

    def get_prep_value(self, value):
        return self.encrypt(value)
