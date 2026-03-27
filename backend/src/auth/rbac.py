"""
Role-Based Access Control (RBAC) manager.
Handles permission checking and role management.
"""

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.models import Permission, Role, User, role_permissions


class RBACManager:
    """
    RBAC manager for permission checking and role operations.
    Provides both sync and async methods for flexibility.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize RBAC manager.

        Args:
            session: Async database session
        """
        self.session = session

    async def get_user_permissions(self, user_id: int) -> list[str]:
        """
        Get all permissions for a user (via their role).

        Args:
            user_id: User ID

        Returns:
            List of permission strings (e.g., ['positions:read', 'trading:execute'])

        Raises:
            ValueError: If user not found
        """
        # Get user with role and permissions
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.role).selectinload(Role.permissions))
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        # Get permissions from role
        stmt = (
            select(Permission)
            .join(role_permissions, Permission.id == role_permissions.c.permission_id)
            .where(role_permissions.c.role_id == user.role_id)
        )
        result = await self.session.execute(stmt)
        permissions = result.scalars().all()

        return [f"{p.resource}:{p.action}" for p in permissions]

    async def has_permission(self, user_id: int, resource: str, action: str) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User ID
            resource: Resource name (e.g., 'positions', 'trading')
            action: Action name (e.g., 'read', 'write', 'execute')

        Returns:
            True if user has permission, False otherwise
        """
        try:
            permissions = await self.get_user_permissions(user_id)
            required_permission = f"{resource}:{action}"
            has_perm = required_permission in permissions

            if not has_perm:
                logger.warning(
                    f"User {user_id} denied access to {required_permission}. "
                    f"User permissions: {permissions}"
                )

            return has_perm
        except ValueError as e:
            logger.error(f"Permission check failed: {e}")
            return False

    async def get_role_by_name(self, role_name: str) -> Role | None:
        """
        Get role by name.

        Args:
            role_name: Role name (e.g., 'VIEWER', 'TRADER', 'ADMIN')

        Returns:
            Role object or None if not found
        """
        stmt = select(Role).where(Role.name == role_name.upper())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_permission(self, resource: str, action: str) -> Permission | None:
        """
        Get permission by resource and action.

        Args:
            resource: Resource name
            action: Action name

        Returns:
            Permission object or None if not found
        """
        stmt = select(Permission).where(
            Permission.resource == resource, Permission.action == action
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def assign_role_permission(self, role_id: int, permission_id: int) -> None:
        """
        Assign a permission to a role.

        Args:
            role_id: Role ID
            permission_id: Permission ID

        Raises:
            ValueError: If role or permission not found
        """
        # Verify role exists
        role = await self.session.get(Role, role_id)
        if not role:
            raise ValueError(f"Role {role_id} not found")

        # Verify permission exists
        permission = await self.session.get(Permission, permission_id)
        if not permission:
            raise ValueError(f"Permission {permission_id} not found")

        # Insert into association table
        stmt = role_permissions.insert().values(role_id=role_id, permission_id=permission_id)
        await self.session.execute(stmt)
        await self.session.commit()

        logger.info(
            f"Assigned permission {permission.resource}:{permission.action} to role {role.name}"
        )

    async def create_role(self, name: str, description: str | None = None) -> Role:
        """
        Create a new role.

        Args:
            name: Role name (will be uppercased)
            description: Optional role description

        Returns:
            Created role

        Raises:
            ValueError: If role already exists
        """
        existing = await self.get_role_by_name(name)
        if existing:
            raise ValueError(f"Role {name} already exists")

        role = Role(name=name.upper(), description=description)
        self.session.add(role)
        await self.session.commit()
        await self.session.refresh(role)

        logger.info(f"Created role: {role.name}")
        return role

    async def create_permission(
        self, resource: str, action: str, description: str | None = None
    ) -> Permission:
        """
        Create a new permission.

        Args:
            resource: Resource name
            action: Action name
            description: Optional permission description

        Returns:
            Created permission

        Raises:
            ValueError: If permission already exists
        """
        existing = await self.get_permission(resource, action)
        if existing:
            raise ValueError(f"Permission {resource}:{action} already exists")

        permission = Permission(resource=resource, action=action, description=description)
        self.session.add(permission)
        await self.session.commit()
        await self.session.refresh(permission)

        logger.info(f"Created permission: {resource}:{action}")
        return permission
