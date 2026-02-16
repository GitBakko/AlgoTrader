"""
Secrets manager for storing encrypted credentials in database.
Provides secure storage and retrieval of API keys and sensitive data.
"""

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.security.encryption import EncryptionService
from src.security.models import EncryptedSecret


class SecretManager:
    """
    Manager for encrypted secrets stored in database.
    Automatically encrypts on write and decrypts on read.
    """

    def __init__(self, session: AsyncSession, encryption_service: EncryptionService | None = None):
        """
        Initialize secret manager.

        Args:
            session: Async database session
            encryption_service: Encryption service (creates new if None)
        """
        self.session = session
        self.encryption_service = encryption_service or EncryptionService()

    async def set_secret(
        self,
        key_name: str,
        value: str,
        description: str | None = None,
        created_by: int | None = None,
    ) -> EncryptedSecret:
        """
        Store or update an encrypted secret.

        Args:
            key_name: Unique identifier for the secret
            value: Plaintext value to encrypt and store
            description: Optional description
            created_by: User ID who created the secret

        Returns:
            Created or updated EncryptedSecret record

        Raises:
            ValueError: If key_name or value is empty
        """
        if not key_name or not key_name.strip():
            raise ValueError("Key name cannot be empty")

        if not value:
            raise ValueError("Secret value cannot be empty")

        # Encrypt the value
        encrypted_value = self.encryption_service.encrypt(value)

        # Check if secret already exists
        stmt = select(EncryptedSecret).where(EncryptedSecret.key_name == key_name)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing secret
            existing.encrypted_value = encrypted_value
            existing.description = description
            secret = existing
            logger.info(f"Updated encrypted secret: {key_name}")
        else:
            # Create new secret
            secret = EncryptedSecret(
                key_name=key_name,
                encrypted_value=encrypted_value,
                description=description,
                created_by=created_by,
            )
            self.session.add(secret)
            logger.info(f"Created encrypted secret: {key_name}")

        await self.session.commit()
        await self.session.refresh(secret)

        return secret

    async def get_secret(self, key_name: str) -> str | None:
        """
        Retrieve and decrypt a secret.

        Args:
            key_name: Secret identifier

        Returns:
            Decrypted secret value or None if not found

        Raises:
            ValueError: If decryption fails
        """
        stmt = select(EncryptedSecret).where(EncryptedSecret.key_name == key_name)
        result = await self.session.execute(stmt)
        secret = result.scalar_one_or_none()

        if not secret:
            logger.warning(f"Secret not found: {key_name}")
            return None

        try:
            decrypted = self.encryption_service.decrypt(secret.encrypted_value)
            logger.debug(f"Retrieved secret: {key_name}")
            return decrypted
        except Exception as e:
            logger.error(f"Failed to decrypt secret {key_name}: {e}")
            raise ValueError(f"Decryption failed for {key_name}: {e}")

    async def delete_secret(self, key_name: str) -> bool:
        """
        Delete a secret from storage.

        Args:
            key_name: Secret identifier

        Returns:
            True if deleted, False if not found
        """
        stmt = select(EncryptedSecret).where(EncryptedSecret.key_name == key_name)
        result = await self.session.execute(stmt)
        secret = result.scalar_one_or_none()

        if not secret:
            logger.warning(f"Secret not found for deletion: {key_name}")
            return False

        await self.session.delete(secret)
        await self.session.commit()
        logger.info(f"Deleted secret: {key_name}")
        return True

    async def list_secrets(self) -> list[dict[str, Any]]:
        """
        List all stored secrets (without values).

        Returns:
            List of secret metadata (id, key_name, description, created_by, created_at)
        """
        stmt = select(EncryptedSecret)
        result = await self.session.execute(stmt)
        secrets = result.scalars().all()

        return [
            {
                "id": secret.id,
                "key_name": secret.key_name,
                "description": secret.description,
                "created_by": secret.created_by,
                "created_at": secret.created_at.isoformat() if secret.created_at else None,
            }
            for secret in secrets
        ]

    async def secret_exists(self, key_name: str) -> bool:
        """
        Check if a secret exists.

        Args:
            key_name: Secret identifier

        Returns:
            True if secret exists, False otherwise
        """
        stmt = select(EncryptedSecret).where(EncryptedSecret.key_name == key_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def rotate_secret(self, key_name: str, new_value: str) -> EncryptedSecret:
        """
        Rotate a secret by updating its value.

        Args:
            key_name: Secret identifier
            new_value: New plaintext value

        Returns:
            Updated secret

        Raises:
            ValueError: If secret not found
        """
        stmt = select(EncryptedSecret).where(EncryptedSecret.key_name == key_name)
        result = await self.session.execute(stmt)
        secret = result.scalar_one_or_none()

        if not secret:
            raise ValueError(f"Secret not found: {key_name}")

        # Encrypt new value
        encrypted_value = self.encryption_service.encrypt(new_value)
        secret.encrypted_value = encrypted_value

        await self.session.commit()
        await self.session.refresh(secret)

        logger.info(f"Rotated secret: {key_name}")
        return secret
