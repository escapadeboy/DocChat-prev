"""
Authentication router for user registration and login.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import get_db
from app.models import User
from app.schemas import (
    RegisterRequest,
    LoginRequest,
    UserInfo,
    LoginResponse
)
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    validate_phone_number
)

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

# Initialize limiter
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=UserInfo, status_code=status.HTTP_201_CREATED)
# @limiter.limit("3/minute")  # TEMPORARILY DISABLED - causing timeouts
async def register(
    request: Request,
    user_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new user.
    
    Args:
        user_data: User registration data (phone_number, password, name)
        db: Database session
        
    Returns:
        User information (id, phone_number, name)
        
    Raises:
        HTTPException: 400 if invalid input, 409 if phone number already exists
    """
    # Mask phone for logging (show only last 4 digits)
    masked_phone = f"****{user_data.phone_number[-4:]}" if len(user_data.phone_number) >= 4 else "****"
    logger.info(f"Registration attempt for phone: {masked_phone}")
    
    # Validate phone number format
    if not validate_phone_number(user_data.phone_number):
        logger.warning(f"Invalid phone number format during registration: {masked_phone}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format. Must be a 10-digit Indian number starting with 6-9"
        )
    
    # Check if user already exists
    existing_user = db.query(User).filter(User.phone_number == user_data.phone_number).first()
    if existing_user:
        logger.warning(f"Phone number already registered: {masked_phone}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already registered"
        )
    
    # Hash password and create user
    try:
        hashed_password = hash_password(user_data.password)
        new_user = User(
            phone_number=user_data.phone_number,
            name=user_data.name,
            hashed_password=hashed_password
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info(f"User registered successfully: {masked_phone}, user_id: {new_user.id}")
    except Exception as e:
        logger.error(f"Error during user registration: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user. Please try again."
        )
    
    return UserInfo(
        id=new_user.id,
        phone_number=new_user.phone_number,
        name=new_user.name
    )


@router.post("/login", response_model=LoginResponse)
# @limiter.limit("5/minute")  # TEMPORARILY DISABLED - causing timeouts
async def login(
    request: Request,
    user_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticate user and return JWT token.
    
    Args:
        user_data: User login credentials (phone_number, password)
        db: Database session
        
    Returns:
        Login response with access_token, token_type, and user information
        
    Raises:
        HTTPException: 401 if credentials are invalid
    """
    # Mask phone for logging (show only last 4 digits)
    masked_phone = f"****{user_data.phone_number[-4:]}" if len(user_data.phone_number) >= 4 else "****"
    logger.info(f"Login attempt for phone: {masked_phone}")
    
    # Validate phone number format before querying database
    if not validate_phone_number(user_data.phone_number):
        logger.warning(f"Invalid phone number format during login: {masked_phone}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password"
        )
    
    # Validate password is not empty
    if not user_data.password or len(user_data.password) < 1:
        logger.warning(f"Empty password provided during login: {masked_phone}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password"
        )
    
    # Find user by phone number
    user = db.query(User).filter(User.phone_number == user_data.phone_number).first()
    if not user:
        logger.warning(f"User not found during login: {masked_phone}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password"
        )
    
    logger.debug(f"User found: {masked_phone}, user_id: {user.id}, has hash: {bool(user.hashed_password)}, hash length: {len(user.hashed_password) if user.hashed_password else 0}")
    
    # Verify password
    password_valid = verify_password(user_data.password, user.hashed_password)
    if not password_valid:
        logger.warning(f"Password verification failed for user: {masked_phone}, user_id: {user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password"
        )
    
    logger.debug(f"Password verified successfully for user: {masked_phone}")
    
    # Check if user is active
    if not user.is_active:
        logger.warning(f"Inactive user attempted login: {masked_phone}, user_id: {user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive"
        )
    
    # Create access token with phone_number as subject
    try:
        access_token = create_access_token(data={"sub": user.phone_number})
        logger.info(f"Login successful for user: {masked_phone}, user_id: {user.id}")
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create authentication token"
        )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserInfo(
            id=user.id,
            phone_number=user.phone_number,
            name=user.name
        )
    )


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user information.
    
    Args:
        current_user: Current authenticated user (from JWT token)
        
    Returns:
        User information (id, phone_number, name)
        
    Raises:
        HTTPException: 401 if token is invalid (handled by get_current_user dependency)
    """
    return UserInfo(
        id=current_user.id,
        phone_number=current_user.phone_number,
        name=current_user.name
    )
