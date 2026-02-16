"""
Password hashing and verification using bcrypt.
Provides secure password storage with configurable rounds.
"""

import bcrypt


def hash_password(password: str, rounds: int = 12) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password
        rounds: Number of hashing rounds (default 12, range 4-31)

    Returns:
        Hashed password as string

    Raises:
        ValueError: If password is empty or rounds out of range
    """
    if not password or not password.strip():
        raise ValueError("Password cannot be empty")

    if not 4 <= rounds <= 31:
        raise ValueError("Rounds must be between 4 and 31")

    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=rounds)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise

    Raises:
        ValueError: If either password is empty
    """
    if not plain_password or not hashed_password:
        raise ValueError("Both passwords must be provided")

    try:
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except (ValueError, AttributeError):
        # Invalid hash format or encoding issue
        return False
