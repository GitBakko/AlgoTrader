"""
JWT token generation and validation.
Uses HS256 algorithm with configurable expiration.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from loguru import logger

from src.utils.config import get_settings


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data to encode (typically {"sub": user_id})
        expires_delta: Token expiration time (defaults to config value)

    Returns:
        Encoded JWT token string

    Raises:
        ValueError: If data is empty or invalid
    """
    if not data:
        raise ValueError("Token data cannot be empty")

    settings = get_settings()
    to_encode = data.copy()

    # Set expiration
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})

    # Encode token
    try:
        encoded_jwt = jwt.encode(
            to_encode, settings.secret_key, algorithm=settings.jwt_algorithm
        )
        return encoded_jwt
    except Exception as e:
        logger.error(f"Failed to create access token: {e}")
        raise ValueError(f"Token creation failed: {e}")


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.

    Args:
        token: JWT token string to decode

    Returns:
        Decoded token payload

    Raises:
        jwt.ExpiredSignatureError: If token has expired
        jwt.InvalidTokenError: If token is invalid
        ValueError: If token is empty
    """
    if not token or not token.strip():
        raise ValueError("Token cannot be empty")

    settings = get_settings()

    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Expired JWT token")
        raise
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise


def get_token_user_id(token: str) -> int:
    """
    Extract user ID from JWT token.

    Args:
        token: JWT token string

    Returns:
        User ID from token subject

    Raises:
        jwt.InvalidTokenError: If token is invalid or missing 'sub' claim
    """
    payload = decode_access_token(token)

    user_id = payload.get("sub")
    if user_id is None:
        raise jwt.InvalidTokenError("Token missing 'sub' claim")

    try:
        return int(user_id)
    except (ValueError, TypeError):
        raise jwt.InvalidTokenError(f"Invalid user ID in token: {user_id}")
