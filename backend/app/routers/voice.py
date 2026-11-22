"""
Voice router for audio transcription, text-to-speech, and voice chat.
"""
import logging
import base64
import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request, Form, Response
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models import User
from app.auth import get_current_user
from app.schemas import TranscribeResponse, TextToSpeechRequest, VoiceChatResponse
from app.services.voice_service import (
    transcribe_audio, 
    text_to_speech, 
    validate_audio_file,
    VoiceServiceError,
    AudioValidationError,
    TranscriptionError,
    TTSError,
    VoiceRateLimitError,
    VALID_VOICES,
    VALID_AUDIO_FORMATS
)
from app.services.chat_service import chat_with_agent, ChatServiceError
from app.config import settings
from app.support.engine import create_support_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

# Initialize limiter
limiter = Limiter(key_func=get_remote_address)


@router.post("/transcribe", response_model=TranscribeResponse, status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def transcribe_audio_endpoint(
    request: Request,
    file: UploadFile = File(..., description="Audio file (mp3, wav, webm, m4a)"),
    language: str = "en",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Transcribe audio to text using OpenAI Whisper API.
    
    Accepts audio files in the following formats: mp3, wav, webm, m4a.
    Maximum file size: 25MB.
    
    Args:
        file: Audio file to transcribe
        language: Language code for transcription (default: "en")
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        TranscribeResponse with transcribed text and language
        
    Raises:
        HTTPException:
            - 400: Invalid file format or size
            - 500: Transcription service error
    """
    try:
        # Validate file extension
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filename provided"
            )
        
        file_ext = file.filename.lower().split('.')[-1]
        if file_ext not in VALID_AUDIO_FORMATS:
            logger.warning(f"Invalid audio format: {file_ext}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported audio format. Supported: {', '.join(VALID_AUDIO_FORMATS)}"
            )
        
        # Read file bytes
        try:
            file_bytes = await file.read()
        except Exception as e:
            logger.error(f"Error reading audio file: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error reading file: {str(e)}"
            )
        
        logger.info(f"User {current_user.id} transcribing audio: {file.filename} ({len(file_bytes)} bytes)")
        
        # Transcribe audio (validation happens inside transcribe_audio)
        transcribed_text = transcribe_audio(file_bytes, language)
        
        logger.info(f"Transcription successful for user {current_user.id}: {len(transcribed_text)} characters")
        
        return TranscribeResponse(
            text=transcribed_text,
            language=language
        )
    
    except AudioValidationError as e:
        logger.warning(f"Audio validation failed for user {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    except VoiceRateLimitError as e:
        logger.warning(f"Rate limit hit for user {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    
    except TranscriptionError as e:
        logger.error(f"Transcription error for user {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    except HTTPException:
        raise
        
    except VoiceServiceError as e:
        # Handle voice service errors
        error_message = str(e)
        logger.error(f"Voice service error in transcribe endpoint: {error_message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {error_message}"
        )
        
    except Exception as e:
        # Handle unexpected errors
        error_message = str(e)
        logger.error(f"Unexpected error in transcribe endpoint: {error_message}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {error_message}"
        )


@router.post("/speak", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def text_to_speech_endpoint(
    request: Request,
    tts_request: TextToSpeechRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Convert text to speech using OpenAI TTS API.
    
    Generates audio from text using one of six available voices.
    Returns audio in MP3 format.
    
    Args:
        tts_request: Text-to-speech request with text and voice
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Audio file (audio/mpeg)
        
    Raises:
        HTTPException:
            - 400: Text too long or invalid voice
            - 500: TTS service error
    """
    try:
        text = tts_request.text
        voice = tts_request.voice
        
        logger.info(f"User {current_user.id} generating speech: {len(text)} chars, voice={voice}")
        
        # Generate speech
        audio_bytes = text_to_speech(text, voice)
        
        logger.info(f"TTS successful for user {current_user.id}: {len(audio_bytes)} bytes")
        
        # Return audio as response
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "attachment; filename=speech.mp3",
                "Content-Length": str(len(audio_bytes))
            }
        )
    
    except TTSError as e:
        # Handle TTS-specific errors (validation, generation failures)
        logger.warning(f"TTS error for user {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    except VoiceRateLimitError as e:
        logger.warning(f"Rate limit hit for user {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    
    except HTTPException:
        raise
        
    except VoiceServiceError as e:
        # Handle voice service errors
        error_message = str(e)
        logger.error(f"Voice service error in TTS endpoint: {error_message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Text-to-speech failed: {error_message}"
        )
        
    except Exception as e:
        # Handle unexpected errors
        error_message = str(e)
        logger.error(f"Unexpected error in TTS endpoint: {error_message}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {error_message}"
        )


@router.post("/chat-speak", response_model=VoiceChatResponse, status_code=status.HTTP_200_OK)
@limiter.limit("15/minute")
async def voice_chat_endpoint(
    request: Request,
    agent_id: int = Form(..., description="Agent ID to chat with"),
    voice: str = Form(default="alloy", description="Voice for TTS response"),
    language: str = Form(default="en", description="Language for audio transcription"),
    audio: Optional[UploadFile] = File(None, description="Audio file with question"),
    text: Optional[str] = Form(None, description="Text question (alternative to audio)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Combined endpoint: transcribe audio (or use text) → chat with agent → TTS response.
    
    This endpoint allows voice-based chat with an agent. You can either:
    1. Upload an audio file with your question
    2. Provide text directly
    
    The agent will generate a response, which is returned both as text and audio.
    
    Args:
        agent_id: ID of the agent to chat with
        voice: Voice for TTS response (alloy, echo, fable, onyx, nova, shimmer)
        language: Language code for audio transcription
        audio: Optional audio file with question
        text: Optional text question
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        VoiceChatResponse with answer text, audio (base64), sources, and timestamp
        
    Raises:
        HTTPException:
            - 400: Missing input, both inputs provided, or invalid agent
            - 403: User doesn't own agent
            - 404: Agent not found
            - 500: Service errors
    """
    try:
        # Validate voice parameter
        if voice not in VALID_VOICES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid voice. Must be one of: {', '.join(VALID_VOICES)}"
            )
        
        # Validate input: either audio OR text, not both, not neither
        if audio is None and text is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'audio' or 'text' must be provided"
            )
        
        if audio is not None and text is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide either 'audio' or 'text', not both"
            )
        
        # Step 1: Get question text (from audio or direct text)
        question = None
        
        if audio is not None:
            # Transcribe audio to text
            logger.info(f"User {current_user.id} voice chat with agent {agent_id}: transcribing audio")
            
            # Validate audio file extension
            if not audio.filename:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No filename provided for audio"
                )
            
            file_ext = audio.filename.lower().split('.')[-1]
            if file_ext not in VALID_AUDIO_FORMATS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported audio format. Supported: {', '.join(VALID_AUDIO_FORMATS)}"
                )
            
            # Read and transcribe audio
            try:
                audio_bytes = await audio.read()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error reading audio file: {str(e)}"
                )
            
            question = transcribe_audio(audio_bytes, language)
            logger.info(f"Audio transcribed: {len(question)} characters")
        else:
            # Use text directly
            question = text
            logger.info(f"User {current_user.id} voice chat with agent {agent_id}: using text input")
        
        # Step 2: Chat with agent
        logger.info(f"Chatting with agent {agent_id}: {question[:50]}...")
        
        try:
            chat_result = chat_with_agent(
                agent_id=agent_id,
                question=question,
                user_id=current_user.id,
                db=db
            )
        except ValueError as e:
            # Handle agent not found or ownership errors
            error_message = str(e)
            if "not found" in error_message.lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_message
                )
            elif "does not belong" in error_message.lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=error_message
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message
                )
        except ChatServiceError as e:
            # Handle chat service errors
            error_message = str(e)
            if "No relevant content found" in error_message or "No similar chunks" in error_message:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Chat service error: {error_message}"
                )
        
        answer = chat_result["answer"]
        sources = chat_result["sources"]
        timestamp = chat_result["timestamp"]
        
        # Step 3: Generate TTS from answer
        logger.info(f"Generating TTS for answer: {len(answer)} characters, voice={voice}")
        audio_bytes = text_to_speech(answer, voice)
        
        # Encode audio as base64
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        logger.info(f"Voice chat successful for user {current_user.id}, agent {agent_id}")
        
        return VoiceChatResponse(
            answer=answer,
            audio_base64=audio_base64,
            sources=sources,
            timestamp=timestamp
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
        
    except VoiceServiceError as e:
        # Handle voice service errors
        error_message = str(e)
        logger.error(f"Voice service error in voice chat endpoint: {error_message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice processing failed: {error_message}"
        )
        
    except Exception as e:
        # Handle unexpected errors
        error_message = str(e)
        logger.error(f"Unexpected error in voice chat endpoint: {error_message}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {error_message}"
        )



@router.post("/livekit-token", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def livekit_token_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a LiveKit room token for a live voice call with the support agent.

    The token lets the browser join a fresh room and dispatches the "support-agent" worker
    into it. The participant metadata carries the user and session IDs so the agent can
    look up this customer's orders and log the conversation.

    Returns:
        server_url, token, room name and the support session_id

    Raises:
        HTTPException 503: LiveKit is not configured on the server
    """
    if not (settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LiveKit is not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET in backend/.env"
        )

    from livekit import api as livekit_api

    session = create_support_session(db, current_user.id, "voice")
    room_name = f"support-{current_user.id}-{uuid.uuid4().hex[:8]}"
    metadata = json.dumps({"user_id": current_user.id, "session_id": session.id, "name": current_user.name})

    token = (
        livekit_api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(f"user-{current_user.id}")
        .with_name(current_user.name)
        .with_metadata(metadata)
        .with_grants(livekit_api.VideoGrants(
            room_join=True, room=room_name, can_publish=True, can_subscribe=True, can_publish_data=True
        ))
        .with_room_config(livekit_api.RoomConfiguration(
            agents=[livekit_api.RoomAgentDispatch(agent_name=settings.LIVEKIT_AGENT_NAME, metadata=metadata)]
        ))
        .to_jwt()
    )

    logger.info(f"Issued LiveKit token for user {current_user.id}, room {room_name}, session {session.id}")
    return {"server_url": settings.LIVEKIT_URL, "token": token, "room": room_name, "session_id": session.id}
