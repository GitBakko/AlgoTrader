"""Tests for password hashing and verification."""

import pytest

from src.auth.password import hash_password, verify_password


class TestPasswordHashing:
    """Test password hashing functionality."""

    def test_hash_password_creates_different_hash_each_time(self):
        """Test that same password produces different hashes (due to salt)."""
        password = "testpassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        assert len(hash1) == 60  # bcrypt hash length
        assert len(hash2) == 60

    def test_verify_password_success(self):
        """Test successful password verification."""
        password = "correct_password_123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_failure(self):
        """Test password verification with wrong password."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_hash_empty_password_raises_error(self):
        """Test that empty password raises ValueError."""
        with pytest.raises(ValueError, match="Password cannot be empty"):
            hash_password("")

        with pytest.raises(ValueError, match="Password cannot be empty"):
            hash_password("   ")

    def test_verify_empty_password_raises_error(self):
        """Test that empty passwords raise ValueError."""
        with pytest.raises(ValueError, match="Both passwords must be provided"):
            verify_password("", "somehash")

        with pytest.raises(ValueError, match="Both passwords must be provided"):
            verify_password("password", "")

    def test_hash_with_custom_rounds(self):
        """Test password hashing with custom rounds."""
        password = "testpassword"
        hash1 = hash_password(password, rounds=4)  # Min rounds
        hash2 = hash_password(password, rounds=12)  # Default rounds

        assert len(hash1) == 60
        assert len(hash2) == 60
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_hash_invalid_rounds_raises_error(self):
        """Test that invalid rounds raise ValueError."""
        with pytest.raises(ValueError, match="Rounds must be between 4 and 31"):
            hash_password("password", rounds=3)

        with pytest.raises(ValueError, match="Rounds must be between 4 and 31"):
            hash_password("password", rounds=32)

    def test_verify_with_invalid_hash_returns_false(self):
        """Test that verification with invalid hash returns False."""
        assert verify_password("password", "not_a_valid_hash") is False
        assert verify_password("password", "invalid$hash$format") is False

    def test_password_with_special_characters(self):
        """Test password hashing and verification with special characters."""
        password = "p@ssw0rd!#$%^&*()_+{}[]|:;<>?,./"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True
        assert verify_password("different", hashed) is False

    def test_password_with_unicode_characters(self):
        """Test password hashing with Unicode characters."""
        password = "pássword_中文_🔐"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True
