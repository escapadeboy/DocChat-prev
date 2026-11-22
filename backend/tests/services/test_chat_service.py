"""
Tests for chat service functions.
"""
import pytest
from unittest.mock import patch, Mock, MagicMock
import numpy as np

from app.services.chat_service import (
    cosine_similarity,
    embed_text,
    find_similar_chunks,
    generate_answer,
    chat_with_agent,
    ChatServiceError
)
from app.models import Agent, Chunk, Embedding, AgentDocument


@pytest.mark.chat
@pytest.mark.unit
def test_cosine_similarity_identical():
    """Test cosine similarity of identical vectors returns 1.0."""
    vec1 = [1.0, 2.0, 3.0, 4.0, 5.0]
    vec2 = [1.0, 2.0, 3.0, 4.0, 5.0]
    
    similarity = cosine_similarity(vec1, vec2)
    
    assert similarity == pytest.approx(1.0, abs=0.01)


@pytest.mark.chat
@pytest.mark.unit
def test_cosine_similarity_orthogonal():
    """Test cosine similarity of orthogonal vectors returns 0.0."""
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [0.0, 1.0, 0.0]
    
    similarity = cosine_similarity(vec1, vec2)
    
    assert similarity == pytest.approx(0.0, abs=0.01)


@pytest.mark.chat
@pytest.mark.unit
def test_cosine_similarity_opposite():
    """Test cosine similarity of opposite vectors returns 0.0 (clipped)."""
    vec1 = [1.0, 2.0, 3.0]
    vec2 = [-1.0, -2.0, -3.0]
    
    similarity = cosine_similarity(vec1, vec2)
    
    # Opposite vectors have similarity of -1, but we clip to [0, 1]
    assert similarity == pytest.approx(0.0, abs=0.01)


@pytest.mark.chat
@pytest.mark.unit
def test_cosine_similarity_dimension_mismatch():
    """Test that dimension mismatch raises ValueError."""
    vec1 = [1.0, 2.0, 3.0]
    vec2 = [1.0, 2.0]
    
    with pytest.raises(ValueError, match="dimensions must match"):
        cosine_similarity(vec1, vec2)


@pytest.mark.chat
@pytest.mark.unit
def test_embed_text_success():
    """Test successful text embedding with mocked OpenAI."""
    mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    
    # Mock the OpenAI response
    mock_response = Mock()
    mock_response.data = [Mock(embedding=mock_embedding)]
    
    with patch('app.services.chat_service.get_openai_client') as mock_client:
        mock_client.return_value.embeddings.create.return_value = mock_response
        
        result = embed_text("test text")
        
        assert result == mock_embedding
        mock_client.return_value.embeddings.create.assert_called_once()


@pytest.mark.chat
@pytest.mark.unit
def test_embed_text_empty_raises_error():
    """Test that embedding empty text raises ValueError."""
    with pytest.raises(ValueError, match="cannot be empty"):
        embed_text("")
    
    with pytest.raises(ValueError, match="cannot be empty"):
        embed_text("   ")


@pytest.mark.chat
@pytest.mark.unit
def test_embed_text_retry_on_rate_limit():
    """Test that embed_text retries on rate limit errors."""
    from openai import RateLimitError
    
    mock_embedding = [0.1, 0.2, 0.3]
    mock_response = Mock()
    mock_response.data = [Mock(embedding=mock_embedding)]
    
    with patch('app.services.chat_service.get_openai_client') as mock_client:
        # First call raises RateLimitError, second succeeds
        mock_client.return_value.embeddings.create.side_effect = [
            RateLimitError("Rate limit exceeded", response=Mock(status_code=429), body=None),
            mock_response
        ]
        
        with patch('app.services.chat_service.time.sleep'):  # Skip actual sleep
            result = embed_text("test text")
        
        assert result == mock_embedding
        assert mock_client.return_value.embeddings.create.call_count == 2


@pytest.mark.chat
@pytest.mark.integration
def test_find_similar_chunks(db_session, test_agent, test_document_with_chunks):
    """Test finding similar chunks for an agent's documents."""
    # Query embedding (similar to chunk1's embedding [0.1, 0.2, 0.3, 0.4, 0.5])
    query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    
    result = find_similar_chunks(
        question_embedding=query_embedding,
        agent_id=test_agent.id,
        db=db_session,
        top_k=2
    )
    
    assert len(result) <= 2
    assert all("chunk_id" in chunk for chunk in result)
    assert all("text" in chunk for chunk in result)
    assert all("similarity" in chunk for chunk in result)
    
    # Check that similarities are sorted (descending)
    if len(result) > 1:
        assert result[0]["similarity"] >= result[1]["similarity"]


@pytest.mark.chat
@pytest.mark.integration
def test_find_similar_chunks_no_documents(db_session, test_user):
    """Test finding chunks when agent has no linked documents."""
    # Create agent without documents
    agent = Agent(
        user_id=test_user.id,
        name="Empty Agent",
        ai_model="gpt-4"
    )
    db_session.add(agent)
    db_session.commit()
    
    query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    
    result = find_similar_chunks(
        question_embedding=query_embedding,
        agent_id=agent.id,
        db=db_session,
        top_k=3
    )
    
    assert result == []


@pytest.mark.chat
@pytest.mark.unit
def test_generate_answer():
    """Test answer generation with mocked OpenAI."""
    mock_answer = "This is a test answer from the AI."
    
    # Mock OpenAI chat completion response
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = mock_answer
    
    # Create mock agent
    agent = Mock()
    agent.id = 1
    agent.ai_model = "gpt-4"
    agent.system_prompt = "You are helpful."
    
    with patch('app.services.chat_service.get_openai_client') as mock_client:
        mock_client.return_value.chat.completions.create.return_value = mock_response
        
        result = generate_answer(
            question="What is this?",
            context="Some context text",
            agent=agent
        )
        
        assert result == mock_answer
        mock_client.return_value.chat.completions.create.assert_called_once()


@pytest.mark.chat
@pytest.mark.unit
def test_generate_answer_empty_question():
    """Test that empty question raises ValueError."""
    agent = Mock()
    
    with pytest.raises(ValueError, match="cannot be empty"):
        generate_answer("", "context", agent)


@pytest.mark.chat
@pytest.mark.integration
def test_chat_with_agent_success(db_session, test_agent, test_document_with_chunks):
    """Test full chat flow with agent."""
    mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    mock_answer = "This is the AI's answer."
    
    # Mock OpenAI embedding
    mock_embed_response = Mock()
    mock_embed_response.data = [Mock(embedding=mock_embedding)]
    
    # Mock OpenAI chat completion
    mock_chat_response = Mock()
    mock_chat_response.choices = [Mock()]
    mock_chat_response.choices[0].message = Mock()
    mock_chat_response.choices[0].message.content = mock_answer
    
    with patch('app.services.chat_service.get_openai_client') as mock_client:
        mock_client.return_value.embeddings.create.return_value = mock_embed_response
        mock_client.return_value.chat.completions.create.return_value = mock_chat_response
        
        result = chat_with_agent(
            agent_id=test_agent.id,
            question="What is this about?",
            user_id=test_agent.user_id,
            db=db_session
        )
        
        assert "answer" in result
        assert "sources" in result
        assert "timestamp" in result
        assert result["answer"] == mock_answer
        assert len(result["sources"]) > 0


@pytest.mark.chat
@pytest.mark.integration
def test_chat_with_agent_not_found(db_session, test_user):
    """Test chat with non-existent agent raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        chat_with_agent(
            agent_id=99999,
            question="Test question",
            user_id=test_user.id,
            db=db_session
        )


@pytest.mark.chat
@pytest.mark.integration
def test_chat_with_agent_wrong_owner(db_session, test_agent, second_test_user):
    """Test chat with agent owned by different user raises ValueError."""
    with pytest.raises(ValueError, match="does not belong"):
        chat_with_agent(
            agent_id=test_agent.id,
            question="Test question",
            user_id=second_test_user.id,
            db=db_session
        )


@pytest.mark.chat
@pytest.mark.integration
def test_chat_with_agent_no_similar_chunks(db_session, test_agent):
    """Test chat when no similar chunks found raises ChatServiceError."""
    mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    
    mock_embed_response = Mock()
    mock_embed_response.data = [Mock(embedding=mock_embedding)]
    
    with patch('app.services.chat_service.get_openai_client') as mock_client:
        mock_client.return_value.embeddings.create.return_value = mock_embed_response
        
        # Mock find_similar_chunks to return empty list
        with patch('app.services.chat_service.find_similar_chunks') as mock_find:
            mock_find.return_value = []
            
            with pytest.raises(ChatServiceError, match="No relevant content"):
                chat_with_agent(
                    agent_id=test_agent.id,
                    question="Test question",
                    user_id=test_agent.user_id,
                    db=db_session
                )


@pytest.mark.chat
@pytest.mark.unit
def test_cosine_similarity_normalized_vectors():
    """Test cosine similarity with pre-normalized vectors."""
    # Unit vectors
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [0.707, 0.707, 0.0]  # 45 degrees from vec1
    
    similarity = cosine_similarity(vec1, vec2)
    
    assert similarity == pytest.approx(0.707, abs=0.01)


@pytest.mark.chat
@pytest.mark.unit
def test_generate_answer_with_default_system_prompt():
    """Test answer generation when agent has no custom system prompt."""
    mock_answer = "Default prompt answer."
    
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = mock_answer
    
    agent = Mock()
    agent.id = 1
    agent.ai_model = "gpt-3.5-turbo"
    agent.system_prompt = None  # No custom prompt
    
    with patch('app.services.chat_service.get_openai_client') as mock_client:
        mock_client.return_value.chat.completions.create.return_value = mock_response
        
        result = generate_answer("Question?", "Context", agent)
        
        assert result == mock_answer
        # Verify default system prompt was used
        call_args = mock_client.return_value.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        assert messages[0]['role'] == 'system'
        assert 'helpful assistant' in messages[0]['content'].lower()

