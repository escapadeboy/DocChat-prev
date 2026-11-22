"""
Pytest configuration and shared fixtures for DocChat backend tests.
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.models import User, Document, Agent, Chunk, Embedding
from app.auth import hash_password, create_access_token


# Set test environment variables
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-min-32-chars"
os.environ["OPENAI_API_KEY"] = "sk-test-key-for-testing"
os.environ["ENVIRONMENT"] = "testing"


@pytest.fixture(scope="function")
def test_db_engine():
    """
    Create a fresh in-memory SQLite database for each test.
    Uses function scope so each test gets a clean database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection, so TestClient's request thread sees the same in-memory DB
        echo=False
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    yield engine
    
    # Drop all tables after test
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(test_db_engine):
    """
    Create a new database session for each test.
    Automatically rolls back changes after test completes.
    """
    # Create session factory
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_db_engine
    )
    
    session = TestingSessionLocal()
    
    yield session
    
    # Cleanup
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """
    Create a TestClient with database session override.
    This allows API tests to use the test database.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session):
    """
    Create a test user in the database.
    Password: TestPass123!
    """
    user = User(
        phone_number="9876543210",
        name="Test User",
        hashed_password=hash_password("TestPass123!")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def second_test_user(db_session):
    """
    Create a second test user for testing authorization.
    Password: TestPass123!
    """
    user = User(
        phone_number="9876543211",
        name="Second Test User",
        hashed_password=hash_password("TestPass123!")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user):
    """
    Generate a valid JWT token for the test user.
    """
    token = create_access_token(data={"sub": test_user.phone_number})
    return token


@pytest.fixture
def auth_headers(auth_token):
    """
    Create authorization headers with valid JWT token.
    """
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def authenticated_client(client, auth_headers):
    """
    TestClient with authentication headers pre-configured.
    """
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def test_document(db_session, test_user):
    """
    Create a test document in the database.
    """
    document = Document(
        user_id=test_user.id,
        original_name="test_document.pdf",
        file_path="uploads/1/test_document.pdf",
        file_size=1024,
        is_processed=True
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


@pytest.fixture
def test_document_with_chunks(db_session, test_document):
    """
    Create a test document with chunks and embeddings.
    """
    # Create chunks
    chunk1 = Chunk(
        document_id=test_document.id,
        text="This is the first chunk of test content.",
        chunk_index=0
    )
    chunk2 = Chunk(
        document_id=test_document.id,
        text="This is the second chunk of test content.",
        chunk_index=1
    )
    
    db_session.add(chunk1)
    db_session.add(chunk2)
    db_session.flush()
    
    # Create embeddings (simple vectors for testing)
    embedding1 = Embedding(
        chunk_id=chunk1.id,
        vector=[0.1, 0.2, 0.3, 0.4, 0.5]
    )
    embedding2 = Embedding(
        chunk_id=chunk2.id,
        vector=[0.5, 0.4, 0.3, 0.2, 0.1]
    )
    
    db_session.add(embedding1)
    db_session.add(embedding2)
    db_session.commit()
    
    return test_document


@pytest.fixture
def test_agent(db_session, test_user, test_document):
    """
    Create a test agent linked to a document.
    """
    agent = Agent(
        user_id=test_user.id,
        name="Test Agent",
        ai_model="gpt-4",
        system_prompt="You are a helpful assistant."
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    
    # Link document to agent
    from app.models import AgentDocument
    agent_doc = AgentDocument(
        agent_id=agent.id,
        document_id=test_document.id
    )
    db_session.add(agent_doc)
    db_session.commit()
    
    return agent


@pytest.fixture
def sample_pdf_bytes():
    """
    Return minimal valid PDF file bytes for testing uploads.
    This is a minimal PDF that can be parsed.
    """
    # Minimal PDF structure
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
410
%%EOF
"""
    return pdf_content


@pytest.fixture
def mock_openai_embedding():
    """
    Return a mock OpenAI embedding response.
    """
    return [0.1, 0.2, 0.3, 0.4, 0.5] * 307  # 1535 dimensions (close to real embedding size)


@pytest.fixture
def mock_openai_chat_response():
    """
    Return a mock OpenAI chat completion response.
    """
    return "This is a test response from the AI agent."

