"""
Main FastAPI application entry point.
"""
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import time

from app.database import Base, engine, ensure_schema
from app.models import User, Document, Chunk, Embedding, Agent, AgentDocument  # Import to register models
from app.schemas import ErrorResponse
from app.routers import auth, documents, chat, agents, voice, support
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI application
app = FastAPI(
    title="DocChat API",
    description="Document chat application with AI-powered conversations",
    version="1.0.0"
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Logging middleware
class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log HTTP requests and responses."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log request
        logger.info(f"{request.method} {request.url.path}")
        
        # Process request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log response
        logger.info(
            f"{request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Time: {process_time:.3f}s"
        )
        
        return response


# Add middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    max_age=600,  # Cache preflight requests for 10 minutes
)


# Database setup on startup
@app.on_event("startup")
async def startup_event():
    """Create database tables on application startup."""
    logger.info("Creating database tables...")
    ensure_schema()
    logger.info("Database tables created successfully")


# Include routers
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(agents.router)
app.include_router(voice.router)
app.include_router(support.router)


# API root endpoint
@app.get("/api")
async def root():
    """
    API root endpoint.
    
    Returns:
        Welcome message
    """
    return {"message": "DocChat API v1"}


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Health status
    """
    return {"status": "ok"}


# Global error handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Global exception handler for HTTPException.
    
    Returns:
        Error response in standard format
    """
    logger.warning(f"HTTP {exc.status_code}: {exc.detail} - {request.method} {request.url.path}")
    error_response = ErrorResponse(
        detail=exc.detail,
        status_code=exc.status_code
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump()
    )


# Mount static files (frontend build) - MUST be after all API routes
frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    # Mount static assets (CSS, JS, etc.)
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    
    # Serve index.html for all other routes (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for all non-API routes."""
        # Exclude API routes - these should return 404 if not found by FastAPI
        # Check both with and without trailing slashes for API base paths
        if (full_path.startswith(("api/", "auth/", "documents/", "agents/", "voice/", "chat/", "chat", "support/")) or
            full_path in ("health", "api", "auth", "documents", "agents", "voice", "chat")):
            # Let FastAPI handle these as 404 if not found
            raise HTTPException(status_code=404, detail="Not Found")
        
        # Check if it's a static file request
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        
        # Otherwise return index.html for client-side routing (includes /chat, /dashboard, etc.)
        return FileResponse(frontend_dist / "index.html")
    
    logger.info(f"Serving frontend from {frontend_dist}")
else:
    logger.warning(f"Frontend dist directory not found at {frontend_dist}. Run 'npm run build' in frontend directory.")
