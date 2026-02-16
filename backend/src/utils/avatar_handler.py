"""
Avatar file upload and management utilities.
Handles validation, resizing, storage, and cleanup of user avatar images.
"""

import os
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image
from fastapi import UploadFile, HTTPException, status
from loguru import logger

# Avatar configuration
MAX_AVATAR_SIZE_MB = 5
MAX_AVATAR_SIZE_BYTES = MAX_AVATAR_SIZE_MB * 1024 * 1024
AVATAR_SIZE = (256, 256)  # Target size for all avatars
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
AVATAR_QUALITY = 85  # JPEG quality for compression

# Storage path (relative to backend root)
AVATAR_STORAGE_DIR = Path("data/avatars")


class AvatarValidationError(Exception):
    """Raised when avatar file validation fails."""

    pass


def validate_avatar_file(file: UploadFile) -> None:
    """
    Validate avatar file type and size.

    Args:
        file: Uploaded file to validate

    Raises:
        AvatarValidationError: If validation fails
    """
    # Check file extension
    if not file.filename:
        raise AvatarValidationError("Il file non ha un nome valido")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(ALLOWED_EXTENSIONS)
        raise AvatarValidationError(
            f"Tipo di file non supportato. Usa uno di questi: {allowed}"
        )

    # Check content type
    if file.content_type and not file.content_type.startswith("image/"):
        raise AvatarValidationError(
            f"Il file deve essere un'immagine (ricevuto: {file.content_type})"
        )


def generate_avatar_filename(user_id: int, original_filename: str) -> str:
    """
    Generate unique filename for avatar.

    Args:
        user_id: User ID
        original_filename: Original uploaded filename

    Returns:
        Generated filename in format: {user_id}_{uuid}.jpg
    """
    # Always save as JPEG for consistency and compression
    unique_id = uuid.uuid4().hex[:8]
    return f"{user_id}_{unique_id}.jpg"


def get_avatar_storage_path() -> Path:
    """
    Get avatar storage directory path, creating it if needed.

    Returns:
        Path to avatar storage directory
    """
    storage_path = AVATAR_STORAGE_DIR
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def get_avatar_url(user_id: int) -> str:
    """
    Generate public URL for user avatar.

    Args:
        user_id: User ID

    Returns:
        Public URL path for avatar (e.g., /api/auth/avatar/123)
    """
    return f"/api/auth/avatar/{user_id}"


async def save_avatar(
    file: UploadFile, user_id: int, old_avatar_path: Optional[str] = None
) -> tuple[str, str]:
    """
    Save and process avatar image.

    This function:
    1. Validates the file
    2. Deletes old avatar if exists
    3. Resizes image to 256x256
    4. Saves as optimized JPEG
    5. Returns URL and storage path

    Args:
        file: Uploaded file
        user_id: User ID
        old_avatar_path: Path to old avatar to delete (optional)

    Returns:
        Tuple of (avatar_url, storage_path)

    Raises:
        HTTPException: If validation or processing fails
    """
    try:
        # Validate file
        validate_avatar_file(file)

        # Read file contents
        contents = await file.read()

        # Check file size
        if len(contents) > MAX_AVATAR_SIZE_BYTES:
            raise AvatarValidationError(
                f"Il file è troppo grande. Dimensione massima: {MAX_AVATAR_SIZE_MB}MB"
            )

        # Delete old avatar if exists
        if old_avatar_path:
            delete_avatar(old_avatar_path)

        # Open and process image
        try:
            image = Image.open(file.file)
        except Exception as e:
            logger.error(f"Failed to open image: {e}")
            raise AvatarValidationError("File immagine corrotto o non valido")

        # Convert to RGB if needed (for JPEG compatibility)
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Resize image to target size (with high-quality resampling)
        image = image.resize(AVATAR_SIZE, Image.Resampling.LANCZOS)

        # Generate filename and get storage path
        filename = generate_avatar_filename(user_id, file.filename or "avatar.jpg")
        storage_dir = get_avatar_storage_path()
        file_path = storage_dir / filename

        # Save optimized JPEG
        image.save(file_path, "JPEG", quality=AVATAR_QUALITY, optimize=True)

        logger.info(
            f"Avatar saved for user {user_id}: {file_path} ({len(contents)} bytes → {file_path.stat().st_size} bytes)"
        )

        # Generate URL and return paths
        avatar_url = get_avatar_url(user_id)
        storage_path = str(file_path)

        return avatar_url, storage_path

    except AvatarValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except Exception as e:
        logger.error(f"Failed to save avatar for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore durante il salvataggio dell'avatar",
        ) from e


def delete_avatar(storage_path: str) -> None:
    """
    Delete avatar file from storage.

    Args:
        storage_path: Path to avatar file to delete
    """
    try:
        path = Path(storage_path)
        if path.exists() and path.is_file():
            path.unlink()
            logger.info(f"Deleted avatar: {storage_path}")
    except Exception as e:
        logger.warning(f"Failed to delete avatar {storage_path}: {e}")


def get_avatar_file_path(user_id: int, storage_path: str) -> Optional[Path]:
    """
    Get file path for user avatar.

    Args:
        user_id: User ID
        storage_path: Storage path from database

    Returns:
        Path to avatar file, or None if not found
    """
    if not storage_path:
        return None

    path = Path(storage_path)
    if path.exists() and path.is_file():
        return path

    logger.warning(f"Avatar file not found for user {user_id}: {storage_path}")
    return None
