"""
Tests for messaging.audio_processor.AudioProcessor.
US-B01/US-B02: Voice announcement transcoding pipeline.
"""
import os
import tempfile
from unittest.mock import patch, MagicMock
from django.test import TestCase
from messaging.audio_processor import AudioProcessor


class AudioProcessorTests(TestCase):
    """Tests for the AudioProcessor compression service."""

    def test_compress_audio_file_not_found(self):
        """Raises FileNotFoundError for non-existent input."""
        with self.assertRaises(FileNotFoundError):
            AudioProcessor.compress_audio('/nonexistent/audio.wav')

    @patch('messaging.audio_processor.shutil.which', return_value=None)
    def test_compress_audio_ffmpeg_not_installed(self, mock_which):
        """Raises RuntimeError when ffmpeg is not available."""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b'RIFF' + b'\x00' * 100)
            tmp_path = f.name
        try:
            with self.assertRaises(RuntimeError) as ctx:
                AudioProcessor.compress_audio(tmp_path)
            self.assertIn('ffmpeg is not installed', str(ctx.exception))
        finally:
            os.unlink(tmp_path)

    @patch('messaging.audio_processor.subprocess.run')
    @patch('messaging.audio_processor.shutil.which', return_value='/usr/bin/ffmpeg')
    def test_compress_audio_success(self, mock_which, mock_run):
        """Successfully compresses audio and returns metadata."""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b'RIFF' + b'\x00' * 10000)
            tmp_input = f.name

        # Create fake output
        tmp_output = tmp_input.replace('.wav', '.ogg')
        with open(tmp_output, 'wb') as f:
            f.write(b'OggS' + b'\x00' * 500)

        mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='')

        try:
            result = AudioProcessor.compress_audio(tmp_input)
            self.assertTrue(result['success'])
            self.assertEqual(result['output_path'], tmp_output)
            self.assertGreater(result['input_size'], 0)
            self.assertGreater(result['output_size'], 0)
            self.assertGreater(result['compression_ratio'], 0)

            # Verify ffmpeg was called with correct args
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            self.assertIn('ffmpeg', call_args)
            self.assertIn('-ac', call_args)
            self.assertIn('1', call_args)  # Mono
            self.assertIn('-ar', call_args)
            self.assertIn('16000', call_args)  # 16kHz
            self.assertIn('-b:a', call_args)
            self.assertIn('16k', call_args)  # 16kbps
            self.assertIn('-c:a', call_args)
            self.assertIn('libopus', call_args)  # Opus codec
        finally:
            for p in [tmp_input, tmp_output]:
                if os.path.exists(p):
                    os.unlink(p)

    @patch('messaging.audio_processor.subprocess.run')
    @patch('messaging.audio_processor.shutil.which', return_value='/usr/bin/ffmpeg')
    def test_compress_audio_ffmpeg_failure(self, mock_which, mock_run):
        """Raises RuntimeError when ffmpeg returns non-zero exit code."""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b'RIFF' + b'\x00' * 100)
            tmp_path = f.name

        mock_run.return_value = MagicMock(returncode=1, stderr='codec error', stdout='')

        try:
            with self.assertRaises(RuntimeError) as ctx:
                AudioProcessor.compress_audio(tmp_path)
            self.assertIn('ffmpeg failed', str(ctx.exception))
        finally:
            os.unlink(tmp_path)

    @patch('messaging.audio_processor.subprocess.run')
    @patch('messaging.audio_processor.shutil.which', return_value='/usr/bin/ffmpeg')
    def test_compress_audio_timeout(self, mock_which, mock_run):
        """Raises RuntimeError on ffmpeg timeout."""
        import subprocess
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b'RIFF' + b'\x00' * 100)
            tmp_path = f.name

        mock_run.side_effect = subprocess.TimeoutExpired(cmd='ffmpeg', timeout=120)

        try:
            with self.assertRaises(RuntimeError) as ctx:
                AudioProcessor.compress_audio(tmp_path)
            self.assertIn('timed out', str(ctx.exception))
        finally:
            os.unlink(tmp_path)

    def test_compress_audio_custom_output_path(self):
        """Respects custom output path."""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b'RIFF' + b'\x00' * 100)
            tmp_input = f.name

        custom_output = tmp_input.replace('.wav', '_custom.ogg')

        with patch('messaging.audio_processor.subprocess.run') as mock_run, \
             patch('messaging.audio_processor.shutil.which', return_value='/usr/bin/ffmpeg'):
            # Create fake output at custom path
            with open(custom_output, 'wb') as f:
                f.write(b'OggS' + b'\x00' * 50)
            mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='')

            result = AudioProcessor.compress_audio(tmp_input, output_path=custom_output)
            self.assertEqual(result['output_path'], custom_output)

        for p in [tmp_input, custom_output]:
            if os.path.exists(p):
                os.unlink(p)

    def test_is_ffmpeg_available(self):
        """is_ffmpeg_available returns boolean based on shutil.which."""
        with patch('messaging.audio_processor.shutil.which', return_value='/usr/bin/ffmpeg'):
            self.assertTrue(AudioProcessor.is_ffmpeg_available())
        with patch('messaging.audio_processor.shutil.which', return_value=None):
            self.assertFalse(AudioProcessor.is_ffmpeg_available())

    def test_validate_for_whatsapp_file_not_found(self):
        """Returns invalid result for missing files."""
        result = AudioProcessor.validate_for_whatsapp('/nonexistent/audio.ogg')
        self.assertFalse(result['valid'])
        self.assertIn('File not found', result['errors'])

    def test_validate_for_whatsapp_too_large(self):
        """Flags files exceeding size limit."""
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
            # Write >16MB
            f.write(b'\x00' * (17 * 1024 * 1024))
            tmp_path = f.name

        try:
            with patch.object(AudioProcessor, 'get_audio_duration', return_value=60.0):
                result = AudioProcessor.validate_for_whatsapp(tmp_path)
                self.assertFalse(result['valid'])
                self.assertTrue(any('too large' in e for e in result['errors']))
        finally:
            os.unlink(tmp_path)
