"""
Configuration settings for the DocChat backend application.
Uses Pydantic BaseSettings for environment variable validation.

IMPORTANT SECURITY NOTES:
- Never commit .env files to git
- Use strong, random SECRET_KEY (min 32 characters)
- Rotate keys regularly, especially in production
- Use different keys for dev/staging/production environments
- Never hardcode secrets in code
"""
from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Environment (development, staging, production)
    ENVIRONMENT: str = "development"
    
    # Database configuration
    DATABASE_URL: str
    
    # Security settings
    SECRET_KEY: str
    
    # OpenAI configuration
    OPENAI_API_KEY: str
    
    # Voice processing configuration
    MAX_AUDIO_SIZE_MB: int = 25  # Whisper API limit
    TTS_VOICE_DEFAULT: str = "alloy"  # Default TTS voice (alloy, echo, fable, onyx, nova, shimmer)
    TTS_MODEL: str = "tts-1"  # OpenAI TTS model
    WHISPER_MODEL: str = "whisper-1"  # OpenAI speech recognition model
    AUDIO_STORAGE_PATH: str = "./audio_temp"  # Temporary audio storage directory
    
    # Customer support bot configuration
    SUPPORT_MODEL: str = "gpt-4o-mini"  # Model for the support engine and NLP analysis
    SUPPORT_AGENT_NAME: str = "Support Bot"  # Agent whose linked FAQ document backs search_faq
    ESCALATION_SENTIMENT_THRESHOLD: float = -0.7  # Escalate to a human at or below this sentiment

    # LiveKit configuration (server-side only - never expose the secret to the frontend)
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    LIVEKIT_AGENT_NAME: str = "support-agent"

    # JWT settings
    JWT_EXPIRATION_MINUTES: int = 1440  # 24 hours
    
    # CORS configuration
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    
    @field_validator('ALLOWED_ORIGINS')
    @classmethod
    def parse_allowed_origins(cls, v: str) -> List[str]:
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        if isinstance(v, str):
            # Split by comma and strip whitespace from each origin
            origins = [origin.strip() for origin in v.split(',') if origin.strip()]
            return origins
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables (e.g., DEBUG)
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"


# Global settings instance with validation
settings = Settings()

# Validate production SECRET_KEY strength
if settings.is_production() and len(settings.SECRET_KEY) < 32:
    raise ValueError(
        "SECRET_KEY must be at least 32 characters in production. "
        "Use a strong, random secret key."
    )

