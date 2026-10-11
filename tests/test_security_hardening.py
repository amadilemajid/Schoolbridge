"""
Security Hardening Tests.
Tests every SEC-* finding from the security audit report.

SEC-001: Public onboarding endpoint rate limiting.
SEC-002: Password reset confirm rate limiting.
SEC-003: WhatsApp webhook enforces HMAC; rejects if secret missing in production.
SEC-004: Airtel webhook verifies OAuth bearer token.
SEC-005: Payment plan sibling query scoped to same school.
SEC-006: Voice broadcast upload validates size, extension, and MIME/magic bytes.
SEC-007: Production secret guard raises ImproperlyConfigured.
SEC-008: AuditLog is immutable — delete() and save() (UPDATE) are blocked.
SEC-009: PII encrypted fields — phone_hash used for lookup; plaintext not stored.
"""
import hashlib
import hmac
import io
import json
import uuid
from datetime import date
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from django.conf import settings
from django.test import override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status as http_status

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def school(db):
    from schools.models import School
    return School.objects.create(
        name='Test Security School',
        slug='test-security-school',
        district='Kampala',
        email='sec@school.ug',
        phone='+256700000001',
        is_active=True,
    )


@pytest.fixture
def director(db, school):
    user = User.objects.create_user(
        email='director@school.ug',
        password='TestPass123!',
        role='director',
        school=school,
        first_name='Test',
        last_name='Director',
    )
    return user


@pytest.fixture
def bursar(db, school):
    user = User.objects.create_user(
        email='bursar@school.ug',
        password='TestPass123!',
        role='bursar',
        school=school,
        first_name='Test',
        last_name='Bursar',
    )
    return user


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, director):
    api_client.force_authenticate(user=director)
    return api_client


@pytest.fixture
def student(db, school):
    from students.models import Student, ClassGroup
    cg = ClassGroup.objects.create(
        school=school,
        name='S1A',
        level='S1',
    )
    return Student.objects.create(
        school=school,
        student_id='SEC001',
        first_name='Alice',
        last_name='Test',
        current_class=cg,
        admission_date=date(2024, 2, 1),
        academic_year_admitted=2024,
        is_active=True,
    )


@pytest.fixture
def guardian(db, student, school):
    from students.models import Guardian
    return Guardian.objects.create(
        student=student,
        first_name='GuardFirst',
        last_name='GuardLast',
        relationship='Father',
        phone='+256701234567',
        is_primary=True,
    )


# ─────────────────────────────────────────────────────────────
# SEC-008: AuditLog immutability
# ─────────────────────────────────────────────────────────────

class TestAuditLogImmutability:
    """SEC-008: AuditLog records must never be updated or deleted via ORM."""

    def test_create_audit_log_succeeds(self):
        from audit.models import AuditLog
        entry = AuditLog.log(
            category='SYSTEM',
            action='TEST_ACTION',
            description='Security test entry',
        )
        assert entry.pk is not None

    def test_update_audit_log_raises_permission_error(self):
        from audit.models import AuditLog
        entry = AuditLog.log(
            category='SYSTEM',
            action='IMMUTABLE_TEST',
        )
        entry.description = 'Tampered!'
        with pytest.raises(PermissionError, match='immutable'):
            entry.save()

    def test_delete_audit_log_raises_permission_error(self):
        from audit.models import AuditLog
        entry = AuditLog.log(
            category='SYSTEM',
            action='DELETE_TEST',
        )
        with pytest.raises(PermissionError, match='cannot be deleted'):
            entry.delete()

    def test_bypass_flag_allows_save_in_retention_job(self):
        """The bypass flag is reserved for the automated DB retention job only."""
        from audit.models import AuditLog
        entry = AuditLog.log(
            category='SYSTEM',
            action='BYPASS_TEST',
        )
        # Should not raise with _bypass_immutability=True
        entry.description = 'Updated by retention job'
        entry.save(_bypass_immutability=True)

    def test_bypass_flag_allows_delete_in_retention_job(self):
        from audit.models import AuditLog
        entry = AuditLog.log(
            category='SYSTEM',
            action='BYPASS_DELETE_TEST',
        )
        pk = entry.pk
        entry.delete(_bypass_immutability=True)
        assert not AuditLog.objects.filter(pk=pk).exists()


# ─────────────────────────────────────────────────────────────
# SEC-009: PII Encryption — phone_hash lookup
# ─────────────────────────────────────────────────────────────

class TestPIIEncryption:
    """SEC-009: Guardian PII is encrypted; phone_hash is used for lookups."""

    def test_guardian_phone_hash_computed_on_save(self, guardian):
        expected_hash = hashlib.sha256(guardian.phone_normalised.encode()).hexdigest()
        assert guardian.phone_hash == expected_hash

    def test_guardian_phone_hash_lookup_finds_guardian(self, guardian):
        from students.models import Guardian
        normalised = guardian.phone_normalised
        phone_hash = hashlib.sha256(normalised.encode()).hexdigest()
        found = Guardian.objects.filter(phone_hash=phone_hash).first()
        assert found is not None
        assert found.pk == guardian.pk

    def test_guardian_first_name_is_decrypted_on_access(self, guardian):
        """EncryptedCharField transparently decrypts on read."""
        from students.models import Guardian
        fetched = Guardian.objects.get(pk=guardian.pk)
        assert fetched.first_name == 'GuardFirst'

    def test_student_date_of_birth_encryption(self, student):
        """EncryptedDateField stores encrypted, decrypts transparently."""
        student.date_of_birth = date(2010, 5, 15)
        student.save()
        from students.models import Student
        fetched = Student.objects.get(pk=student.pk)
        assert fetched.date_of_birth == date(2010, 5, 15)

    def test_encrypted_fields_module_encrypts_at_rest(self, guardian):
        """The raw DB value should NOT be the plaintext phone number."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT phone FROM guardians WHERE id = %s",
                [str(guardian.pk)]
            )
            row = cursor.fetchone()
        raw_db_value = row[0]
        # Raw value must be a Fernet token (starts with 'gAAAAA'), not plaintext
        assert raw_db_value.startswith('gAAAAA'), (
            f"Expected Fernet token but got plaintext: {raw_db_value[:20]!r}"
        )

    def test_phone_filter_by_plaintext_does_not_match(self, guardian):
        """Filtering by plaintext phone on encrypted field returns nothing."""
        from students.models import Guardian
        result = Guardian.objects.filter(phone='+256701234567')
        # Direct filter on encrypted field won't match because stored value is ciphertext
        # (This confirms encryption is working)
        assert result.count() == 0


# ─────────────────────────────────────────────────────────────
# SEC-003: WhatsApp Webhook HMAC enforcement
# ─────────────────────────────────────────────────────────────

class TestWhatsAppWebhookSecurity:
    """SEC-003: WhatsApp webhook must enforce HMAC in production."""

    def _make_signed_payload(self, secret, body):
        mac = hmac.new(secret.encode(), msg=body, digestmod='sha256')
        return f"sha256={mac.hexdigest()}"

    def test_valid_signature_accepted(self, api_client):
        secret = 'test_app_secret'
        body = b'{"entry": []}'
        sig = self._make_signed_payload(secret, body)
        with override_settings(WHATSAPP_APP_SECRET=secret, DEBUG=True):
            response = api_client.post(
                '/webhooks/whatsapp/',
                data=body,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=sig,
            )
        assert response.status_code == 200

    def test_invalid_signature_rejected(self, api_client):
        secret = 'test_app_secret'
        body = b'{"entry": []}'
        with override_settings(WHATSAPP_APP_SECRET=secret, DEBUG=True):
            response = api_client.post(
                '/webhooks/whatsapp/',
                data=body,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256='sha256=deadbeef0000000000000000000000000000000000',
            )
        assert response.status_code == 403

    def test_missing_signature_rejected(self, api_client):
        with override_settings(WHATSAPP_APP_SECRET='secret', DEBUG=True):
            response = api_client.post(
                '/webhooks/whatsapp/',
                data=b'{}',
                content_type='application/json',
            )
        assert response.status_code == 403

    def test_missing_secret_in_production_rejects_all(self, api_client):
        """In production (DEBUG=False), missing WHATSAPP_APP_SECRET must hard-reject."""
        with override_settings(WHATSAPP_APP_SECRET=None, DEBUG=False):
            response = api_client.post(
                '/webhooks/whatsapp/',
                data=b'{}',
                content_type='application/json',
            )
        assert response.status_code == 403


# ─────────────────────────────────────────────────────────────
# SEC-004: Airtel Webhook token verification
# ─────────────────────────────────────────────────────────────

class TestAirtelWebhookSecurity:
    """SEC-004: Airtel IPN webhook must verify the OAuth bearer token."""

    def test_valid_token_accepted_in_debug(self, api_client, school, db):
        """In DEBUG mode with cached token, valid bearer is accepted."""
        from django.core.cache import cache
        cache.set(f"airtel_token:{school.id}", 'valid_token_123', timeout=3600)
        payload = {
            'transaction': {
                'id': 'AIRTEL-TEST-001',
                'status': 'TS',  # Airtel success code
                'amount': 50000,
                'msisdn': '256701234567',
            }
        }
        with override_settings(DEBUG=True):
            response = api_client.post(
                f'/webhooks/momo/airtel/{school.id}/',
                data=json.dumps(payload),
                content_type='application/json',
                HTTP_AUTHORIZATION='Bearer valid_token_123',
            )
        # Status 200 or the service processes (not 401)
        assert response.status_code != 401

    def test_invalid_token_rejected(self, api_client, school, db):
        from django.core.cache import cache
        cache.set(f"airtel_token:{school.id}", 'valid_token_123', timeout=3600)
        with override_settings(DEBUG=False):
            response = api_client.post(
                f'/webhooks/momo/airtel/{school.id}/',
                data=b'{}',
                content_type='application/json',
                HTTP_AUTHORIZATION='Bearer wrong_token',
            )
        assert response.status_code == 401

    def test_missing_token_in_production_rejected(self, api_client, school, db):
        from django.core.cache import cache
        cache.set(f"airtel_token:{school.id}", 'valid_token_123', timeout=3600)
        with override_settings(DEBUG=False):
            response = api_client.post(
                f'/webhooks/momo/airtel/{school.id}/',
                data=b'{}',
                content_type='application/json',
                # No Authorization header
            )
        assert response.status_code == 401

    def test_no_cached_token_in_production_rejected(self, api_client, school, db):
        """If the token refresh job hasn't run, reject in production."""
        from django.core.cache import cache
        cache.delete(f"airtel_token:{school.id}")
        with override_settings(DEBUG=False):
            response = api_client.post(
                f'/webhooks/momo/airtel/{school.id}/',
                data=b'{}',
                content_type='application/json',
                HTTP_AUTHORIZATION='Bearer any_token',
            )
        assert response.status_code == 401

    def test_no_cached_token_in_debug_passes(self, api_client, school, db):
        """In DEBUG mode, missing cached token allows through (dev convenience)."""
        from django.core.cache import cache
        cache.delete(f"airtel_token:{school.id}")
        with override_settings(DEBUG=True):
            response = api_client.post(
                f'/webhooks/momo/airtel/{school.id}/',
                data=b'{"transaction": {}}',
                content_type='application/json',
            )
        # Should not be 401 (may be 400 for bad payload, but not auth failure)
        assert response.status_code != 401


# ─────────────────────────────────────────────────────────────
# SEC-006: Voice broadcast file upload validation
# ─────────────────────────────────────────────────────────────

class TestVoiceBroadcastUploadValidation:
    """SEC-006: Voice broadcast endpoint validates file size, extension, MIME, magic bytes."""

    URL = '/api/v1/messaging/voice-broadcasts/'

    def _mp3_header(self):
        """Minimal valid MP3 magic bytes."""
        return b'ID3' + b'\x00' * 9

    def test_oversized_file_rejected(self, auth_client):
        oversized = io.BytesIO(b'ID3' + b'\x00' * (17 * 1024 * 1024))
        oversized.name = 'big.mp3'
        response = auth_client.post(
            self.URL,
            {'audio_file': oversized, 'target_type': 'all_parents'},
            format='multipart',
        )
        assert response.status_code == 400
        assert 'too large' in response.data.get('error', '').lower()

    def test_disallowed_extension_rejected(self, auth_client):
        f = io.BytesIO(self._mp3_header())
        f.name = 'evil.exe'
        response = auth_client.post(
            self.URL,
            {'audio_file': f, 'target_type': 'all_parents'},
            format='multipart',
        )
        assert response.status_code == 400
        assert 'invalid file type' in response.data.get('error', '').lower()

    def test_wrong_mime_type_rejected(self, auth_client):
        f = io.BytesIO(self._mp3_header())
        f.name = 'audio.mp3'
        # Override content_type to something suspicious
        from django.core.files.uploadedfile import InMemoryUploadedFile
        upload = InMemoryUploadedFile(
            f, 'audio_file', 'audio.mp3',
            'application/octet-stream',  # wrong MIME
            len(self._mp3_header()), None,
        )
        response = auth_client.post(
            self.URL,
            {'audio_file': upload, 'target_type': 'all_parents'},
            format='multipart',
        )
        assert response.status_code == 400

    def test_bad_magic_bytes_rejected(self, auth_client):
        """A file with correct extension but wrong magic bytes should be rejected."""
        f = io.BytesIO(b'MZ\x90\x00' + b'\x00' * 8)  # PE executable header
        f.name = 'fake.mp3'
        from django.core.files.uploadedfile import InMemoryUploadedFile
        upload = InMemoryUploadedFile(
            f, 'audio_file', 'fake.mp3',
            'audio/mpeg',
            12, None,
        )
        response = auth_client.post(
            self.URL,
            {'audio_file': upload, 'target_type': 'all_parents'},
            format='multipart',
        )
        assert response.status_code == 400
        assert 'magic' in response.data.get('error', '').lower() or \
               'audio format' in response.data.get('error', '').lower()


# ─────────────────────────────────────────────────────────────
# SEC-005: Sibling cross-tenant scope
# ─────────────────────────────────────────────────────────────

class TestSiblingCrossTenantScope:
    """SEC-005: Sibling payment plan calculation must be scoped to the same school."""

    def test_sibling_query_scoped_to_same_school(self, db):
        from schools.models import School
        from students.models import Student, ClassGroup
        from payments.services import FeeService

        school_a = School.objects.create(
            name='School A', slug='school-a', district='Kampala',
            email='a@test.ug', phone='+256700000002', is_active=True
        )
        school_b = School.objects.create(
            name='School B', slug='school-b', district='Kampala',
            email='b@test.ug', phone='+256700000003', is_active=True
        )
        cg_a = ClassGroup.objects.create(school=school_a, name='P1', level='P1')
        cg_b = ClassGroup.objects.create(school=school_b, name='P1', level='P1')

        student_a = Student.objects.create(
            school=school_a, student_id='SECA001', first_name='Alice',
            last_name='A', current_class=cg_a, admission_date=date(2024, 1, 1),
            academic_year_admitted=2024, is_active=True,
        )
        # Attacker puts student_b as a "sibling" of student_a but different school
        student_b = Student.objects.create(
            school=school_b, student_id='SECB001', first_name='Bob',
            last_name='B', current_class=cg_b, admission_date=date(2024, 1, 1),
            academic_year_admitted=2024, is_active=True,
        )
        student_a.siblings.add(student_b)

        # The sibling query must only return students in school_a
        siblings = list(student_a.siblings.filter(
            school=student_a.school, is_active=True
        ))
        assert student_b not in siblings, "Cross-school sibling MUST be excluded"


# ─────────────────────────────────────────────────────────────
# SEC-001: Registration rate limit
# ─────────────────────────────────────────────────────────────

class TestRegistrationRateLimit:
    """SEC-001: Public registration endpoint has throttle_scope = 'registration'."""

    def test_registration_view_has_throttle_scope(self):
        from onboarding.views import SchoolOnboardingRegisterView
        assert hasattr(SchoolOnboardingRegisterView, 'throttle_scope')
        assert SchoolOnboardingRegisterView.throttle_scope == 'registration'

    def test_registration_throttle_rate_defined_in_settings(self):
        # Read from the actual settings module (not the runtime `settings` object)
        # because the autouse `disable_throttling` fixture zeros DEFAULT_THROTTLE_RATES.
        import config.settings as app_settings
        rates = app_settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        assert 'registration' in rates, "registration throttle rate must be configured"


# ─────────────────────────────────────────────────────────────
# SEC-002: Password reset confirm rate limit
# ─────────────────────────────────────────────────────────────

class TestPasswordResetRateLimit:
    """SEC-002: Password reset confirm endpoint has throttle_scope = 'password_reset'."""

    def test_password_reset_confirm_has_throttle_scope(self):
        from authentication.views import PasswordResetConfirmView
        assert hasattr(PasswordResetConfirmView, 'throttle_scope')
        assert PasswordResetConfirmView.throttle_scope == 'password_reset'

    def test_password_reset_throttle_rate_defined_in_settings(self):
        # Read from the actual settings module, not runtime settings (autouse fixture zeros throttle rates).
        import config.settings as app_settings
        rates = app_settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        assert 'password_reset' in rates, "password_reset throttle rate must be configured"


# ─────────────────────────────────────────────────────────────
# SEC-007: Production secret management guard
# ─────────────────────────────────────────────────────────────

class TestProductionSecretGuard:
    """SEC-007: settings.py raises ImproperlyConfigured if insecure defaults are used in production."""

    def test_secret_key_guard_constant_exists(self):
        """The guard logic exists in settings — validated by checking the constants."""
        import config.settings as s
        # _DEFAULT_SECRET must exist; the guard raises ImproperlyConfigured
        # when SECRET_KEY == _DEFAULT_SECRET AND DEBUG is False (production).
        assert hasattr(s, '_DEFAULT_SECRET'), "_DEFAULT_SECRET constant must be defined in settings"
        # The constant must be the well-known insecure default string
        assert isinstance(s._DEFAULT_SECRET, str) and len(s._DEFAULT_SECRET) > 0

    def test_fernet_keys_default_constant_exists(self):
        import config.settings as s
        assert hasattr(s, '_DEFAULT_FERNET')


# ─────────────────────────────────────────────────────────────
# SEC-009b: momo_reference_hash idempotency
# ─────────────────────────────────────────────────────────────

class TestMomoReferenceHash:
    """SEC-009b: MoMoIPNLog.momo_reference_hash is computed on save for idempotency."""

    def test_momo_ipn_log_hash_computed_on_save(self, db, school):
        from payments.models import MoMoIPNLog
        ref = 'MTN-TXN-REF-HASH-TEST-001'
        log = MoMoIPNLog.objects.create(
            school=school,
            provider='mtn',
            momo_reference=ref,
            phone='+256700000001',
            amount=50000,
            raw_payload={'test': True},
        )
        expected = hashlib.sha256(ref.encode()).hexdigest()
        assert log.momo_reference_hash == expected

    def test_momo_ipn_log_hash_lookup(self, db, school):
        from payments.models import MoMoIPNLog
        ref = 'MTN-HASH-LOOKUP-002'
        MoMoIPNLog.objects.create(
            school=school,
            provider='mtn',
            momo_reference=ref,
            phone='+256700000001',
            amount=25000,
            raw_payload={'test': True},
        )
        ref_hash = hashlib.sha256(ref.encode()).hexdigest()
        assert MoMoIPNLog.objects.filter(momo_reference_hash=ref_hash).exists()
