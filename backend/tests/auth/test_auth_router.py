"""Tests for authentication API router endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import status
from httpx import AsyncClient

from src.auth.models import Role, User
from src.auth.password import hash_password


@pytest.fixture
def sample_role():
    """Sample role for testing."""
    return Role(id=1, name="VIEWER", description="Read-only access")


@pytest.fixture
def sample_user(sample_role):
    """Sample user for testing."""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("testpassword123"),
        role_id=sample_role.id,
        is_active=True,
        last_login=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


class TestLoginEndpoint:
    """Test /api/auth/login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self, sample_user, sample_role):
        """Test successful login."""
        with patch("src.api.routers.auth.get_db_session") as mock_session:
            # Mock database query
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            # Make request (would need full FastAPI test setup)
            # This is simplified - full test would use TestClient
            from src.api.routers.auth import login
            from src.auth.schemas import LoginRequest

            request = LoginRequest(username="testuser", password="testpassword123")
            response = await login(request, mock_db)

            assert "access_token" in response.model_dump()
            assert response.token_type == "bearer"
            assert response.expires_in > 0

    @pytest.mark.asyncio
    async def test_login_invalid_username(self):
        """Test login with invalid username."""
        with patch("src.api.routers.auth.get_db_session") as mock_session:
            # Mock database query returning no user
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value.__aenter__.return_value = mock_db

            from fastapi import HTTPException

            from src.api.routers.auth import login
            from src.auth.schemas import LoginRequest

            request = LoginRequest(username="nonexistent", password="password")

            with pytest.raises(HTTPException) as exc_info:
                await login(request, mock_db)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Incorrect username or password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, sample_user):
        """Test login with invalid password."""
        with patch("src.api.routers.auth.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value.__aenter__.return_value = mock_db

            from fastapi import HTTPException

            from src.api.routers.auth import login
            from src.auth.schemas import LoginRequest

            request = LoginRequest(username="testuser", password="wrongpassword")

            with pytest.raises(HTTPException) as exc_info:
                await login(request, mock_db)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Incorrect username or password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, sample_user):
        """Test login with inactive user account."""
        sample_user.is_active = False

        with patch("src.api.routers.auth.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value.__aenter__.return_value = mock_db

            from fastapi import HTTPException

            from src.api.routers.auth import login
            from src.auth.schemas import LoginRequest

            request = LoginRequest(username="testuser", password="testpassword123")

            with pytest.raises(HTTPException) as exc_info:
                await login(request, mock_db)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "inactive" in exc_info.value.detail.lower()


class TestRegisterEndpoint:
    """Test /api/auth/register endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, sample_role):
        """Test successful user registration."""
        with patch("src.api.routers.auth.get_db_session") as mock_session, patch(
            "src.api.routers.auth.RBACManager"
        ) as mock_rbac:
            # Mock database queries
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None  # No existing user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()

            def refresh_side_effect(user):
                user.id = 2

            mock_db.refresh = AsyncMock(side_effect=refresh_side_effect)
            mock_session.return_value.__aenter__.return_value = mock_db

            # Mock RBAC manager
            mock_rbac_instance = AsyncMock()
            mock_rbac_instance.get_role_by_name = AsyncMock(return_value=sample_role)
            mock_rbac.return_value = mock_rbac_instance

            from src.api.routers.auth import register
            from src.auth.schemas import RegisterRequest

            request = RegisterRequest(
                username="newuser",
                email="newuser@example.com",
                password="newpassword123",
                role_name="VIEWER",
            )

            response = await register(request, mock_db)

            assert response.username == "newuser"
            assert response.email == "newuser@example.com"
            assert response.role_name == "VIEWER"
            assert response.is_active is True

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, sample_user):
        """Test registration with existing username."""
        with patch("src.api.routers.auth.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value.__aenter__.return_value = mock_db

            from fastapi import HTTPException

            from src.api.routers.auth import register
            from src.auth.schemas import RegisterRequest

            request = RegisterRequest(
                username="testuser",  # Existing username
                email="different@example.com",
                password="password123",
            )

            with pytest.raises(HTTPException) as exc_info:
                await register(request, mock_db)

            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
            assert "Username already registered" in exc_info.value.detail


class TestGetCurrentUserProfile:
    """Test /api/auth/me endpoint."""

    @pytest.mark.asyncio
    async def test_get_profile_success(self, sample_user, sample_role):
        """Test successful profile retrieval."""
        with patch("src.api.routers.auth.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_role
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value.__aenter__.return_value = mock_db

            from src.api.routers.auth import get_current_user_profile

            response = await get_current_user_profile(sample_user, mock_db)

            assert response.id == sample_user.id
            assert response.username == sample_user.username
            assert response.email == sample_user.email
            assert response.role_name == sample_role.name
