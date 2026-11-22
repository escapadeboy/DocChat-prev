"""
Document router for file upload and management.
"""
import os
import re
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models import User, Document, Chunk
from app.schemas import DocumentResponse, DocumentListResponse
from app.auth import get_current_user
from app.services.document_service import validate_file, process_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Initialize limiter
limiter = Limiter(key_func=get_remote_address)

# Upload directory (for MVP, can be in-memory or temp storage)
UPLOAD_DIR = "uploads"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other security issues.
    
    Args:
        filename: Original filename from upload
        
    Returns:
        Sanitized filename safe for filesystem storage
    """
    # Get the base filename (removes any path separators)
    filename = os.path.basename(filename)
    
    # Remove any remaining dangerous characters
    # Keep only alphanumeric, dots, hyphens, underscores, and spaces
    filename = re.sub(r'[^\w\s.-]', '', filename)
    
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', ' ', filename)
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    
    # Limit length to 255 characters (filesystem limit)
    if len(filename) > 255:
        # Preserve file extension
        name, ext = os.path.splitext(filename)
        max_name_length = 255 - len(ext)
        filename = name[:max_name_length] + ext
    
    # If filename is empty after sanitization, use a default
    if not filename:
        filename = "uploaded_file.pdf"
    
    return filename


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a PDF document.
    
    Args:
        file: The PDF file to upload
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        DocumentResponse with id, original_name, status information
        
    Raises:
        HTTPException: 400 if invalid file type, 413 if too large
    """
    # Validate file type first (before reading)
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed"
        )
    
    # Read file content
    try:
        file_bytes = await file.read()
        file_size = len(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error reading file: {str(e)}"
        )
    
    # Validate file using service (includes size check)
    # Create a file-like object for validation
    class FileWrapper:
        def __init__(self, filename, size):
            self.filename = filename
            self.size = size
    
    if not validate_file(FileWrapper(file.filename, file_size)):
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds maximum limit of 10MB"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file"
        )
    
    # Sanitize filename to prevent path traversal attacks
    safe_filename = sanitize_filename(file.filename)
    
    # Create file path (for MVP, using placeholder path)
    # In production, you would save the file to storage (S3, local filesystem, etc.)
    file_path = f"{UPLOAD_DIR}/{current_user.id}/{safe_filename}"
    
    # Create document record with sanitized filename
    new_document = Document(
        user_id=current_user.id,
        original_name=safe_filename,
        file_path=file_path,
        file_size=file_size,
        is_processed=False
    )
    db.add(new_document)
    db.commit()
    db.refresh(new_document)
    
    # Process document synchronously (extract text, chunk, generate embeddings)
    processing_error = None
    try:
        logger.info(f"Starting processing for document {new_document.id}: {new_document.original_name}")
        process_document(new_document.id, file_bytes, db)
        # Refresh to get updated is_processed status
        db.refresh(new_document)
        logger.info(f"Document {new_document.id} processed successfully: is_processed={new_document.is_processed}")
    except Exception as e:
        # Document is created but processing failed
        processing_error = str(e)
        logger.error(f"Failed to process document {new_document.id}: {processing_error}", exc_info=True)
        # In production, you might want to queue this for retry
        # For MVP, we'll leave is_processed=False
        # Raise the exception so the user knows what went wrong
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document uploaded but processing failed: {processing_error}"
        )
    
    return DocumentResponse(
        id=new_document.id,
        original_name=new_document.original_name,
        file_size=new_document.file_size,
        upload_date=new_document.upload_date,
        is_processed=new_document.is_processed
    )


@router.get("/", response_model=DocumentListResponse)
@router.get("", response_model=DocumentListResponse, include_in_schema=False)
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all documents for the current user.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        List of documents (DocumentListResponse)
    """
    documents = db.query(Document).filter(Document.user_id == current_user.id).all()
    
    document_responses = [
        DocumentResponse(
            id=doc.id,
            original_name=doc.original_name,
            file_size=doc.file_size,
            upload_date=doc.upload_date,
            is_processed=doc.is_processed
        )
        for doc in documents
    ]
    
    return DocumentListResponse(documents=document_responses)


@router.get("/{doc_id}", response_model=dict)
async def get_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific document by ID with chunk count.
    
    Args:
        doc_id: The document ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        DocumentResponse with chunk_count
        
    Raises:
        HTTPException: 404 if not found, 403 if not owner
    """
    document = db.query(Document).filter(Document.id == doc_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this document"
        )
    
    # Count chunks for this document
    chunk_count = db.query(func.count(Chunk.id)).filter(Chunk.document_id == doc_id).scalar() or 0
    
    return {
        "id": document.id,
        "original_name": document.original_name,
        "file_size": document.file_size,
        "upload_date": document.upload_date,
        "is_processed": document.is_processed,
        "chunk_count": chunk_count
    }


@router.delete("/{doc_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a document by ID (cascade deletes chunks and embeddings).
    
    Args:
        doc_id: The document ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: 404 if not found, 403 if not owner
    """
    document = db.query(Document).filter(Document.id == doc_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this document"
        )
    
    # Delete document (cascade will delete chunks and embeddings automatically)
    db.delete(document)
    db.commit()
    
    return {"message": "deleted"}
