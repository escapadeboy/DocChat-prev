"""
Chat service for question embedding, similarity search, and AI answer generation.
"""
import logging
import time
from typing import List, Dict, Optional
from datetime import datetime
import numpy as np
from openai import OpenAI, RateLimitError, APIError
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.config import settings
from app.models import Agent, AgentDocument, Document, Chunk, Embedding
from app.services.document_service import get_openai_client


class ChatServiceError(Exception):
    """Custom exception for chat service errors."""
    pass

logger = logging.getLogger(__name__)

# Constants
EMBEDDING_MODEL = "text-embedding-ada-002"
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
MAX_CONTEXT_LENGTH = 8000  # Maximum context length in characters
DEFAULT_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided context.

FORMATTING RULES:
- Use **bold** for key terms and important information
- Use bullet points (-) for lists of items or features
- Use numbered lists (1., 2., 3.) for steps, sequences, or rankings
- Use ## for section headings when organizing complex information
- Break responses into clear, concise paragraphs
- Keep sentences clear and direct

CONTENT RULES:
- Only use information from the provided context
- If the context doesn't contain enough information, clearly state this
- Cite specific details from the context when relevant
- Be professional and helpful
- Focus on being clear and actionable

Your goal is to make information easy to understand and scan quickly."""


def embed_text(text: str) -> List[float]:
    """
    Generate embedding for a single text string using OpenAI.
    
    Args:
        text: The text string to embed
        
    Returns:
        Embedding vector as list of floats
        
    Raises:
        APIError: If OpenAI API calls fail after retries
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")
    
    retries = 0
    while retries < MAX_RETRIES:
        try:
            client = get_openai_client()
            if client is None:
                raise ChatServiceError("OpenAI client not initialized. Please configure OPENAI_API_KEY.")
            
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text
            )
            
            # Extract embedding from response
            embedding = response.data[0].embedding
            logger.info(f"Generated embedding for text (length: {len(text)} chars)")
            return embedding
            
        except RateLimitError as e:
            retries += 1
            if retries >= MAX_RETRIES:
                logger.error(f"Rate limit error after {MAX_RETRIES} retries")
                raise ChatServiceError(f"Rate limit exceeded: {str(e)}")
            
            wait_time = RETRY_DELAY * (2 ** (retries - 1))  # Exponential backoff
            logger.warning(f"Rate limit hit, retrying in {wait_time}s (attempt {retries}/{MAX_RETRIES})")
            time.sleep(wait_time)
            
        except APIError as e:
            retries += 1
            if retries >= MAX_RETRIES:
                logger.error(f"OpenAI API error after {MAX_RETRIES} retries: {str(e)}")
                raise ChatServiceError(f"Failed to generate embedding: {str(e)}")
            
            wait_time = RETRY_DELAY * (2 ** (retries - 1))  # Exponential backoff
            logger.warning(f"API error, retrying in {wait_time}s (attempt {retries}/{MAX_RETRIES})")
            time.sleep(wait_time)
        
        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {str(e)}")
            raise ChatServiceError(f"Unexpected error: {str(e)}")


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        vec1: First embedding vector
        vec2: Second embedding vector
        
    Returns:
        Similarity score between 0 and 1
    """
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimensions must match: {len(vec1)} vs {len(vec2)}")
    
    vec1_array = np.array(vec1)
    vec2_array = np.array(vec2)
    
    # Calculate cosine similarity
    dot_product = np.dot(vec1_array, vec2_array)
    norm1 = np.linalg.norm(vec1_array)
    norm2 = np.linalg.norm(vec2_array)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = dot_product / (norm1 * norm2)
    
    # Ensure result is between 0 and 1
    return float(np.clip(similarity, 0.0, 1.0))


def find_similar_chunks(
    question_embedding: List[float],
    agent_id: int,
    db: Session,
    top_k: int = 3
) -> List[Dict]:
    """
    Find the most similar chunks for an agent's linked documents.
    
    Args:
        question_embedding: Embedding vector of the question
        agent_id: Agent ID
        db: Database session
        top_k: Number of top chunks to return (default: 3)
        
    Returns:
        List of dicts with format: [{"chunk_id": int, "text": str, "similarity": float}]
        Returns empty list if agent has no documents or chunks
    """
    try:
        # Get agent's linked document IDs
        linked_doc_ids = db.query(AgentDocument.document_id).filter(
            AgentDocument.agent_id == agent_id
        ).all()
        
        if not linked_doc_ids:
            logger.info(f"Agent {agent_id} has no linked documents")
            return []
        
        doc_ids = [doc_id[0] for doc_id in linked_doc_ids]
        
        # Get all chunks with embeddings for linked documents
        # Use left outer join to ensure we only get chunks with embeddings
        chunks_with_embeddings = db.query(Chunk, Embedding).join(
            Embedding, Chunk.id == Embedding.chunk_id
        ).filter(
            Chunk.document_id.in_(doc_ids)
        ).all()
        
        logger.info(f"Found {len(chunks_with_embeddings)} chunks with embeddings for agent {agent_id} across {len(doc_ids)} documents")
        
        if not chunks_with_embeddings:
            logger.warning(f"No chunks with embeddings found for agent {agent_id}. Documents may not be processed.")
            # Check if documents exist but aren't processed
            linked_docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
            unprocessed_docs = [doc.id for doc in linked_docs if not doc.is_processed]
            if unprocessed_docs:
                logger.warning(f"Agent {agent_id} has {len(unprocessed_docs)} unprocessed documents: {unprocessed_docs}")
            return []
        
        # Calculate similarity for each chunk
        chunk_similarities = []
        for chunk, embedding in chunks_with_embeddings:
            try:
                # Validate embedding exists
                if not embedding or not embedding.vector:
                    logger.warning(f"Chunk {chunk.id} has no embedding vector")
                    continue
                
                # Get embedding vector and ensure it's a list of floats
                chunk_embedding = embedding.vector
                
                # Handle case where vector might be a JSON string (shouldn't happen with JSON column, but safety check)
                if isinstance(chunk_embedding, str):
                    import json
                    chunk_embedding = json.loads(chunk_embedding)
                
                # Validate it's a list of numbers
                if not isinstance(chunk_embedding, list):
                    logger.warning(f"Chunk {chunk.id} embedding vector is not a list: {type(chunk_embedding)}")
                    continue
                
                # Validate list contains floats
                if not all(isinstance(x, (int, float)) for x in chunk_embedding):
                    logger.warning(f"Chunk {chunk.id} embedding vector contains non-numeric values")
                    continue
                
                # Convert to list of floats
                chunk_embedding = [float(x) for x in chunk_embedding]
                
                # Validate dimensions match
                if len(chunk_embedding) != len(question_embedding):
                    logger.warning(f"Chunk {chunk.id} embedding dimension mismatch: {len(chunk_embedding)} vs {len(question_embedding)}")
                    continue
                
                similarity = cosine_similarity(question_embedding, chunk_embedding)
                
                chunk_similarities.append({
                    "chunk_id": chunk.id,
                    "text": chunk.text,
                    "similarity": similarity
                })
            except Exception as e:
                logger.warning(f"Error calculating similarity for chunk {chunk.id}: {str(e)}", exc_info=True)
                continue
        
        # Sort by similarity (descending) and return top K
        chunk_similarities.sort(key=lambda x: x["similarity"], reverse=True)
        top_chunks = chunk_similarities[:top_k]
        
        logger.info(f"Found {len(top_chunks)} similar chunks for agent {agent_id}")
        return top_chunks
        
    except Exception as e:
        logger.error(f"Error finding similar chunks for agent {agent_id}: {str(e)}")
        return []


def generate_answer(question: str, context: str, agent: Agent) -> str:
    """
    Generate AI answer using OpenAI chat completion.
    
    Args:
        question: The user's question
        context: The context string from similar chunks
        agent: The Agent object with AI model and system prompt
        
    Returns:
        Generated answer string
        
    Raises:
        APIError: If OpenAI API calls fail after retries
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty")
    
    # Use agent's system prompt if exists, else default
    system_prompt = agent.system_prompt if agent.system_prompt else DEFAULT_SYSTEM_PROMPT
    
    # Format user prompt with context and question
    user_prompt = f"Based on this context:\n\n{context}\n\nAnswer this question: {question}"
    
    # Prepare messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    retries = 0
    while retries < MAX_RETRIES:
        try:
            client = get_openai_client()
            if client is None:
                raise ChatServiceError("OpenAI client not initialized. Please configure OPENAI_API_KEY.")
            
            # Use agent's AI model
            response = client.chat.completions.create(
                model=agent.ai_model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            answer = response.choices[0].message.content.strip()
            logger.info(f"Generated answer for agent {agent.id} using {agent.ai_model}")
            return answer
            
        except RateLimitError as e:
            retries += 1
            if retries >= MAX_RETRIES:
                logger.error(f"Rate limit error after {MAX_RETRIES} retries")
                raise ChatServiceError(f"Rate limit exceeded: {str(e)}")
            
            wait_time = RETRY_DELAY * (2 ** (retries - 1))  # Exponential backoff
            logger.warning(f"Rate limit hit, retrying in {wait_time}s (attempt {retries}/{MAX_RETRIES})")
            time.sleep(wait_time)
            
        except APIError as e:
            retries += 1
            if retries >= MAX_RETRIES:
                logger.error(f"OpenAI API error after {MAX_RETRIES} retries: {str(e)}")
                raise ChatServiceError(f"Failed to generate answer: {str(e)}")
            
            wait_time = RETRY_DELAY * (2 ** (retries - 1))  # Exponential backoff
            logger.warning(f"API error, retrying in {wait_time}s (attempt {retries}/{MAX_RETRIES})")
            time.sleep(wait_time)
        
        except Exception as e:
            logger.error(f"Unexpected error generating answer: {str(e)}")
            raise ChatServiceError(f"Unexpected error: {str(e)}")


def chat_with_agent(
    agent_id: int,
    question: str,
    user_id: int,
    db: Session
) -> Dict:
    """
    Main orchestrator function for chat with agent.
    
    Args:
        agent_id: Agent ID
        question: User's question
        user_id: User ID (to verify ownership)
        db: Database session
        
    Returns:
        Dict with format: {"answer": str, "sources": List[Dict], "timestamp": str}
        sources format: [{"chunk_id": int, "text": str, "similarity": float}]
        
    Raises:
        ValueError: If agent not found or user doesn't own the agent
        ChatServiceError: If OpenAI API calls fail
    """
    try:
        # Get agent from database
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        
        if not agent:
            raise ValueError(f"Agent with ID {agent_id} not found")
        
        # Verify user owns the agent
        if agent.user_id != user_id:
            raise ValueError(f"Agent {agent_id} does not belong to user {user_id}")
        
        logger.info(f"Processing chat request for agent {agent_id}, question: {question[:50]}...")
        
        # Generate question embedding
        question_embedding = embed_text(question)
        
        # Find similar chunks
        similar_chunks = find_similar_chunks(question_embedding, agent_id, db, top_k=3)
        
        # Initialize context and sources to avoid scope issues
        context = ""
        sources = []
        
        if not similar_chunks:
            # If no similar chunks found, raise an error rather than generating without context
            logger.warning(f"No similar chunks found for agent {agent_id}")
            raise ChatServiceError(
                "No relevant content found in the documents for this question. "
                "Please ensure documents are processed and contain relevant information."
            )
        
        logger.info(f"Found {len(similar_chunks)} similar chunks for agent {agent_id}")
        # Combine chunk texts into context string (max 8000 chars)
        context_parts = []
        current_length = 0
        
        for chunk_info in similar_chunks:
            chunk_text = chunk_info["text"]
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
        
        # Prepare sources list
        sources = [
            {
                "chunk_id": chunk_info["chunk_id"],
                "text": chunk_info["text"][:500],  # Limit text length for response
                "similarity": chunk_info["similarity"]
            }
            for chunk_info in similar_chunks
        ]
        
        logger.info(f"Prepared context for agent {agent_id}: {len(context)} characters from {len(similar_chunks)} chunks")
        
        # Generate answer with context (context should always be present now since we check for similar_chunks)
        answer = generate_answer(question, context, agent)
        
        # Prepare response
        timestamp = datetime.utcnow().isoformat()
        
        result = {
            "answer": answer,
            "sources": sources,
            "timestamp": timestamp
        }
        
        logger.info(f"Successfully generated chat response for agent {agent_id}")
        return result
        
    except ValueError as e:
        logger.error(f"Value error in chat_with_agent: {str(e)}")
        raise
    except ChatServiceError as e:
        logger.error(f"Chat service error in chat_with_agent: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat_with_agent: {str(e)}")
        raise ValueError(f"Failed to process chat request: {str(e)}")

