"""
Tests for VoiceBroadcastView API and process_voice_broadcast task.
US-B01/US-B02: Voice broadcasts to parents.
"""
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from schools.models import School
from authentication.models import User
from messaging.models import BroadcastMedia, MessageLog
from messaging.tasks import process_voice_broadcast


class VoiceBroadcastAPITests(APITestCase):
    """Tests for VoiceBroadcastView endpoints."""

    def setUp(self):
        self.school = School.objects.create(
            name='Voice Broadcast School', slug='voice-broadcast',
            district='Kampala', phone='0700000000',
            email='admin@voice.ug', school_type='primary'
        )
        self.user = User.objects.create_user(
            email='bursar@voice.ug', password='password123',
            role='bursar', school=self.school
        )
        self.client.force_authenticate(user=self.user)

    @patch('messaging.audio_processor.AudioProcessor.compress_audio')
    @patch('messaging.services.WhatsAppService.upload_media')
    @patch('messaging.tasks.process_voice_broadcast.apply_async')
    def test_voice_broadcast_upload_and_dispatch(self, mock_apply_async, mock_upload, mock_compress):
        """Uploading audio file successfully triggers compression, upload, and async celery task."""
        # Setup mocks
        mock_compress.return_value = {
            'output_path': 'test_compressed.ogg',
            'success': True
        }
        
        media_mock = MagicMock()
        media_mock.id = '12345678-1234-5678-1234-567812345678'
        media_mock.whatsapp_media_id = 'meta_audio_999'
        media_mock.is_ready = True
        mock_upload.return_value = media_mock

        # Create dummy file to upload with valid ID3 magic bytes
        dummy_mp3_content = b"ID3\x04\x00\x00\x00\x00\x00\x00dummy mp3 data"
        audio_file = SimpleUploadedFile("announcement.mp3", dummy_mp3_content, content_type="audio/mpeg")

        response = self.client.post(
            '/api/v1/messaging/voice-broadcasts/',
            {
                'audio_file': audio_file,
                'recipient_phones': ['256701111111', '256702222222'],
                'description': 'Test voice broadcast description'
            },
            format='multipart'
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['whatsapp_media_id'], 'meta_audio_999')
        
        # Verify compressor was called
        mock_compress.assert_called_once()
        
        # Verify WABA upload was called
        mock_upload.assert_called_once()
        
        # Verify Celery apply_async task was called with correct args
        mock_apply_async.assert_called_once()
        call_args = mock_apply_async.call_args
        self.assertEqual(call_args.kwargs['args'][0], '12345678-1234-5678-1234-567812345678')
        self.assertIn('256701111111', call_args.kwargs['args'][1])


class ProcessVoiceBroadcastTaskTests(TestCase):
    """Tests for process_voice_broadcast Celery task."""

    def setUp(self):
        self.school = School.objects.create(
            name='Voice Broadcast School Task', slug='voice-broadcast-task',
            district='Kampala', phone='0700000000',
            email='admin@voice-task.ug', school_type='primary'
        )
        self.user = User.objects.create_user(
            email='teacher@voice.ug', password='password123',
            role='teacher', school=self.school
        )
        # Create media record in DB
        self.media = BroadcastMedia.objects.create(
            school=self.school,
            media_file='broadcast_media/voice.ogg',
            media_type='voice',
            original_filename='announcement.ogg',
            file_size_bytes=1024,
            meta_upload_status='uploaded',
            whatsapp_media_id='meta_waba_101',
            expires_at=timezone.now() + timedelta(days=30),
            uploaded_by=self.user
        )

    @patch('messaging.services.WhatsAppService.send_audio_message')
    def test_task_sends_to_recipients_and_logs(self, mock_send):
        mock_send.return_value = ('msg_waba_id', True)
        
        recipients = [f"2567000000{i:02d}" for i in range(10)]
        process_voice_broadcast(str(self.media.id), recipients)
        
        # Verify WhatsAppService.send_audio_message was called for all
        self.assertEqual(mock_send.call_count, 10)
        
        # Check logs in DB
        logs = MessageLog.objects.filter(school=self.school, template_type='broadcast')
        self.assertEqual(logs.count(), 10)
        for log in logs:
            self.assertEqual(log.status, 'sent')
            # Voice broadcasts are intentionally logged as channel='voice'
            # so the frontend filter for 'Voice Broadcast' works correctly
            self.assertEqual(log.channel, 'voice')
            self.assertEqual(log.whatsapp_message_id, 'msg_waba_id')

    @patch('messaging.services.WhatsAppService.send_audio_message')
    @patch('time.sleep')
    def test_task_chunking_and_rate_limiting(self, mock_sleep, mock_send):
        mock_send.return_value = ('msg_waba_id', True)
        
        # 120 recipients -> should sleep twice because 120 has 3 chunks (chunk size = 50)
        recipients = [f"2567000000{i:02d}" for i in range(120)]
        
        process_voice_broadcast(str(self.media.id), recipients)
        
        self.assertEqual(mock_send.call_count, 120)
        # Verify sleep was called 2 times between 3 chunks
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(2)
