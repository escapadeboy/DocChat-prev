"""
Tests for authentication endpoints.
"""
import pytest
from fastapi import status


@pytest.mark.auth
def test_register_success(client):
    """Test successful user registration with valid data."""
    response = client.post("/auth/register", json={
        "phone_number": "9123456789",
        "password": "SecurePass123!",
        "name": "New User"
    })
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["phone_number"] == "9123456789"
    assert data["name"] == "New User"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.auth
def test_register_duplicate_phone(client, test_user):
    """Test registration with duplicate phone number returns 409."""
    response = client.post("/auth/register", json={
        "phone_number": test_user.phone_number,
        "password": "SecurePass123!",
        "name": "Duplicate User"
    })
    
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.auth
def test_register_invalid_phone(client):
    """Test registration with invalid phone number format."""
    # Phone number too short
    response = client.post("/auth/register", json={
        "phone_number": "12345",
        "password": "SecurePass123!",
        "name": "Invalid User"
    })
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Phone number starting with invalid digit
    response = client.post("/auth/register", json={
        "phone_number": "5123456789",
        "password": "SecurePass123!",
        "name": "Invalid User"
    })
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.auth
def test_register_weak_password(client):
    """Test registration with weak passwords that don't meet requirements."""
    # Too short (< 12 characters)
    response = client.post("/auth/register", json={
        "phone_number": "9123456789",
        "password": "Short1!",
        "name": "Test User"
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # No uppercase letter
    response = client.post("/auth/register", json={
        "phone_number": "9123456789",
        "password": "alllowercase123!",
        "name": "Test User"
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # No lowercase letter
    response = client.post("/auth/register", json={
        "phone_number": "9123456789",
        "password": "ALLUPPERCASE123!",
        "name": "Test User"
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # No digit
    response = client.post("/auth/register", json={
        "phone_number": "9123456789",
        "password": "NoDigitsHere!",
        "name": "Test User"
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # No special character
    response = client.post("/auth/register", json={
        "phone_number": "9123456789",
        "password": "NoSpecials123",
        "name": "Test User"
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.auth
def test_login_success(client, test_user):
    """Test successful login with valid credentials."""
    response = client.post("/auth/login", json={
        "phone_number": test_user.phone_number,
        "password": "TestPass123!"
    })
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data
    assert data["user"]["id"] == test_user.id
    assert data["user"]["phone_number"] == test_user.phone_number
    assert data["user"]["name"] == test_user.name


@pytest.mark.auth
def test_login_invalid_credentials(client, test_user):
    """Test login with wrong password returns 401."""
    response = client.post("/auth/login", json={
        "phone_number": test_user.phone_number,
        "password": "WrongPassword123!"
    })
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.auth
def test_login_nonexistent_user(client):
    """Test login with non-existent user returns 401."""
    response = client.post("/auth/login", json={
        "phone_number": "9999999999",
        "password": "TestPass123!"
    })
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.auth
def test_get_current_user(authenticated_client, test_user):
    """Test getting current user info with valid token."""
    response = authenticated_client.get("/auth/me")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == test_user.id
    assert data["phone_number"] == test_user.phone_number
    assert data["name"] == test_user.name


@pytest.mark.auth
def test_get_current_user_invalid_token(client):
    """Test getting current user with invalid token returns 401."""
    # No token
    response = client.get("/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    # Invalid token
    client.headers.update({"Authorization": "Bearer invalid_token_here"})
    response = client.get("/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    # Malformed token
    client.headers.update({"Authorization": "InvalidFormat"})
    response = client.get("/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.auth
def test_register_strips_whitespace(client):
    """Test that registration strips whitespace from name."""
    response = client.post("/auth/register", json={
        "phone_number": "9123456789",
        "password": "SecurePass123!",
        "name": "  Whitespace User  "
    })
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "Whitespace User"


@pytest.mark.auth
def test_register_normalizes_phone_number(client):
    """Test that registration normalizes phone number format."""
    response = client.post("/auth/register", json={
        "phone_number": "91-234-56789",
        "password": "SecurePass123!",
        "name": "Test User"
    })
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    # Phone number should be cleaned (dashes removed)
    assert data["phone_number"] == "9123456789"

