"""
FastAPI dependencies for authentication and authorization.
Provides dependency injection for current user and permission checking.
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt import decode_access_token
from src.auth.models import User
from src.auth.rbac import RBACManager
from src.database.session import get_db_session

# HTTP Bearer token scheme for JWT
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """
    Get current authenticated user from JWT token.

    Args:
        credentials: HTTP Bearer credentials with JWT token
        session: Database session

    Returns:
        Current user

    Raises:
        HTTPException: 401 if token invalid or user not found
    """
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
        user_id: int = int(payload.get("sub"))
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Get current active user (convenience wrapper).

    Args:
        current_user: Current user from get_current_user

    Returns:
        Current active user
    """
    return current_user


def require_permission(resource: str, action: str):
    """
    Dependency factory to require specific permission for endpoint.

    Args:
        resource: Required resource (e.g., 'positions', 'trading')
        action: Required action (e.g., 'read', 'write', 'execute')

    Returns:
        Dependency function that checks permission

    Example:
        @router.post("/trading/start", dependencies=[Depends(require_permission("trading", "execute"))])
        async def start_trading():
            ...
    """

    async def permission_checker(
        current_user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> User:
        """Check if current user has required permission."""
        rbac = RBACManager(session)
        has_perm = await rbac.has_permission(current_user.id, resource, action)

        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {resource}:{action}",
            )

        return current_user

    return permission_checker


def require_role(role_name: str):
    """
    Dependency factory to require specific role for endpoint.

    Args:
        role_name: Required role name (e.g., 'ADMIN', 'TRADER')

    Returns:
        Dependency function that checks role

    Example:
        @router.delete("/users/{user_id}", dependencies=[Depends(require_role("ADMIN"))])
        async def delete_user(user_id: int):
            ...
    """

    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> User:
        """Check if current user has required role."""
        # Get user's role
        from src.auth.models import Role

        stmt = select(Role).where(Role.id == current_user.role_id)
        result = await session.execute(stmt)
        role = result.scalar_one_or_none()

        if not role or role.name != role_name.upper():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {role_name}",
            )

        return current_user

    return role_checker
