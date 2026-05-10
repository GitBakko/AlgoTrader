"""
Authentication API router.
Handles user login, registration, and profile retrieval.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from loguru import logger
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import success_response

limiter = Limiter(key_func=get_remote_address)
from src.auth.dependencies import get_current_user
from src.auth.jwt import create_access_token
from src.auth.models import RefreshToken, Role, User
from src.auth.password import hash_password, verify_password
from src.auth.rbac import RBACManager
from src.auth.schemas import (
    LoginRequest,
    LoginResponse,
    PermissionResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    UserResponse,
)
from src.database.session import get_db_session
from src.utils.avatar_handler import delete_avatar, get_avatar_file_path, save_avatar
from src.utils.config import get_settings

router = APIRouter()


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Authenticate user and return JWT token with user info.

    Args:
        request: FastAPI request (for rate limiting)
        body: Login credentials (username, password)
        session: Database session

    Returns:
        Access token with expiration time and user information

    Raises:
        HTTPException: 401 if credentials invalid
    """
    # Find user by username
    stmt = select(User).where(User.username == body.username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not verify_password(body.password, user.hashed_password):
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

    # Update last login (naive UTC for TIMESTAMP WITHOUT TIME ZONE column)
    user.last_login = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()

    # Get role name for response
    stmt_role = select(Role).where(Role.id == user.role_id)
    result_role = await session.execute(stmt_role)
    role = result_role.scalar_one_or_none()

    # Get role permissions
    from src.auth.models import Permission, role_permissions

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

    # Create refresh token (7 days default)
    refresh_token = RefreshToken(
        user_id=user.id,
        expires_at=datetime.now(UTC).replace(tzinfo=None)
        + timedelta(days=settings.refresh_token_expire_days),
    )
    session.add(refresh_token)
    await session.commit()
    await session.refresh(refresh_token)

    logger.info(f"User {user.username} logged in successfully with {len(permissions)} permissions")

    return success_response(
        LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            refresh_token=refresh_token.token,
            refresh_expires_in=settings.refresh_token_expire_days * 86400,
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                role_id=user.role_id,
                role_name=role.name if role else "UNKNOWN",
                is_active=user.is_active,
                last_login=user.last_login,
                avatar_url=user.avatar_url,
                permissions=[
                    PermissionResponse(id=p.id, resource=p.resource, action=p.action)
                    for p in permissions
                ],
            ),
        ).model_dump()
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def register(
    request: Request,
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Register a new user.

    C2-API security fix: any non-VIEWER role_name supplied by an
    unauthenticated request is silently downgraded to VIEWER.
    Privilege escalation via self-registration is now impossible —
    higher roles must be granted by an ADMIN through a separate flow.

    Args:
        request: FastAPI request (for rate limiting + auth probe)
        body: Registration data (username, email, password, role)
        session: Database session

    Returns:
        Created user information

    Raises:
        HTTPException: 400 if username/email already exists
    """
    # Probe for an authenticated ADMIN caller. Any other case (no token,
    # invalid token, non-ADMIN role) silently forces VIEWER.
    requested_role = (body.role_name or "VIEWER").upper()
    effective_role = "VIEWER"
    if requested_role != "VIEWER":
        try:
            from src.auth.dependencies import get_current_user as _get_user  # noqa: PLC0415

            current = await _get_user(request, session)
            current_role = await RBACManager(session).get_role_by_id(current.role_id)
            if current_role and current_role.name == "ADMIN":
                effective_role = requested_role
            else:
                logger.warning(
                    f"Register: role downgrade {requested_role}→VIEWER "
                    f"(caller user_id={current.id} role={getattr(current_role,'name',None)})"
                )
        except Exception:
            logger.warning(
                f"Register: role downgrade {requested_role}→VIEWER "
                f"(unauthenticated request)"
            )

    # Check if username already exists
    stmt = select(User).where(User.username == body.username)
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Check if email already exists
    stmt = select(User).where(User.email == body.email)
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Get role
    rbac = RBACManager(session)
    role = await rbac.get_role_by_name(effective_role)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {effective_role}. Must be one of: VIEWER, TRADER, ADMIN",
        )

    # Create user
    hashed_pwd = hash_password(body.password)
    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hashed_pwd,
        role_id=role.id,
        is_active=True,
    )

    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info(f"New user registered: {user.username} with role {effective_role}")

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

    # Get role permissions (same as login endpoint)
    from src.auth.models import Permission, role_permissions

    stmt_perms = (
        select(Permission)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .where(role_permissions.c.role_id == current_user.role_id)
    )
    result_perms = await session.execute(stmt_perms)
    permissions = result_perms.scalars().all()

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
            permissions=[
                PermissionResponse(id=p.id, resource=p.resource, action=p.action)
                for p in permissions
            ],
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
# Token Refresh & Logout
# ═════════════════════════════════════════════════════════════════════════════


@router.post("/refresh")
async def refresh_token(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Refresh access token using a valid refresh token (token rotation).

    The old refresh token is revoked and a new pair (access + refresh) is issued.
    Also cleans up expired tokens older than 30 days for the same user.
    """
    # Find the refresh token
    stmt = select(RefreshToken).where(
        RefreshToken.token == body.refresh_token,
        RefreshToken.is_revoked == False,  # noqa: E712
    )
    result = await session.execute(stmt)
    rt = result.scalar_one_or_none()

    if not rt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token",
        )

    # Check expiration
    now = datetime.now(UTC).replace(tzinfo=None)
    if rt.expires_at < now:
        rt.is_revoked = True
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    # Revoke old token
    rt.is_revoked = True

    # Load the user
    stmt_user = select(User).where(User.id == rt.user_id, User.is_active == True)  # noqa: E712
    result_user = await session.execute(stmt_user)
    user = result_user.scalar_one_or_none()

    if not user:
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Create new access token
    settings = get_settings()
    access_token = create_access_token({"sub": str(user.id)})

    # Create new refresh token (rotation)
    new_rt = RefreshToken(
        user_id=user.id,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    session.add(new_rt)

    # Cleanup: delete expired tokens older than 30 days for this user
    cutoff = now - timedelta(days=30)
    stmt_cleanup = select(RefreshToken).where(
        RefreshToken.user_id == user.id,
        RefreshToken.expires_at < cutoff,
    )
    result_cleanup = await session.execute(stmt_cleanup)
    old_tokens = result_cleanup.scalars().all()
    for old_t in old_tokens:
        await session.delete(old_t)

    await session.commit()
    await session.refresh(new_rt)

    logger.info(f"Token refreshed for user {user.username}")

    return success_response(
        RefreshResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            refresh_token=new_rt.token,
            refresh_expires_in=settings.refresh_token_expire_days * 86400,
        ).model_dump()
    )


@router.post("/logout")
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Logout user by revoking all their refresh tokens.
    """
    stmt = select(RefreshToken).where(
        RefreshToken.user_id == current_user.id,
        RefreshToken.is_revoked == False,  # noqa: E712
    )
    result = await session.execute(stmt)
    tokens = result.scalars().all()

    for token in tokens:
        token.is_revoked = True

    await session.commit()

    logger.info(f"User {current_user.username} logged out, {len(tokens)} refresh tokens revoked")

    return success_response({"message": "Logged out successfully"})


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
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Retrieve user avatar image.

    C3-API security fix: now requires auth + verifies the resolved file
    path stays inside ``AVATAR_STORAGE_DIR`` (path-traversal containment).
    MIME type detected via stdlib ``mimetypes`` instead of hard-coded
    ``image/jpeg`` (M5-API).

    Args:
        user_id: User ID
        current_user: Authenticated caller (any role)
        session: Database session

    Returns:
        Avatar image file
    """
    # Get user
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.avatar_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar non trovato")

    # Get file path
    file_path = get_avatar_file_path(user_id, user.avatar_storage_path)
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File avatar non trovato")

    # Path-traversal containment: resolve symlinks + verify the file is
    # under AVATAR_STORAGE_DIR. Refuse to serve anything outside.
    import mimetypes  # noqa: PLC0415
    from src.utils.avatar_handler import AVATAR_STORAGE_DIR  # noqa: PLC0415

    try:
        resolved = Path(file_path).resolve()
        avatar_root = AVATAR_STORAGE_DIR.resolve()
        if not resolved.is_relative_to(avatar_root):
            logger.warning(
                f"avatar serve refused — path {resolved} outside {avatar_root}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File avatar non trovato",
            )
    except (RuntimeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File avatar non trovato"
        )

    media_type, _ = mimetypes.guess_type(str(resolved))
    if media_type is None:
        media_type = "application/octet-stream"

    # Return file with caching headers (24h cache)
    return FileResponse(
        resolved,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},  # 24 hours
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
