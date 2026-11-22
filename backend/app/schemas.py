"""
Pydantic schemas for request/response validation.
"""
import re
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime


# ============================================================================
# Auth Schemas
# ============================================================================

class RegisterRequest(BaseModel):
    """Schema for user registration request."""
    phone_number: str = Field(..., description="10-digit Indian phone number")
    password: str = Field(..., min_length=12, description="User password (min 12 characters)")
    name: str = Field(..., min_length=1, max_length=100, description="User full name")
    
    @field_validator('phone_number')
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        """Validate 10-digit Indian phone number."""
        # Remove whitespace and dashes
        cleaned = v.strip().replace(" ", "").replace("-", "")
        # Check if it's exactly 10 digits starting with 6-9
        if not cleaned.isdigit() or len(cleaned) != 10:
            raise ValueError("Phone number must be exactly 10 digits")
        first_digit = int(cleaned[0])
        if first_digit < 6 or first_digit > 9:
            raise ValueError("Phone number must start with 6, 7, 8, or 9")
        return cleaned
    
    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Validate password meets security requirements.
        
        Requirements:
        - Minimum 12 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        """
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        
        if not re.search(r'[A-Z]', v):
            raise ValueError("Password must contain at least one uppercase letter")
        
        if not re.search(r'[a-z]', v):
            raise ValueError("Password must contain at least one lowercase letter")
        
        if not re.search(r'\d', v):
            raise ValueError("Password must contain at least one digit")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;/]', v):
            raise ValueError("Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>_-+=[]\\;/)")
        
        return v
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name is not empty after stripping."""
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class LoginRequest(BaseModel):
    """Schema for user login request."""
    phone_number: str = Field(..., description="10-digit Indian phone number")
    password: str = Field(..., description="User password")
    
    @field_validator('phone_number')
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        """Validate 10-digit Indian phone number."""
        # Remove whitespace and dashes
        cleaned = v.strip().replace(" ", "").replace("-", "")
        # Check if it's exactly 10 digits starting with 6-9
        if not cleaned.isdigit() or len(cleaned) != 10:
            raise ValueError("Phone number must be exactly 10 digits")
        first_digit = int(cleaned[0])
        if first_digit < 6 or first_digit > 9:
            raise ValueError("Phone number must start with 6, 7, 8, or 9")
        return cleaned


class UserInfo(BaseModel):
    """User information in response."""
    id: int
    phone_number: str
    name: str
    
    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Schema for login response."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user: UserInfo = Field(..., description="User information")


# ============================================================================
# Document Schemas
# ============================================================================

class DocumentResponse(BaseModel):
    """Schema for document response."""
    id: int
    original_name: str = Field(..., description="Original filename")
    file_size: int = Field(..., ge=0, description="File size in bytes")
    upload_date: datetime
    is_processed: bool = Field(..., description="Whether document has been processed")
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Schema for list of documents."""
    documents: List[DocumentResponse] = Field(..., description="List of documents")


# ============================================================================
# Agent Schemas
# ============================================================================

class CreateAgentRequest(BaseModel):
    """Schema for creating an agent."""
    name: str = Field(..., min_length=1, max_length=100, description="Agent name")
    ai_model: Literal["gpt-4", "gpt-3.5-turbo"] = Field(..., description="AI model to use")
    document_ids: List[int] = Field(..., min_length=1, description="List of document IDs to associate with agent")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate agent name is not empty after stripping."""
        if not v.strip():
            raise ValueError("Agent name cannot be empty")
        return v.strip()
    
    @field_validator('document_ids')
    @classmethod
    def validate_document_ids(cls, v: List[int]) -> List[int]:
        """Validate document IDs are positive integers."""
        if not v:
            raise ValueError("At least one document ID is required")
        if any(doc_id <= 0 for doc_id in v):
            raise ValueError("Document IDs must be positive integers")
        return v


class AgentResponse(BaseModel):
    """Schema for agent response."""
    id: int
    name: str
    ai_model: str
    created_at: datetime
    document_count: int = Field(..., ge=0, description="Number of documents associated with agent")
    
    class Config:
        from_attributes = True


class UpdateAgentRequest(BaseModel):
    """Schema for updating an agent."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Agent name")
    system_prompt: Optional[str] = Field(None, max_length=2000, description="System prompt for the agent")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate agent name is not empty after stripping."""
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Agent name cannot be empty")
            return stripped
        return v


# ============================================================================
# Chat Schemas
# ============================================================================

class ChatRequest(BaseModel):
    """Schema for chat request."""
    message: str = Field(..., min_length=1, max_length=5000, description="User question/message")
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate message is not empty after stripping."""
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()


class AgentChatRequest(BaseModel):
    """Schema for agent-based chat request."""
    agent_id: int = Field(..., gt=0, description="Agent ID")
    message: str = Field(..., min_length=1, max_length=5000, description="User question/message")
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate message is not empty after stripping."""
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()


class Source(BaseModel):
    """Source information for chat response."""
    chunk_id: int = Field(..., description="Chunk ID from document")
    text: str = Field(..., description="Text content from chunk")


class ChatResponse(BaseModel):
    """Schema for chat response."""
    answer: str = Field(..., description="AI-generated answer")
    sources: List[Source] = Field(..., description="List of source chunks used for the answer")
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow(), description="Response timestamp")


class ChatSessionCreate(BaseModel):
    """Schema for creating a chat session."""
    document_id: Optional[int] = Field(None, description="Document ID to associate with session")
    title: str = Field(..., min_length=1, max_length=200, description="Session title")
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is not empty after stripping."""
        if not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()


class ChatSessionResponse(BaseModel):
    """Schema for chat session response."""
    id: int
    owner_id: int
    document_id: Optional[int]
    title: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChatMessageCreate(BaseModel):
    """Schema for creating a chat message."""
    role: Literal["user", "assistant"] = Field(..., description="Message role")
    content: str = Field(..., min_length=1, max_length=10000, description="Message content")
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate content is not empty after stripping."""
        if not v.strip():
            raise ValueError("Content cannot be empty")
        return v.strip()


class ChatMessageResponse(BaseModel):
    """Schema for chat message response."""
    id: int
    session_id: int
    role: str
    content: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============================================================================
# Common Schemas
# ============================================================================

class ErrorResponse(BaseModel):
    """Schema for error response."""
    detail: str = Field(..., description="Error message")
    status_code: int = Field(..., ge=400, le=599, description="HTTP status code")


class APIResponse(BaseModel):
    """Generic API response wrapper."""
    status: str = Field(..., description="Response status (success or error)")
    data: Optional[dict] = Field(None, description="Response data")
    error: Optional[str] = Field(None, description="Error message if status is error")


# ============================================================================
# Voice Schemas
# ============================================================================

class TranscribeResponse(BaseModel):
    """Schema for audio transcription response."""
    text: str = Field(..., description="Transcribed text from audio")
    language: str = Field(..., description="Language code used for transcription")


class TextToSpeechRequest(BaseModel):
    """Schema for text-to-speech request."""
    text: str = Field(..., min_length=1, max_length=4096, description="Text to convert to speech")
    voice: str = Field(default="alloy", description="Voice: alloy, echo, fable, onyx, nova, shimmer")
    
    @field_validator('voice')
    @classmethod
    def validate_voice(cls, v: str) -> str:
        """Validate voice parameter against valid options."""
        from app.services.voice_service import VALID_VOICES
        if v not in VALID_VOICES:
            raise ValueError(f"Invalid voice. Must be one of: {', '.join(VALID_VOICES)}")
        return v


class VoiceChatRequest(BaseModel):
    """Schema for voice chat request (text or audio input)."""
    agent_id: int = Field(..., description="Agent ID to chat with")
    text: Optional[str] = Field(None, description="Text question (if not using audio)")
    voice: str = Field(default="alloy", description="Voice for TTS response")
    language: str = Field(default="en", description="Language for audio transcription")
    
    @field_validator('voice')
    @classmethod
    def validate_voice(cls, v: str) -> str:
        """Validate voice parameter against valid options."""
        from app.services.voice_service import VALID_VOICES
        if v not in VALID_VOICES:
            raise ValueError(f"Invalid voice. Must be one of: {', '.join(VALID_VOICES)}")
        return v


class VoiceChatResponse(BaseModel):
    """Schema for voice chat response."""
    answer: str = Field(..., description="Text answer from agent")
    audio_base64: Optional[str] = Field(None, description="Base64 encoded audio of the answer")
    sources: List[dict] = Field(..., description="Source chunks used for the answer")
    timestamp: str = Field(..., description="ISO timestamp of response")
