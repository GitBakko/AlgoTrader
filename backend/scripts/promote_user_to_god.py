"""
Script to promote user to GOD role with all permissions.
"""
import asyncio
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.auth.models import User, Role, Permission, role_permissions
from src.utils.config import get_settings


async def promote_to_god(username: str):
    """Promote user to GOD role with all permissions."""
    settings = get_settings()

    # Create engine - replace postgresql:// with postgresql+asyncpg://
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Check if GOD role exists, create if not
        result = await session.execute(select(Role).where(Role.name == "GOD"))
        god_role = result.scalar_one_or_none()

        if not god_role:
            print("Creating GOD role...")
            god_role = Role(
                name="GOD",
                description="Supreme administrator with unrestricted access to all system functions"
            )
            session.add(god_role)
            await session.commit()
            await session.refresh(god_role)
            print(f"[OK] GOD role created (ID: {god_role.id})")
        else:
            print(f"[OK] GOD role already exists (ID: {god_role.id})")

        # 2. Get all permissions
        result = await session.execute(select(Permission))
        all_permissions = result.scalars().all()
        print(f"[INFO] Found {len(all_permissions)} permissions in system")

        # 3. Assign ALL permissions to GOD role
        # Clear existing permissions for GOD role
        await session.execute(
            delete(role_permissions).where(role_permissions.c.role_id == god_role.id)
        )

        # Add all permissions
        for perm in all_permissions:
            stmt = role_permissions.insert().values(
                role_id=god_role.id,
                permission_id=perm.id
            )
            await session.execute(stmt)

        await session.commit()
        print(f"[OK] Assigned {len(all_permissions)} permissions to GOD role")

        # 4. Update user to GOD role
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user:
            print(f"[ERROR] User '{username}' not found!")
            return

        old_role_id = user.role_id
        user.role_id = god_role.id
        await session.commit()

        print(f"\n{'='*60}")
        print(f"USER PROMOTED TO GOD!")
        print(f"{'='*60}")
        print(f"Username: {user.username}")
        print(f"Email: {user.email}")
        print(f"Old Role ID: {old_role_id}")
        print(f"New Role: GOD (ID: {god_role.id})")
        print(f"Permissions: ALL ({len(all_permissions)} permissions)")
        print(f"{'='*60}")
        print(f"\n[SUCCESS] User '{username}' now has UNRESTRICTED ACCESS to the entire system")

    await engine.dispose()


if __name__ == "__main__":
    import sys

    username = sys.argv[1] if len(sys.argv) > 1 else "Bakko^"
    asyncio.run(promote_to_god(username))
