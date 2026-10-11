"""
Tests for BroadcastMedia model and WhatsAppService.upload_media.
US-B01/US-B02: Media upload pipeline.
"""
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from schools.models import School
from authentication.models import User
from messaging.models import BroadcastMedia
from messaging.services import WhatsAppService


class BroadcastMediaModelTests(TestCase):
    """Tests for the BroadcastMedia model."""

    def setUp(self):
        self.school = School.objects.create(
            name='Media Test School',
            slug='media-test-school',
            district='Kampala',
            phone='+256701234567',
            email='media@school.ug',
            school_type='primary',
        )

    def _create_media(self, **kwargs):
        school = kwargs.pop('school', self.school)
        defaults = {
            'school': school,
            'media_file': 'test/audio.ogg',
            'media_type': 'voice',
            'original_filename': 'announcement.ogg',
            'file_size_bytes': 1024,
            'meta_upload_status': 'uploaded',
            'whatsapp_media_id': 'meta_123',
            'expires_at': timezone.now() + timedelta(days=30),
        }
        defaults.update(kwargs)
        return BroadcastMedia.objects.create(**defaults)

    def test_is_expired_when_past_expiry(self):
        media = self._create_media(expires_at=timezone.now() - timedelta(hours=1))
        self.assertTrue(media.is_expired)

    def test_is_expired_when_no_expiry(self):
        media = self._create_media(expires_at=None)
        self.assertTrue(media.is_expired)

    def test_is_not_expired_when_future(self):
        media = self._create_media(expires_at=timezone.now() + timedelta(days=15))
        self.assertFalse(media.is_expired)

    def test_is_ready_when_uploaded_and_valid(self):
        media = self._create_media(
            meta_upload_status='uploaded',
            whatsapp_media_id='mid_123',
            expires_at=timezone.now() + timedelta(days=25),
        )
        self.assertTrue(media.is_ready)

    def test_is_not_ready_when_pending(self):
        media = self._create_media(meta_upload_status='pending')
        self.assertFalse(media.is_ready)

    def test_is_not_ready_when_expired(self):
        media = self._create_media(
            meta_upload_status='uploaded',
            whatsapp_media_id='mid_123',
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(media.is_ready)

    def test_str_representation(self):
        media = self._create_media(original_filename='morning_announcement.ogg')
        self.assertIn('Voice Note', str(media))
        self.assertIn('morning_announcement.ogg', str(media))


class UploadMediaTests(TestCase):
    """Tests for WhatsAppService.upload_media."""

    def setUp(self):
        self.school = School.objects.create(
            name='Upload Test School',
            slug='upload-test-school',
            district='Kampala',
            phone='+256701234567',
            email='upload@school.ug',
            school_type='primary',
        )
        self.user = User.objects.create_user(
            email='uploader@school.ug',
            password='uploader_password_123',
            role='teacher',
            school=self.school,
            first_name='Uploader',
            last_name='Teacher',
        )

    @patch('messaging.services.requests.post')
    def test_upload_media_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': 'meta_media_id_456'}
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
            f.write(b'OggS' + b'\x00' * 500)
            tmp_path = f.name

        try:
            media = WhatsAppService.upload_media(
                school=self.school,
                file_path=tmp_path,
                mime_type='audio/ogg',
                media_type='voice',
                description='Test announcement',
                uploaded_by=self.user,
            )
            self.assertEqual(media.whatsapp_media_id, 'meta_media_id_456')
            self.assertEqual(media.meta_upload_status, 'uploaded')
            self.assertIsNotNone(media.expires_at)
            self.assertTrue(media.is_ready)
            self.assertEqual(media.uploaded_by, self.user)
        finally:
            os.unlink(tmp_path)

    @patch('messaging.services.requests.post')
    def test_upload_media_api_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
            f.write(b'OggS' + b'\x00' * 500)
            tmp_path = f.name

        try:
            with self.assertRaises(RuntimeError):
                WhatsAppService.upload_media(
                    school=self.school,
                    file_path=tmp_path,
                    mime_type='audio/ogg',
                    uploaded_by=self.user,
                )
            # Verify failed status was saved
            media = BroadcastMedia.objects.last()
            self.assertEqual(media.meta_upload_status, 'failed')
        finally:
            os.unlink(tmp_path)

    def test_upload_media_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            WhatsAppService.upload_media(
                school=self.school,
                file_path='/nonexistent/audio.ogg',
                mime_type='audio/ogg',
            )
