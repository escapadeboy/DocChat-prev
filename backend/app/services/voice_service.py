"""
Voice service for audio transcription (Whisper) and text-to-speech (TTS) processing.
"""
import io
import logging
import time
import random
from typing import Optional
from functools import wraps
from fastapi import HTTPException
from openai import OpenAI, RateLimitError, APIError

from app.config import settings
from app.services.document_service import get_openai_client


# ============================================================================
# Custom Exceptions
# ============================================================================

class VoiceServiceError(Exception):
    """Base exception for voice service errors."""
    pass


class AudioValidationError(VoiceServiceError):
    """Raised when audio validation fails."""
    pass


class TranscriptionError(VoiceServiceError):
    """Raised when transcription fails."""
    pass


class TTSError(VoiceServiceError):
    """Raised when TTS generation fails."""
    pass


class VoiceRateLimitError(VoiceServiceError):
    """Raised when API rate limit is hit."""
    pass


logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

MAX_AUDIO_SIZE_MB = 25  # Whisper API limit
MAX_TTS_TEXT_LENGTH = 4096  # TTS API limit
VALID_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
VALID_AUDIO_FORMATS = ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"]
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

# Magic bytes for audio format validation
AUDIO_SIGNATURES = {
    "mp3": [b'ID3', b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'],
    "wav": [b'RIFF'],
    "m4a": [b'\x00\x00\x00\x18ftyp', b'\x00\x00\x00\x1cftyp', b'\x00\x00\x00 ftyp'],
    "webm": [b'\x1a\x45\xdf\xa3'],
}


# ============================================================================
# Retry Logic with Exponential Backoff
# ============================================================================

def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (VoiceRateLimitError, APIError, RateLimitError)
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff calculation
        exceptions: Tuple of exceptions to retry on
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(f"{func.__name__} failed after {max_retries} retries: {e}")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    
                    # Add jitter (±25% randomness) to prevent thundering herd
                    jitter = delay * 0.25
                    delay = delay + random.uniform(-jitter, jitter)
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    
                    time.sleep(delay)
            
        return wrapper
    return decorator


# ============================================================================
# Audio Validation
# ============================================================================


def validate_audio_file(file_bytes: bytes, max_size_mb: int = 25) -> bool:
    """
    Validate audio file size and format using magic bytes.
    
    Args:
        file_bytes: Audio file content as bytes
        max_size_mb: Maximum file size in megabytes (default: 25)
        
    Returns:
        True if valid
        
    Raises:
        AudioValidationError: If file is invalid (too large or unsupported format)
    """
    try:
        # Check file size
        file_size_mb = len(file_bytes) / (1024 * 1024)
        
        if len(file_bytes) > max_size_mb * 1024 * 1024:
            logger.warning(f"Audio file too large: {file_size_mb:.2f}MB (max: {max_size_mb}MB)")
            raise AudioValidationError(
                f"Audio file exceeds maximum size of {max_size_mb}MB. Current size: {file_size_mb:.2f}MB"
            )
        
        # Check for empty file
        if len(file_bytes) == 0:
            logger.warning("Empty audio file received")
            raise AudioValidationError("Audio file is empty")
        
        # Validate audio format using magic bytes
        is_valid_format = False
        detected_format = None
        
        for format_name, signatures in AUDIO_SIGNATURES.items():
            for signature in signatures:
                if file_bytes.startswith(signature):
                    is_valid_format = True
                    detected_format = format_name
                    break
            if is_valid_format:
                break
        
        if not is_valid_format:
            logger.warning(f"Unsupported audio format detected (first 20 bytes: {file_bytes[:20].hex()})")
            raise AudioValidationError(
                f"Unsupported audio format. Supported formats: {', '.join(VALID_AUDIO_FORMATS)}"
            )
        
        logger.info(f"Audio file validated: format={detected_format}, size={file_size_mb:.2f}MB")
        return True
        
    except AudioValidationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating audio file: {str(e)}", exc_info=True)
        raise AudioValidationError(f"Failed to validate audio file: {str(e)}")


# ============================================================================
# Transcription
# ============================================================================

@retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
def transcribe_audio(audio_bytes: bytes, language: str = "en") -> str:
    """
    Transcribe audio to text using OpenAI Whisper API with enhanced error handling.
    
    Args:
        audio_bytes: Audio file content as bytes
        language: Language code (default: "en" for English)
        
    Returns:
        Transcribed text string
        
    Raises:
        AudioValidationError: If audio file is invalid
        VoiceRateLimitError: If API rate limit is exceeded
        TranscriptionError: If transcription fails
    """
    if not audio_bytes:
        raise TranscriptionError("Audio bytes cannot be empty")
    
    # Validate audio file first
    try:
        validate_audio_file(audio_bytes, max_size_mb=MAX_AUDIO_SIZE_MB)
    except AudioValidationError as e:
        logger.error(f"Audio validation failed: {e}")
        raise
    
    audio_size_mb = len(audio_bytes) / (1024 * 1024)
    logger.info(f"Starting audio transcription: size={audio_size_mb:.2f}MB, language={language}")
    
    try:
        client = get_openai_client()
        if client is None:
            raise TranscriptionError("OpenAI client not initialized. Please configure OPENAI_API_KEY.")
        
        # Create in-memory file object from bytes
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.mp3"  # Give it a name with extension
        
        # Call Whisper API
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=language if language else None
        )
        
        transcribed_text = response.text.strip()
        
        if not transcribed_text:
            logger.warning("Whisper returned empty transcription")
            raise TranscriptionError("No speech detected in audio. Please try speaking more clearly.")
        
        logger.info(f"Audio transcription successful: {len(transcribed_text)} characters")
        return transcribed_text
        
    except RateLimitError as e:
        logger.error(f"OpenAI rate limit hit: {e}")
        raise VoiceRateLimitError("API rate limit exceeded. Please try again in a few moments.")
    
    except APIError as e:
        error_msg = str(e).lower()
        if "invalid_audio" in error_msg or "corrupted" in error_msg:
            logger.error(f"Corrupted audio file: {e}")
            raise AudioValidationError("Audio file appears to be corrupted or in an invalid format. Please try recording again.")
        logger.error(f"OpenAI API error: {e}")
        raise TranscriptionError(f"Transcription failed: {str(e)}")
    
    except TranscriptionError:
        raise
    except AudioValidationError:
        raise
    except VoiceRateLimitError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error transcribing audio: {e}", exc_info=True)
        raise TranscriptionError(f"An unexpected error occurred during transcription: {str(e)}")


# ============================================================================
# Text-to-Speech
# ============================================================================

@retry_with_exponential_backoff(max_retries=3, base_delay=1.0)
def text_to_speech(text: str, voice: str = "alloy") -> bytes:
    """
    Convert text to speech using OpenAI TTS API with enhanced validation and error handling.
    
    Args:
        text: Text to convert to speech
        voice: Voice name (options: alloy, echo, fable, onyx, nova, shimmer)
        
    Returns:
        Audio content as bytes (MP3 format)
        
    Raises:
        TTSError: If TTS generation fails
        VoiceRateLimitError: If API rate limit is exceeded
    """
    # Validate text is not empty
    if not text or not text.strip():
        logger.warning("Empty text provided for TTS")
        raise TTSError("Text cannot be empty")
    
    # Validate text length
    if len(text) > MAX_TTS_TEXT_LENGTH:
        logger.warning(f"Text too long for TTS: {len(text)} chars (max: {MAX_TTS_TEXT_LENGTH})")
        raise TTSError(
            f"Text exceeds maximum length of {MAX_TTS_TEXT_LENGTH} characters. "
            f"Current length: {len(text)} characters."
        )
    
    # Validate voice parameter
    if voice not in VALID_VOICES:
        logger.warning(f"Invalid voice requested: {voice}")
        raise TTSError(f"Invalid voice '{voice}'. Valid options: {', '.join(VALID_VOICES)}")
    
    logger.info(f"Starting text-to-speech: text_length={len(text)}, voice={voice}")
    
    try:
        client = get_openai_client()
        if client is None:
            raise TTSError("OpenAI client not initialized. Please configure OPENAI_API_KEY.")
        
        # Call TTS API
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        
        # Read audio content as bytes
        audio_bytes = response.read()
        
        if not audio_bytes or len(audio_bytes) == 0:
            logger.error("TTS API returned empty audio")
            raise TTSError("Failed to generate audio. Please try again.")
        
        audio_size_kb = len(audio_bytes) / 1024
        logger.info(f"Text-to-speech successful: generated {audio_size_kb:.2f}KB audio")
        return audio_bytes
        
    except RateLimitError as e:
        logger.error(f"TTS rate limit hit: {e}")
        raise VoiceRateLimitError("API rate limit exceeded. Please try again shortly.")
    
    except APIError as e:
        logger.error(f"TTS API error: {e}")
        raise TTSError(f"Text-to-speech generation failed: {str(e)}")
    
    except TTSError:
        raise
    except VoiceRateLimitError:
        raise
    except Exception as e:
        logger.error(f"Unexpected TTS error: {e}", exc_info=True)
        raise TTSError(f"An unexpected error occurred during speech generation: {str(e)}")

