"""
Authentication schemas for API requests and responses.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Request schema for user login."""

    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    """Request schema for user registration."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role_name: str = Field(default="VIEWER", description="Role name (VIEWER, TRADER, ADMIN)")


class TokenResponse(BaseModel):
    """Response schema for authentication tokens."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class LoginResponse(BaseModel):
    """Response schema for login endpoint - includes token and user."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    refresh_token: str
    refresh_expires_in: int  # seconds
    user: 'UserResponse'  # Include user object for frontend


class RefreshRequest(BaseModel):
    """Request schema for token refresh."""

    refresh_token: str


class RefreshResponse(BaseModel):
    """Response schema for token refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    refresh_token: str
    refresh_expires_in: int  # seconds


class UserResponse(BaseModel):
    """Response schema for user information."""

    id: int
    username: str
    email: str
    role_id: int
    role_name: str
    is_active: bool
    last_login: datetime | None
    avatar_url: str | None = None
    permissions: list['PermissionResponse'] = []  # User's role permissions

    model_config = {"from_attributes": True}


class RoleResponse(BaseModel):
    """Response schema for role information."""

    id: int
    name: str
    description: str | None
    permissions: list[str] = []  # ["positions:read", "trading:execute", ...]

    model_config = {"from_attributes": True}


class PermissionResponse(BaseModel):
    """Response schema for permission information."""

    id: int
    resource: str
    action: str

    @property
    def permission_string(self) -> str:
        """Return permission as 'resource:action' string."""
        return f"{self.resource}:{self.action}"

    model_config = {"from_attributes": True}


# Rebuild models to resolve forward references (Pydantic v2 requirement)
UserResponse.model_rebuild()
LoginResponse.model_rebuild()
