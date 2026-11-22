"""
Chat router for conversations with documents.
"""
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from openai import APIError as OpenAIAPIError
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import get_db
from app.models import User, ChatSession, ChatMessage, Agent, AgentDocument, Document, Chunk, Embedding
from app.schemas import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    AgentChatRequest,
    APIResponse
)
from app.auth import get_current_user
from app.services.chat_service import chat_with_agent, ChatServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Initialize limiter
limiter = Limiter(key_func=get_remote_address)


@router.post("/", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def chat_with_agent_endpoint(
    request: Request,
    chat_request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Chat with an agent using AI and document embeddings.
    
    Args:
        chat_request: Chat request with agent_id and message
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dict with answer, sources, and timestamp:
        {
            "answer": str,
            "sources": [{"chunk_id": int, "text": str, "similarity": float}],
            "timestamp": str (ISO format)
        }
        
    Raises:
        HTTPException: 
            - 404 if agent not found
            - 403 if user doesn't own agent
            - 400 if agent has no linked documents
            - 500 for OpenAI API errors
    """
    try:
        agent_id = chat_request.agent_id
        message = chat_request.message
        
        # Validate agent exists
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            logger.warning(f"Agent {agent_id} not found for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        
        # Verify user owns the agent
        if agent.user_id != current_user.id:
            logger.warning(f"User {current_user.id} attempted to access agent {agent_id} owned by user {agent.user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this agent"
            )
        
        # Check if agent has linked documents
        linked_docs = db.query(AgentDocument).filter(
            AgentDocument.agent_id == agent_id
        ).all()
        
        if not linked_docs:
            logger.warning(f"Agent {agent_id} has no linked documents")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent has no linked documents. Please link documents to the agent first."
            )
        
        # Verify that at least one linked document is processed and has chunks with embeddings
        linked_doc_ids = [doc.document_id for doc in linked_docs]
        processed_docs = db.query(Document).filter(
            Document.id.in_(linked_doc_ids),
            Document.is_processed == True
        ).all()
        
        if not processed_docs:
            logger.warning(f"Agent {agent_id} has linked documents but none are processed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent's linked documents are not processed yet. Please wait for document processing to complete."
            )
        
        # Check if processed documents have chunks with embeddings
        chunks_with_embeddings_count = db.query(Chunk).join(
            Embedding, Chunk.id == Embedding.chunk_id
        ).filter(
            Chunk.document_id.in_([doc.id for doc in processed_docs])
        ).count()
        
        if chunks_with_embeddings_count == 0:
            logger.warning(f"Agent {agent_id} has processed documents but no chunks with embeddings")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent's documents don't have any processed chunks. Please re-upload the documents."
            )
        
        # Call chat service
        logger.info(f"Processing chat request for agent {agent_id}, user {current_user.id}")
        result = chat_with_agent(
            agent_id=agent_id,
            question=message,
            user_id=current_user.id,
            db=db
        )
        
        logger.info(f"Successfully generated chat response for agent {agent_id}")
        return result
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
        
    except ValueError as e:
        # Handle value errors from chat_service (agent not found, ownership issues)
        error_message = str(e)
        if "not found" in error_message.lower():
            logger.warning(f"Agent not found: {error_message}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_message
            )
        elif "does not belong" in error_message.lower():
            logger.warning(f"Ownership violation: {error_message}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_message
            )
        else:
            logger.error(f"Value error in chat endpoint: {error_message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        
    except ChatServiceError as e:
        # Handle chat service errors (OpenAI API issues, no similar chunks, etc.)
        error_message = str(e)
        logger.error(f"Chat service error in chat endpoint: {error_message}")
        
        # Check if it's a "no similar chunks" error - should be 400 Bad Request
        if "No relevant content found" in error_message or "No similar chunks" in error_message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        else:
            # Other AI service errors are 500
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI service error: {error_message}"
            )
    except Exception as e:
        # Handle other unexpected exceptions
        error_message = str(e)
        logger.error(f"Unexpected error in chat endpoint: {error_message}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {error_message}"
        )


@router.post("/sessions", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    session_data: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new chat session.
    
    Args:
        session_data: Chat session creation data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        API response with chat session data
    """
    new_session = ChatSession(
        owner_id=current_user.id,
        document_id=session_data.document_id,
        title=session_data.title
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    return APIResponse(
        status="success",
        data={"session": ChatSessionResponse.model_validate(new_session).model_dump()}
    )


@router.get("/sessions", response_model=APIResponse)
async def list_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all chat sessions for the current user.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        API response with list of chat sessions
    """
    sessions = db.query(ChatSession).filter(ChatSession.owner_id == current_user.id).all()
    
    return APIResponse(
        status="success",
        data={"sessions": [ChatSessionResponse.model_validate(session).model_dump() for session in sessions]}
    )


@router.get("/sessions/{session_id}", response_model=APIResponse)
async def get_chat_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific chat session with messages.
    
    Args:
        session_id: The chat session ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        API response with chat session and messages
        
    Raises:
        HTTPException: If session not found or user doesn't have access
    """
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    if session.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this chat session"
        )
    
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    
    return APIResponse(
        status="success",
        data={
            "session": ChatSessionResponse.model_validate(session).model_dump(),
            "messages": [ChatMessageResponse.model_validate(msg).model_dump() for msg in messages]
        }
    )


@router.post("/sessions/{session_id}/messages", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_message(
    session_id: int,
    message_data: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new chat message.
    
    Args:
        session_id: The chat session ID
        message_data: Chat message creation data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        API response with chat message data
        
    Raises:
        HTTPException: If session not found or user doesn't have access
    """
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    if session.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this chat session"
        )
    
    new_message = ChatMessage(
        session_id=session_id,
        role=message_data.role,
        content=message_data.content
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    
    # Generate AI response if this is a user message
    assistant_message = None
    if message_data.role == "user" and session.document_id:
        try:
            # Find an agent owned by the user that has this document linked
            agent_with_doc = db.query(Agent).join(
                AgentDocument, Agent.id == AgentDocument.agent_id
            ).filter(
                Agent.user_id == current_user.id,
                AgentDocument.document_id == session.document_id
            ).first()
            
            if agent_with_doc:
                # Generate AI response using chat service
                logger.info(f"Generating AI response for session {session_id} using agent {agent_with_doc.id}")
                chat_result = chat_with_agent(
                    agent_id=agent_with_doc.id,
                    question=message_data.content,
                    user_id=current_user.id,
                    db=db
                )
                
                # Create assistant message with the generated answer
                assistant_message = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=chat_result["answer"]
                )
                db.add(assistant_message)
                db.commit()
                db.refresh(assistant_message)
                logger.info(f"Generated AI response for session {session_id}")
            else:
                logger.warning(f"No agent found for document {session.document_id} owned by user {current_user.id}")
        except Exception as e:
            # Log error but don't fail the request - user message is already saved
            logger.error(f"Error generating AI response for session {session_id}: {str(e)}", exc_info=True)
    
    # Return both messages if assistant response was generated
    response_data = {"message": ChatMessageResponse.model_validate(new_message).model_dump()}
    if assistant_message:
        response_data["assistant_message"] = ChatMessageResponse.model_validate(assistant_message).model_dump()
    
    return APIResponse(
        status="success",
        data=response_data
    )


@router.delete("/sessions/{session_id}", response_model=APIResponse)
async def delete_chat_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a chat session.
    
    Args:
        session_id: The chat session ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        API response with success message
        
    Raises:
        HTTPException: If session not found or user doesn't have access
    """
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    if session.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this chat session"
        )
    
    db.delete(session)
    db.commit()
    
    return APIResponse(
        status="success",
        data={"message": "Chat session deleted successfully"}
    )

