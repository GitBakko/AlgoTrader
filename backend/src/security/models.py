"""
Security database models for encrypted secrets.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column, ForeignKey, text
from sqlmodel import Field, SQLModel


class EncryptedSecret(SQLModel, table=True):
    """
    Encrypted secrets stored in database.
    Values are encrypted with Fernet before storage.
    """

    __tablename__ = "encrypted_secrets"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    key_name: str = Field(max_length=100, nullable=False, unique=True, index=True)
    encrypted_value: str = Field(nullable=False)  # Base64-encoded Fernet ciphertext
    description: Optional[str] = Field(default=None, max_length=255)
    created_by: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )
