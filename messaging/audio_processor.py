"""
US-B01/US-B02: Audio compression service.
Transcodes browser-recorded audio to WhatsApp-compliant Opus Ogg
optimized for Ugandan cellular networks (low bandwidth).
"""
import logging
import os
import subprocess
import shutil

logger = logging.getLogger('messaging')


class AudioProcessor:
    """
    Compresses audio files using ffmpeg for WhatsApp voice note delivery.
    Target: mono, 16kHz sampling, 16kbps bitrate, Opus codec in Ogg container.
    Produces ~120KB per minute of speech.
    """

    FFMPEG_COMMAND = [
        'ffmpeg', '-y',  # Overwrite output
        '-i', '{input_path}',
        '-vn',  # No video
        '-ac', '1',  # Mono
        '-ar', '16000',  # 16kHz sampling rate
        '-b:a', '16k',  # 16kbps bitrate
        '-c:a', 'libopus',  # Opus codec
        '{output_path}',
    ]

    @classmethod
    def is_ffmpeg_available(cls):
        """Check if ffmpeg is installed and accessible."""
        return shutil.which('ffmpeg') is not None

    @classmethod
    def compress_audio(cls, input_path, output_path=None):
        """
        Compress audio file to WhatsApp-compliant Opus Ogg format.

        Args:
            input_path: Path to input audio file (WebM, Ogg, WAV, MP3, etc.)
            output_path: Optional output path. Defaults to input_path with .ogg extension.

        Returns:
            dict with keys:
                - output_path: Path to compressed file
                - input_size: Input file size in bytes
                - output_size: Output file size in bytes
                - compression_ratio: float
                - success: bool

        Raises:
            FileNotFoundError: If input file doesn't exist
            RuntimeError: If ffmpeg fails or is not installed
        """
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"Input audio file not found: {input_path}")

        if not cls.is_ffmpeg_available():
            raise RuntimeError(
                "ffmpeg is not installed or not in PATH. "
                "Install with: apt-get install ffmpeg (Ubuntu) or brew install ffmpeg (macOS)"
            )

        if output_path is None:
            base, _ = os.path.splitext(input_path)
            output_path = base + '.ogg'

        input_size = os.path.getsize(input_path)

        cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-vn',
            '-ac', '1',
            '-ar', '16000',
            '-b:a', '16k',
            '-c:a', 'libopus',
            output_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout for large files
            )
            if result.returncode != 0:
                logger.error(f"ffmpeg compression failed: {result.stderr}")
                raise RuntimeError(f"ffmpeg failed with exit code {result.returncode}: {result.stderr}")

            if not os.path.isfile(output_path):
                raise RuntimeError("ffmpeg completed but output file was not created")

            output_size = os.path.getsize(output_path)
            compression_ratio = input_size / output_size if output_size > 0 else 0

            logger.info(
                f"Audio compressed: {input_path} ({input_size} bytes) -> "
                f"{output_path} ({output_size} bytes), ratio={compression_ratio:.1f}x"
            )

            return {
                'output_path': output_path,
                'input_size': input_size,
                'output_size': output_size,
                'compression_ratio': compression_ratio,
                'success': True,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg timed out processing {input_path}")
            raise RuntimeError(f"ffmpeg timed out after 120s processing {input_path}")

    @classmethod
    def get_audio_duration(cls, file_path):
        """
        Get duration of an audio file in seconds using ffprobe.

        Args:
            file_path: Path to audio file

        Returns:
            float: Duration in seconds, or None if unable to determine
        """
        if not os.path.isfile(file_path):
            return None

        try:
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'quiet',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError):
            pass
        return None

    @classmethod
    def validate_for_whatsapp(cls, file_path, max_size_mb=16, max_duration_seconds=300):
        """
        Validate that an audio file meets WhatsApp requirements.
        WhatsApp limit: 16MB file size, 5 minutes voice note.

        Args:
            file_path: Path to audio file
            max_size_mb: Maximum file size in MB (default 16)
            max_duration_seconds: Maximum duration in seconds (default 300 = 5 min)

        Returns:
            dict with keys:
                - valid: bool
                - errors: list of error messages
                - size_mb: file size in MB
                - duration_seconds: duration or None
        """
        errors = []

        if not os.path.isfile(file_path):
            return {'valid': False, 'errors': ['File not found'], 'size_mb': 0, 'duration_seconds': None}

        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)

        if size_mb > max_size_mb:
            errors.append(f"File too large: {size_mb:.1f}MB (max {max_size_mb}MB)")

        duration = cls.get_audio_duration(file_path)
        if duration and duration > max_duration_seconds:
            errors.append(f"Duration too long: {duration:.0f}s (max {max_duration_seconds}s)")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'size_mb': round(size_mb, 2),
            'duration_seconds': round(duration, 1) if duration else None,
        }
