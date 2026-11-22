"""
Agent service for agent management, document linking, and context generation.
"""
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import Agent, AgentDocument, Document, Chunk

logger = logging.getLogger(__name__)

MAX_CONTEXT_LENGTH = 8000  # Maximum context length in characters


def create_agent(
    name: str,
    ai_model: str,
    user_id: int,
    system_prompt: Optional[str] = None,
    db: Session = None
) -> Agent:
    """
    Create an agent record.
    
    Args:
        name: Agent name
        ai_model: AI model to use ("gpt-4" or "gpt-3.5-turbo")
        user_id: User ID who owns the agent
        system_prompt: Optional system prompt for the agent
        db: Database session
        
    Returns:
        Created Agent object
        
    Raises:
        ValueError: If ai_model is invalid
    """
    # Validate AI model
    if ai_model not in ["gpt-4", "gpt-3.5-turbo"]:
        raise ValueError(f"Invalid AI model: {ai_model}. Must be 'gpt-4' or 'gpt-3.5-turbo'")
    
    # Create agent
    agent = Agent(
        name=name,
        ai_model=ai_model,
        user_id=user_id,
        system_prompt=system_prompt
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    logger.info(f"Created agent {agent.id} ({name}) for user {user_id}")
    return agent


def link_documents_to_agent(
    agent_id: int,
    document_ids: List[int],
    user_id: int,
    db: Session
) -> Agent:
    """
    Link documents to an agent (replace mode).
    
    Args:
        agent_id: Agent ID
        document_ids: List of document IDs to link
        user_id: User ID (to validate ownership)
        db: Database session
        
    Returns:
        Updated Agent object
        
    Raises:
        ValueError: If agent not found or documents don't belong to user
    """
    # Get agent and validate ownership
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise ValueError(f"Agent with ID {agent_id} not found")
    
    if agent.user_id != user_id:
        raise ValueError(f"Agent {agent_id} does not belong to user {user_id}")
    
    # Validate all documents exist and belong to user
    if document_ids:
        documents = db.query(Document).filter(
            and_(
                Document.id.in_(document_ids),
                Document.user_id == user_id
            )
        ).all()
        
        if len(documents) != len(document_ids):
            found_ids = {doc.id for doc in documents}
            missing_ids = set(document_ids) - found_ids
            raise ValueError(
                f"Some documents not found or don't belong to user: {missing_ids}"
            )
    
    # Clear previous relationships (replace mode)
    db.query(AgentDocument).filter(AgentDocument.agent_id == agent_id).delete()
    
    # Create new relationships
    if document_ids:
        for doc_id in document_ids:
            agent_doc = AgentDocument(
                agent_id=agent_id,
                document_id=doc_id
            )
            db.add(agent_doc)
    
    db.commit()
    db.refresh(agent)
    
    logger.info(f"Linked {len(document_ids)} documents to agent {agent_id}")
    return agent


def get_agent_context(agent_id: int, db: Session) -> str:
    """
    Get agent context from all linked document chunks.
    
    Args:
        agent_id: Agent ID
        db: Database session
        
    Returns:
        Combined context string (max 8000 chars) or empty string if no chunks
    """
    # Get agent's linked documents
    linked_doc_ids = db.query(AgentDocument.document_id).filter(
        AgentDocument.agent_id == agent_id
    ).all()
    
    if not linked_doc_ids:
        logger.info(f"No documents linked to agent {agent_id}")
        return ""
    
    doc_ids = [doc_id[0] for doc_id in linked_doc_ids]
    
    # Get all chunks for linked documents
    chunks = db.query(Chunk).filter(
        Chunk.document_id.in_(doc_ids)
    ).order_by(Chunk.document_id, Chunk.chunk_index).all()
    
    if not chunks:
        logger.info(f"No chunks found for agent {agent_id} documents")
        return ""
    
    # Combine chunks into context string
    context_parts = []
    current_length = 0
    
    for chunk in chunks:
        chunk_text = chunk.text
        chunk_length = len(chunk_text)
        
        # If adding this chunk would exceed limit, stop
        if current_length + chunk_length > MAX_CONTEXT_LENGTH:
            # Try to fit at least part of the chunk if we have space
            remaining_space = MAX_CONTEXT_LENGTH - current_length
            if remaining_space > 100:  # Only add partial if there's meaningful space
                # Add partial chunk (truncate at word boundary)
                truncated = chunk_text[:remaining_space]
                last_space = truncated.rfind(' ')
                if last_space > 0:
                    truncated = truncated[:last_space]
                context_parts.append(truncated)
            break
        
        context_parts.append(chunk_text)
        current_length += chunk_length
    
    context = "\n\n".join(context_parts)
    
    logger.info(f"Generated context for agent {agent_id}: {len(context)} chars from {len(context_parts)} chunks")
    return context


def get_agent_with_docs(agent_id: int, db: Session) -> Optional[Dict[str, Any]]:
    """
    Get agent with linked document IDs and chunk count.
    
    Args:
        agent_id: Agent ID
        db: Database session
        
    Returns:
        Dict with agent info, document_ids, and chunk_count, or None if not found
    """
    # Get agent
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        return None
    
    # Get linked document IDs
    linked_docs = db.query(AgentDocument.document_id).filter(
        AgentDocument.agent_id == agent_id
    ).all()
    document_ids = [doc_id[0] for doc_id in linked_docs]
    
    # Count chunks for linked documents
    chunk_count = 0
    if document_ids:
        chunk_count = db.query(Chunk).filter(
            Chunk.document_id.in_(document_ids)
        ).count()
    
    return {
        "agent": agent,
        "document_ids": document_ids,
        "chunk_count": chunk_count
    }

