"""
Authentication database models.
User, Role, and Permission tables for RBAC.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column, ForeignKey, Table, text
from sqlmodel import Field, Relationship, SQLModel

from src.database.models import metadata


# Association table for many-to-many relationship between roles and permissions
role_permissions = Table(
    "role_permissions",
    metadata,
    Column("role_id", BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        BigInteger,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Role(SQLModel, table=True):
    """
    User roles for RBAC.
    Each role has a set of permissions.
    """

    __tablename__ = "roles"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    name: str = Field(max_length=50, nullable=False, unique=True, index=True)
    description: Optional[str] = Field(default=None, max_length=255)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class Permission(SQLModel, table=True):
    """
    Individual permissions for resources and actions.
    Combined as 'resource:action' (e.g., 'positions:read', 'trading:execute').
    """

    __tablename__ = "permissions"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    resource: str = Field(max_length=100, nullable=False, index=True)
    action: str = Field(max_length=50, nullable=False, index=True)
    description: Optional[str] = Field(default=None, max_length=255)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )

    class Config:
        """SQLModel config."""

        # Unique constraint on (resource, action) pair
        table_args = ({"sqlite_autoincrement": True},)


class User(SQLModel, table=True):
    """
    Application users with authentication and authorization.
    Each user has one role that determines their permissions.
    """

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    username: str = Field(max_length=100, nullable=False, unique=True, index=True)
    email: str = Field(max_length=255, nullable=False, unique=True, index=True)
    hashed_password: str = Field(max_length=255, nullable=False)
    role_id: int = Field(sa_column=Column(BigInteger, ForeignKey("roles.id"), nullable=False))
    is_active: bool = Field(default=True, nullable=False)
    last_login: Optional[datetime] = None
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
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    avatar_storage_path: Optional[str] = Field(default=None, max_length=500)
