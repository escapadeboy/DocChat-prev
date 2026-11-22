"""
Tests for document endpoints.
"""
import pytest
import io
from fastapi import status
from unittest.mock import patch, Mock


@pytest.mark.documents
def test_upload_document_success(authenticated_client, test_user, sample_pdf_bytes):
    """Test successful document upload."""
    # Mock the document processing to avoid actual OpenAI calls
    with patch('app.routers.documents.process_document') as mock_process:
        mock_process.return_value = None
        
        files = {
            'file': ('test.pdf', io.BytesIO(sample_pdf_bytes), 'application/pdf')
        }
        response = authenticated_client.post("/documents/upload", files=files)
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["original_name"] == "test.pdf"
        assert data["file_size"] == len(sample_pdf_bytes)
        assert "id" in data
        assert "upload_date" in data
        # Check that processing was called
        assert mock_process.called


@pytest.mark.documents
def test_upload_invalid_file_type(authenticated_client):
    """Test upload with non-PDF file returns 400."""
    # Upload a text file instead of PDF
    files = {
        'file': ('document.txt', io.BytesIO(b'This is a text file'), 'text/plain')
    }
    response = authenticated_client.post("/documents/upload", files=files)
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "pdf" in response.json()["detail"].lower()


@pytest.mark.documents
def test_upload_file_too_large(authenticated_client):
    """Test upload with file larger than 10MB returns 413."""
    # Create a file larger than 10MB
    large_file = b'x' * (11 * 1024 * 1024)  # 11MB
    
    files = {
        'file': ('large.pdf', io.BytesIO(large_file), 'application/pdf')
    }
    response = authenticated_client.post("/documents/upload", files=files)
    
    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert "10mb" in response.json()["detail"].lower()


@pytest.mark.documents
def test_upload_malicious_filename(authenticated_client, sample_pdf_bytes):
    """Test that malicious filenames are sanitized."""
    with patch('app.routers.documents.process_document') as mock_process:
        mock_process.return_value = None
        
        # Try path traversal attack
        files = {
            'file': ('../../../etc/passwd.pdf', io.BytesIO(sample_pdf_bytes), 'application/pdf')
        }
        response = authenticated_client.post("/documents/upload", files=files)
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        # Filename should be sanitized (path separators removed)
        assert "../" not in data["original_name"]
        assert data["original_name"] == "etcpasswd.pdf"


@pytest.mark.documents
def test_list_documents(authenticated_client, test_document):
    """Test listing user's documents."""
    response = authenticated_client.get("/documents/")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "documents" in data
    assert len(data["documents"]) == 1
    assert data["documents"][0]["id"] == test_document.id
    assert data["documents"][0]["original_name"] == test_document.original_name


@pytest.mark.documents
def test_list_documents_empty(authenticated_client):
    """Test listing documents when user has none."""
    response = authenticated_client.get("/documents/")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "documents" in data
    assert len(data["documents"]) == 0


@pytest.mark.documents
def test_get_document_details(authenticated_client, test_document_with_chunks):
    """Test getting specific document details."""
    response = authenticated_client.get(f"/documents/{test_document_with_chunks.id}")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == test_document_with_chunks.id
    assert data["original_name"] == test_document_with_chunks.original_name
    assert "chunk_count" in data
    assert data["chunk_count"] == 2  # We created 2 chunks in fixture


@pytest.mark.documents
def test_get_document_not_found(authenticated_client):
    """Test getting non-existent document returns 404."""
    response = authenticated_client.get("/documents/999")
    
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.documents
def test_delete_document(authenticated_client, test_document, db_session):
    """Test deleting owned document."""
    document_id = test_document.id
    
    response = authenticated_client.delete(f"/documents/{document_id}")
    
    assert response.status_code == status.HTTP_200_OK
    assert "deleted" in response.json()["message"].lower()
    
    # Verify document is actually deleted
    from app.models import Document
    deleted_doc = db_session.query(Document).filter(Document.id == document_id).first()
    assert deleted_doc is None


@pytest.mark.documents
def test_delete_document_not_owner(authenticated_client, db_session, second_test_user):
    """Test that user cannot delete another user's document."""
    # Create document owned by second user
    from app.models import Document
    other_document = Document(
        user_id=second_test_user.id,
        original_name="other_user_doc.pdf",
        file_path="uploads/2/other_user_doc.pdf",
        file_size=1024,
        is_processed=True
    )
    db_session.add(other_document)
    db_session.commit()
    db_session.refresh(other_document)
    
    # Try to delete it with first user's token
    response = authenticated_client.delete(f"/documents/{other_document.id}")
    
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "access" in response.json()["detail"].lower()


@pytest.mark.documents
def test_upload_without_authentication(client, sample_pdf_bytes):
    """Test that upload requires authentication."""
    files = {
        'file': ('test.pdf', io.BytesIO(sample_pdf_bytes), 'application/pdf')
    }
    response = client.post("/documents/upload", files=files)
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.documents
def test_list_documents_isolation(authenticated_client, db_session, test_user, second_test_user):
    """Test that users only see their own documents."""
    # Create documents for both users
    from app.models import Document
    
    user1_doc = Document(
        user_id=test_user.id,
        original_name="user1_doc.pdf",
        file_path="uploads/1/user1_doc.pdf",
        file_size=1024,
        is_processed=True
    )
    user2_doc = Document(
        user_id=second_test_user.id,
        original_name="user2_doc.pdf",
        file_path="uploads/2/user2_doc.pdf",
        file_size=2048,
        is_processed=True
    )
    
    db_session.add(user1_doc)
    db_session.add(user2_doc)
    db_session.commit()
    
    # List documents (authenticated as test_user)
    response = authenticated_client.get("/documents/")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Should only see user1's document
    assert len(data["documents"]) == 1
    assert data["documents"][0]["original_name"] == "user1_doc.pdf"


@pytest.mark.documents
@pytest.mark.slow
def test_upload_processing_failure(authenticated_client, sample_pdf_bytes):
    """Test handling of document processing failure."""
    # Mock processing to raise an exception
    with patch('app.routers.documents.process_document') as mock_process:
        mock_process.side_effect = Exception("Processing failed")
        
        files = {
            'file': ('test.pdf', io.BytesIO(sample_pdf_bytes), 'application/pdf')
        }
        response = authenticated_client.post("/documents/upload", files=files)
        
        # Should return 500 with error message
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "processing failed" in response.json()["detail"].lower()

