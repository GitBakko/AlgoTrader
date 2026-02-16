"""
Authentication API router.
Handles user login, registration, and profile retrieval.
"""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import error_response, success_response
from src.auth.dependencies import get_current_user
from src.auth.jwt import create_access_token
from src.auth.models import Role, User
from src.auth.password import hash_password, verify_password
from src.auth.rbac import RBACManager
from src.auth.schemas import LoginRequest, LoginResponse, RegisterRequest, TokenResponse, UserResponse, PermissionResponse
from src.database.session import get_db_session
from src.utils.config import get_settings
from src.utils.avatar_handler import save_avatar, delete_avatar, get_avatar_file_path

router = APIRouter()


@router.post("/login")
async def login(
    request: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Authenticate user and return JWT token with user info.

    Args:
        request: Login credentials (username, password)
        session: Database session

    Returns:
        Access token with expiration time and user information

    Raises:
        HTTPException: 401 if credentials invalid
    """
    # Find user by username
    stmt = select(User).where(User.username == request.username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last login
    user.last_login = datetime.utcnow()
    await session.commit()

    # Get role name for response
    stmt_role = select(Role).where(Role.id == user.role_id)
    result_role = await session.execute(stmt_role)
    role = result_role.scalar_one_or_none()

    # Get role permissions
    from src.auth.models import role_permissions, Permission
    stmt_perms = (
        select(Permission)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .where(role_permissions.c.role_id == user.role_id)
    )
    result_perms = await session.execute(stmt_perms)
    permissions = result_perms.scalars().all()

    # Create access token
    settings = get_settings()
    token_data = {"sub": str(user.id)}
    access_token = create_access_token(token_data)

    logger.info(f"User {user.username} logged in successfully with {len(permissions)} permissions")

    return success_response(
        LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,  # Convert to seconds
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                role_id=user.role_id,
                role_name=role.name if role else "UNKNOWN",
                is_active=user.is_active,
                last_login=user.last_login,
                permissions=[
                    PermissionResponse(id=p.id, resource=p.resource, action=p.action)
                    for p in permissions
                ],
            ),
        ).model_dump()
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Register a new user.

    Args:
        request: Registration data (username, email, password, role)
        session: Database session

    Returns:
        Created user information

    Raises:
        HTTPException: 400 if username/email already exists or role invalid
    """
    # Check if username already exists
    stmt = select(User).where(User.username == request.username)
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Check if email already exists
    stmt = select(User).where(User.email == request.email)
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Get role
    rbac = RBACManager(session)
    role = await rbac.get_role_by_name(request.role_name)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {request.role_name}. Must be one of: VIEWER, TRADER, ADMIN",
        )

    # Create user
    hashed_pwd = hash_password(request.password)
    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hashed_pwd,
        role_id=role.id,
        is_active=True,
    )

    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info(f"New user registered: {user.username} with role {request.role_name}")

    # Get role name for response
    return success_response(
        {
            "user": UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                role_id=user.role_id,
                role_name=role.name,
                is_active=user.is_active,
                last_login=user.last_login,
            ).model_dump()
        }
    )


@router.get("/me")
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Get current authenticated user's profile.

    Args:
        current_user: Current user from JWT token
        session: Database session

    Returns:
        User profile information
    """
    # Get role name
    stmt = select(Role).where(Role.id == current_user.role_id)
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()

    return success_response(
        UserResponse(
            id=current_user.id,
            username=current_user.username,
            email=current_user.email,
            role_id=current_user.role_id,
            role_name=role.name if role else "UNKNOWN",
            is_active=current_user.is_active,
            last_login=current_user.last_login,
            avatar_url=current_user.avatar_url,
        ).model_dump()
    )


@router.get("/permissions")
async def get_user_permissions(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Get current user's permissions.

    Args:
        current_user: Current user from JWT token
        session: Database session

    Returns:
        List of user permissions
    """
    rbac = RBACManager(session)
    permissions = await rbac.get_user_permissions(current_user.id)

    return success_response({"permissions": permissions})


# ═════════════════════════════════════════════════════════════════════════════
# Avatar Management
# ═════════════════════════════════════════════════════════════════════════════


@router.post("/avatar/upload")
async def upload_avatar(
    file: Annotated[UploadFile, File(description="Avatar image file")],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Upload user avatar image.

    Accepts image files (JPG, PNG, GIF, WebP) up to 5MB.
    Automatically resizes to 256x256 and optimizes for storage.

    Args:
        file: Uploaded image file
        current_user: Current user from JWT token
        session: Database session

    Returns:
        Updated user profile with avatar URL
    """
    try:
        # Save avatar (this will also delete old avatar if exists)
        avatar_url, storage_path = await save_avatar(
            file, current_user.id, current_user.avatar_storage_path
        )

        # Update user record
        current_user.avatar_url = avatar_url
        current_user.avatar_storage_path = storage_path
        await session.commit()
        await session.refresh(current_user)

        logger.info(f"Avatar uploaded for user {current_user.id}")

        # Get role name for response
        stmt = select(Role).where(Role.id == current_user.role_id)
        result = await session.execute(stmt)
        role = result.scalar_one_or_none()

        return success_response(
            UserResponse(
                id=current_user.id,
                username=current_user.username,
                email=current_user.email,
                role_id=current_user.role_id,
                role_name=role.name if role else "UNKNOWN",
                is_active=current_user.is_active,
                last_login=current_user.last_login,
                avatar_url=current_user.avatar_url,
            ).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload avatar for user {current_user.id}: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore durante il caricamento dell'avatar",
        ) from e


@router.get("/avatar/{user_id}")
async def get_avatar(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Retrieve user avatar image.

    Returns the avatar image file with appropriate caching headers.

    Args:
        user_id: User ID
        session: Database session

    Returns:
        Avatar image file
    """
    # Get user
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.avatar_storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Avatar non trovato"
        )

    # Get file path
    file_path = get_avatar_file_path(user_id, user.avatar_storage_path)
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File avatar non trovato"
        )

    # Return file with caching headers (24h cache)
    return FileResponse(
        file_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},  # 24 hours
    )


@router.delete("/avatar")
async def delete_user_avatar(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Delete user avatar.

    Removes avatar file and clears avatar fields in database.

    Args:
        current_user: Current user from JWT token
        session: Database session

    Returns:
        Success message
    """
    if not current_user.avatar_storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nessun avatar da eliminare",
        )

    try:
        # Delete file
        delete_avatar(current_user.avatar_storage_path)

        # Clear database fields
        current_user.avatar_url = None
        current_user.avatar_storage_path = None
        await session.commit()

        logger.info(f"Avatar deleted for user {current_user.id}")

        return success_response({"message": "Avatar eliminato con successo"})
    except Exception as e:
        logger.error(f"Failed to delete avatar for user {current_user.id}: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore durante l'eliminazione dell'avatar",
        ) from e
