"""
Encryption service using Fernet (symmetric encryption).
Provides AES-128-CBC encryption with HMAC for data integrity.
"""

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from src.utils.config import get_settings


class EncryptionService:
    """
    Encryption service for sensitive data.
    Uses Fernet (AES-128-CBC + HMAC-SHA256) for symmetric encryption.
    """

    def __init__(self, encryption_key: str | None = None):
        """
        Initialize encryption service.

        Args:
            encryption_key: Base64-encoded Fernet key (32 bytes)
                           If None, loads from config (ENCRYPTION_KEY env var)

        Raises:
            ValueError: If encryption key is invalid
        """
        settings = get_settings()

        # Get encryption key from parameter or config
        if encryption_key is None:
            encryption_key = getattr(settings, "encryption_key", None)

        if not encryption_key:
            raise ValueError(
                "Encryption key not provided. Set ENCRYPTION_KEY environment variable or pass key parameter."
            )

        try:
            self.fernet = Fernet(
                encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
            )
        except Exception as e:
            raise ValueError(f"Invalid encryption key: {e}")

        logger.info("Encryption service initialized")

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key.

        Returns:
            Base64-encoded key (44 characters)

        Example:
            >>> key = EncryptionService.generate_key()
            >>> print(key)
            'pZ3...==' (44 chars)
        """
        return Fernet.generate_key().decode()

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext string.

        Args:
            plaintext: String to encrypt

        Returns:
            Base64-encoded encrypted string

        Raises:
            ValueError: If plaintext is empty
        """
        if not plaintext:
            raise ValueError("Plaintext cannot be empty")

        try:
            plaintext_bytes = plaintext.encode("utf-8")
            encrypted_bytes = self.fernet.encrypt(plaintext_bytes)
            return encrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError(f"Encryption failed: {e}")

    def decrypt(self, encrypted_text: str) -> str:
        """
        Decrypt encrypted string.

        Args:
            encrypted_text: Base64-encoded encrypted string

        Returns:
            Decrypted plaintext string

        Raises:
            ValueError: If decryption fails or token invalid
        """
        if not encrypted_text:
            raise ValueError("Encrypted text cannot be empty")

        try:
            encrypted_bytes = encrypted_text.encode()
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            logger.error("Decryption failed: Invalid token or wrong key")
            raise ValueError("Decryption failed: Invalid token or wrong encryption key")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Decryption failed: {e}")

    def encrypt_dict(self, data: dict) -> dict[str, str]:
        """
        Encrypt all values in a dictionary.

        Args:
            data: Dictionary with string keys and values

        Returns:
            Dictionary with encrypted values

        Example:
            >>> service = EncryptionService(key)
            >>> encrypted = service.encrypt_dict({"api_key": "secret123"})
            >>> print(encrypted)
            {'api_key': 'gAAAAA...'}
        """
        return {key: self.encrypt(str(value)) for key, value in data.items()}

    def decrypt_dict(self, encrypted_data: dict[str, str]) -> dict[str, str]:
        """
        Decrypt all values in a dictionary.

        Args:
            encrypted_data: Dictionary with encrypted values

        Returns:
            Dictionary with decrypted values
        """
        return {key: self.decrypt(value) for key, value in encrypted_data.items()}

    def is_encrypted(self, text: str) -> bool:
        """
        Check if text appears to be Fernet-encrypted.

        Args:
            text: Text to check

        Returns:
            True if text looks like Fernet ciphertext, False otherwise

        Note:
            This is a heuristic check based on format, not cryptographic verification.
        """
        if not text or len(text) < 20:
            return False

        # Fernet tokens start with "gAAAAA" (base64 of version byte + timestamp)
        try:
            return text.startswith("gAAAAA") or (
                len(text) > 60 and "=" in text[-5:]  # Base64 padding
            )
        except Exception:
            return False
