"""
Authentication utilities for password hashing, JWT tokens, and user authentication.
"""
import re
import logging
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User

# Set up logging
logger = logging.getLogger(__name__)

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: The plain text password to hash
        
    Returns:
        The hashed password as a string
    """
    if not password:
        raise ValueError("Password cannot be empty")
    
    try:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        result = hashed.decode('utf-8')
        logger.debug(f"Password hashed successfully, length: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}")
        raise ValueError(f"Failed to hash password: {str(e)}")


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plain password against a hashed password.
    
    Args:
        plain: The plain text password
        hashed: The hashed password to verify against
        
    Returns:
        True if password matches, False otherwise
    """
    if not plain:
        logger.warning("Empty password provided for verification")
        return False
    
    if not hashed:
        logger.error("Empty hashed password provided for verification")
        return False
    
    try:
        # Validate that hashed password looks like a bcrypt hash
        if not hashed.startswith('$2') or len(hashed) < 50:
            logger.error(f"Invalid bcrypt hash format. Hash length: {len(hashed)}, starts with: {hashed[:10] if len(hashed) >= 10 else hashed}")
            return False
        
        result = bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
        logger.debug(f"Password verification result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}", exc_info=True)
        return False


def create_access_token(data: dict) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: The data to encode in the token (should contain 'sub' key with phone_number)
        
    Returns:
        The encoded JWT token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def verify_access_token(token: str) -> dict:
    """
    Verify and decode a JWT access token.
    
    Args:
        token: The JWT token to verify
        
    Returns:
        The decoded token payload as a dictionary
        
    Raises:
        JWTError: If token is invalid or expired
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    return payload


def validate_phone_number(phone: str) -> bool:
    """
    Validate a 10-digit Indian phone number.
    
    Args:
        phone: The phone number string to validate
        
    Returns:
        True if valid 10-digit Indian number, False otherwise
    """
    # Remove any whitespace or dashes
    phone = phone.strip().replace("-", "").replace(" ", "")
    
    # Check if it's exactly 10 digits
    pattern = r'^[6-9]\d{9}$'
    return bool(re.match(pattern, phone))


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from the JWT token.
    
    Args:
        token: The JWT token from the Authorization header
        db: Database session
        
    Returns:
        The authenticated User object
        
    Raises:
        HTTPException: 401 if token is invalid, expired, or user not found
    """
    # Verify token and extract payload
    try:
        payload = verify_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract phone number from token (stored in 'sub' field)
    phone_number: Optional[str] = payload.get("sub")
    if phone_number is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing phone number",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Find user by phone number
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user
