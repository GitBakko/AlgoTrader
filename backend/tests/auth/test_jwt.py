"""Tests for JWT token generation and validation."""

from datetime import timedelta

import jwt
import pytest

from src.auth.jwt import create_access_token, decode_access_token, get_token_user_id


class TestJWTTokens:
    """Test JWT token functionality."""

    def test_create_access_token_success(self):
        """Test successful token creation."""
        data = {"sub": "123"}
        token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token can be decoded
        payload = decode_access_token(token)
        assert payload["sub"] == "123"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_token_with_custom_expiration(self):
        """Test token creation with custom expiration."""
        data = {"sub": "123"}
        expires_delta = timedelta(minutes=5)
        token = create_access_token(data, expires_delta)

        payload = decode_access_token(token)
        assert payload["sub"] == "123"

    def test_create_token_empty_data_raises_error(self):
        """Test that empty data raises ValueError."""
        with pytest.raises(ValueError, match="Token data cannot be empty"):
            create_access_token({})

    def test_decode_access_token_success(self):
        """Test successful token decoding."""
        data = {"sub": "456", "role": "admin"}
        token = create_access_token(data)

        payload = decode_access_token(token)
        assert payload["sub"] == "456"
        assert payload["role"] == "admin"

    def test_decode_invalid_token_raises_error(self):
        """Test that invalid token raises error."""
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token("invalid.token.here")

    def test_decode_empty_token_raises_error(self):
        """Test that empty token raises ValueError."""
        with pytest.raises(ValueError, match="Token cannot be empty"):
            decode_access_token("")

        with pytest.raises(ValueError, match="Token cannot be empty"):
            decode_access_token("   ")

    def test_decode_expired_token_raises_error(self):
        """Test that expired token raises ExpiredSignatureError."""
        data = {"sub": "123"}
        # Create token that expires immediately
        expires_delta = timedelta(seconds=-1)
        token = create_access_token(data, expires_delta)

        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_get_token_user_id_success(self):
        """Test extracting user ID from token."""
        token = create_access_token({"sub": "789"})
        user_id = get_token_user_id(token)

        assert user_id == 789
        assert isinstance(user_id, int)

    def test_get_token_user_id_missing_sub_raises_error(self):
        """Test that token missing 'sub' claim raises error."""
        # Create token without 'sub' claim (need to use jwt.encode directly)
        from src.utils.config import get_settings

        settings = get_settings()
        token = jwt.encode({"user": "123"}, settings.secret_key, algorithm=settings.jwt_algorithm)

        with pytest.raises(jwt.InvalidTokenError, match="Token missing 'sub' claim"):
            get_token_user_id(token)

    def test_get_token_user_id_invalid_sub_raises_error(self):
        """Test that token with non-numeric 'sub' raises error."""
        token = create_access_token({"sub": "not_a_number"})

        with pytest.raises(jwt.InvalidTokenError, match="Invalid user ID in token"):
            get_token_user_id(token)

    def test_token_contains_issued_at_time(self):
        """Test that token contains 'iat' (issued at) claim."""
        token = create_access_token({"sub": "123"})
        payload = decode_access_token(token)

        assert "iat" in payload
        assert isinstance(payload["iat"], int)

    def test_token_with_additional_claims(self):
        """Test token creation with additional custom claims."""
        data = {
            "sub": "999",
            "username": "testuser",
            "role": "trader",
            "permissions": ["read", "write"],
        }
        token = create_access_token(data)

        payload = decode_access_token(token)
        assert payload["sub"] == "999"
        assert payload["username"] == "testuser"
        assert payload["role"] == "trader"
        assert payload["permissions"] == ["read", "write"]
