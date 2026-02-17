"""Tests for authentication API router endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from starlette.requests import Request
from starlette.datastructures import State

from src.auth.models import Role, User
from src.auth.password import hash_password


def _mock_request():
    """Create a real starlette Request for slowapi rate limiter."""
    mock_app = MagicMock()
    mock_app.state = State()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/auth/test",
        "headers": [],
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 8000),
        "app": mock_app,
    }
    return Request(scope)


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
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestLoginEndpoint:
    """Test /api/auth/login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self, sample_user, sample_role):
        """Test successful login."""
        with patch("src.api.routers.auth.get_db_session") as mock_session, \
             patch("src.api.routers.auth.limiter") as mock_limiter:
            # Disable rate limiter for unit tests
            mock_limiter.limit.return_value = lambda f: f

            # Mock database query
            mock_db = AsyncMock()
            mock_result_user = MagicMock()
            mock_result_user.scalar_one_or_none.return_value = sample_user
            mock_result_role = MagicMock()
            mock_result_role.scalar_one_or_none.return_value = sample_role
            mock_result_perms = MagicMock()
            mock_result_perms.scalars.return_value.all.return_value = []
            mock_db.execute = AsyncMock(side_effect=[mock_result_user, mock_result_role, mock_result_perms])
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            from src.api.routers.auth import login
            from src.auth.schemas import LoginRequest

            body = LoginRequest(username="testuser", password="testpassword123")
            response = await login(_mock_request(), body, mock_db)

            assert "data" in response
            data = response["data"]
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            assert data["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_login_invalid_username(self):
        """Test login with invalid username."""
        with patch("src.api.routers.auth.get_db_session") as mock_session, \
             patch("src.api.routers.auth.limiter") as mock_limiter:
            mock_limiter.limit.return_value = lambda f: f

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value.__aenter__.return_value = mock_db

            from fastapi import HTTPException

            from src.api.routers.auth import login
            from src.auth.schemas import LoginRequest

            body = LoginRequest(username="nonexistent", password="password")

            with pytest.raises(HTTPException) as exc_info:
                await login(_mock_request(), body, mock_db)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Incorrect username or password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, sample_user):
        """Test login with invalid password."""
        with patch("src.api.routers.auth.get_db_session") as mock_session, \
             patch("src.api.routers.auth.limiter") as mock_limiter:
            mock_limiter.limit.return_value = lambda f: f

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value.__aenter__.return_value = mock_db

            from fastapi import HTTPException

            from src.api.routers.auth import login
            from src.auth.schemas import LoginRequest

            body = LoginRequest(username="testuser", password="wrongpassword")

            with pytest.raises(HTTPException) as exc_info:
                await login(_mock_request(), body, mock_db)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Incorrect username or password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, sample_user):
        """Test login with inactive user account."""
        sample_user.is_active = False

        with patch("src.api.routers.auth.get_db_session") as mock_session, \
             patch("src.api.routers.auth.limiter") as mock_limiter:
            mock_limiter.limit.return_value = lambda f: f

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value.__aenter__.return_value = mock_db

            from fastapi import HTTPException

            from src.api.routers.auth import login
            from src.auth.schemas import LoginRequest

            body = LoginRequest(username="testuser", password="testpassword123")

            with pytest.raises(HTTPException) as exc_info:
                await login(_mock_request(), body, mock_db)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "inactive" in exc_info.value.detail.lower()


class TestRegisterEndpoint:
    """Test /api/auth/register endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, sample_role):
        """Test successful user registration."""
        with patch("src.api.routers.auth.get_db_session") as mock_session, \
             patch("src.api.routers.auth.RBACManager") as mock_rbac, \
             patch("src.api.routers.auth.limiter") as mock_limiter:
            mock_limiter.limit.return_value = lambda f: f

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

            mock_rbac_instance = AsyncMock()
            mock_rbac_instance.get_role_by_name = AsyncMock(return_value=sample_role)
            mock_rbac.return_value = mock_rbac_instance

            from src.api.routers.auth import register
            from src.auth.schemas import RegisterRequest

            body = RegisterRequest(
                username="newuser",
                email="newuser@example.com",
                password="newpassword123",
                role_name="VIEWER",
            )

            response = await register(_mock_request(), body, mock_db)

            assert "data" in response
            data = response["data"]
            assert "user" in data
            user_data = data["user"]
            assert user_data["username"] == "newuser"
            assert user_data["email"] == "newuser@example.com"
            assert user_data["role_name"] == "VIEWER"
            assert user_data["is_active"] is True

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, sample_user):
        """Test registration with existing username."""
        with patch("src.api.routers.auth.get_db_session") as mock_session, \
             patch("src.api.routers.auth.limiter") as mock_limiter:
            mock_limiter.limit.return_value = lambda f: f

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value.__aenter__.return_value = mock_db

            from fastapi import HTTPException

            from src.api.routers.auth import register
            from src.auth.schemas import RegisterRequest

            body = RegisterRequest(
                username="testuser",  # Existing username
                email="different@example.com",
                password="password123",
            )

            with pytest.raises(HTTPException) as exc_info:
                await register(_mock_request(), body, mock_db)

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

            assert "data" in response
            data = response["data"]
            assert data["id"] == sample_user.id
            assert data["username"] == sample_user.username
            assert data["email"] == sample_user.email
            assert data["role_name"] == sample_role.name
