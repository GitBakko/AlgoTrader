"""
Initialize roles and permissions for MANTIS AI.
Run this script to create/update roles and permissions in the database.

Usage:
    python scripts/init_permissions.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend root to path (so 'src' module can be imported)
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import Permission, Role, role_permissions
from src.auth.rbac import RBACManager
from src.database.session import DatabaseManager


async def init_permissions():
    """Initialize all roles and permissions."""

    # Initialize database
    DatabaseManager.initialize()

    async with DatabaseManager.session() as session:
        rbac = RBACManager(session)

        # Define roles
        roles_to_create = [
            {"name": "VIEWER", "description": "Read-only access to dashboards and data"},
            {"name": "TRADER", "description": "Trading execution + view access"},
            {"name": "ADMIN", "description": "Full system access including settings"},
        ]

        # Define permissions
        permissions_to_create = [
            # Dashboard
            {"resource": "dashboard", "action": "read", "description": "View dashboard"},
            # Positions
            {"resource": "positions", "action": "read", "description": "View positions"},
            {"resource": "positions", "action": "write", "description": "Manage positions"},
            # Trading
            {"resource": "trading", "action": "read", "description": "View trading data"},
            {"resource": "trading", "action": "execute", "description": "Execute trades"},
            # Markets
            {"resource": "markets", "action": "read", "description": "View market data"},
            # News
            {"resource": "news", "action": "read", "description": "View news"},
            # Models
            {"resource": "models", "action": "read", "description": "View AI models"},
            {"resource": "models", "action": "write", "description": "Manage AI models"},
            # Settings
            {"resource": "settings", "action": "read", "description": "View settings"},
            {"resource": "settings", "action": "write", "description": "Manage settings"},
            # System
            {"resource": "system", "action": "read", "description": "View system info"},
            {"resource": "system", "action": "write", "description": "Manage system"},
        ]

        # Create roles if they don't exist
        created_roles = {}
        for role_data in roles_to_create:
            try:
                role = await rbac.create_role(
                    name=role_data["name"],
                    description=role_data["description"]
                )
                created_roles[role_data["name"]] = role
                logger.success(f"✓ Created role: {role.name}")
            except ValueError:
                # Role already exists
                role = await rbac.get_role_by_name(role_data["name"])
                created_roles[role_data["name"]] = role
                logger.info(f"✓ Role already exists: {role.name}")

        # Create permissions if they don't exist
        created_permissions = {}
        for perm_data in permissions_to_create:
            try:
                perm = await rbac.create_permission(
                    resource=perm_data["resource"],
                    action=perm_data["action"],
                    description=perm_data.get("description")
                )
                key = f"{perm.resource}:{perm.action}"
                created_permissions[key] = perm
                logger.success(f"✓ Created permission: {key}")
            except ValueError:
                # Permission already exists
                perm = await rbac.get_permission(perm_data["resource"], perm_data["action"])
                key = f"{perm.resource}:{perm.action}"
                created_permissions[key] = perm
                logger.info(f"✓ Permission already exists: {key}")

        # Define role-permission mappings
        role_permission_map = {
            "VIEWER": [
                "dashboard:read",
                "positions:read",
                "trading:read",
                "markets:read",
                "news:read",
                "models:read",
                "settings:read",
                "system:read",
            ],
            "TRADER": [
                "dashboard:read",
                "positions:read",
                "positions:write",
                "trading:read",
                "trading:execute",
                "markets:read",
                "news:read",
                "models:read",
                "settings:read",
                "system:read",
            ],
            "ADMIN": [
                # Full access to everything
                "dashboard:read",
                "positions:read",
                "positions:write",
                "trading:read",
                "trading:execute",
                "markets:read",
                "news:read",
                "models:read",
                "models:write",
                "settings:read",
                "settings:write",  # ← This is the key permission for settings page
                "system:read",
                "system:write",
            ],
        }

        # Assign permissions to roles
        for role_name, permission_keys in role_permission_map.items():
            role = created_roles[role_name]

            # Get existing permissions for this role
            stmt = (
                select(Permission)
                .join(role_permissions, Permission.id == role_permissions.c.permission_id)
                .where(role_permissions.c.role_id == role.id)
            )
            result = await session.execute(stmt)
            existing_perms = result.scalars().all()
            existing_keys = {f"{p.resource}:{p.action}" for p in existing_perms}

            # Add missing permissions
            for perm_key in permission_keys:
                if perm_key in existing_keys:
                    logger.debug(f"  ✓ {role_name} already has {perm_key}")
                    continue

                perm = created_permissions[perm_key]

                # Insert into role_permissions table
                stmt = role_permissions.insert().values(
                    role_id=role.id,
                    permission_id=perm.id
                )
                await session.execute(stmt)
                logger.success(f"  ✓ Assigned {perm_key} to {role_name}")

            await session.commit()

        logger.success("🎉 Roles and permissions initialized successfully!")

        # Summary
        logger.info("\n" + "="*60)
        logger.info("ROLE PERMISSIONS SUMMARY")
        logger.info("="*60)
        for role_name in ["VIEWER", "TRADER", "ADMIN"]:
            role = created_roles[role_name]
            stmt = (
                select(Permission)
                .join(role_permissions, Permission.id == role_permissions.c.permission_id)
                .where(role_permissions.c.role_id == role.id)
            )
            result = await session.execute(stmt)
            perms = result.scalars().all()
            perm_list = [f"{p.resource}:{p.action}" for p in perms]

            logger.info(f"\n{role_name} ({len(perm_list)} permissions):")
            for perm_key in sorted(perm_list):
                logger.info(f"  • {perm_key}")
        logger.info("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(init_permissions())
