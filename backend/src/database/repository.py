"""
Base repository pattern for database operations.
Provides generic CRUD operations for all models.
"""

from typing import Any, Generic, TypeVar

from loguru import logger
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

# Generic type for model
ModelType = TypeVar("ModelType", bound=SQLModel)


class BaseRepository(Generic[ModelType]):
    """
    Base repository with CRUD operations.
    Inherit from this class to create model-specific repositories.
    """

    def __init__(self, model: type[ModelType], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: SQLModel class for this repository
            session: Database session
        """
        self.model = model
        self.session = session

    async def create(self, obj: ModelType) -> ModelType:
        """
        Create a new record.

        Args:
            obj: Model instance to create

        Returns:
            Created model instance with ID populated
        """
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        logger.debug(f"Created {self.model.__name__} with ID {obj.id}")
        return obj

    async def get_by_id(self, id: int) -> ModelType | None:
        """
        Get record by ID.

        Args:
            id: Record ID

        Returns:
            Model instance or None if not found
        """
        result = await self.session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelType]:
        """
        Get all records with pagination.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of model instances
        """
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset).order_by(self.model.id.desc())
        )
        return list(result.scalars().all())

    async def update(self, id: int, values: dict[str, Any]) -> ModelType | None:
        """
        Update record by ID.

        Args:
            id: Record ID
            values: Dictionary of field values to update

        Returns:
            Updated model instance or None if not found
        """
        await self.session.execute(
            update(self.model).where(self.model.id == id).values(**values)
        )
        logger.debug(f"Updated {self.model.__name__} ID {id}")
        return await self.get_by_id(id)

    async def delete(self, id: int) -> bool:
        """
        Delete record by ID.

        Args:
            id: Record ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(delete(self.model).where(self.model.id == id))
        deleted = result.rowcount > 0
        if deleted:
            logger.debug(f"Deleted {self.model.__name__} ID {id}")
        return deleted

    async def count(self) -> int:
        """
        Count total records.

        Returns:
            Total record count
        """
        result = await self.session.execute(select(self.model))
        return len(list(result.scalars().all()))

    async def exists(self, id: int) -> bool:
        """
        Check if record exists by ID.

        Args:
            id: Record ID

        Returns:
            True if exists, False otherwise
        """
        result = await self.session.execute(
            select(self.model.id).where(self.model.id == id).limit(1)
        )
        return result.scalar_one_or_none() is not None
