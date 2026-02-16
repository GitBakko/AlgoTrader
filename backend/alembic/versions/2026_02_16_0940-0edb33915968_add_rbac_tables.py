"""add_rbac_tables

Revision ID: 0edb33915968
Revises: 572afc1a68d9
Create Date: 2026-02-16 09:40:33.013232

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0edb33915968"
down_revision: Union[str, Sequence[str], None] = "572afc1a68d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add RBAC tables."""
    # Create roles table
    op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=False)

    # Create permissions table
    op.create_table(
        "permissions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("resource", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource", "action", name="uq_permission_resource_action"),
    )
    op.create_index(op.f("ix_permissions_resource"), "permissions", ["resource"], unique=False)
    op.create_index(op.f("ix_permissions_action"), "permissions", ["action"], unique=False)

    # Create role_permissions association table
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    # Insert default roles
    op.execute(
        """
        INSERT INTO roles (name, description) VALUES
        ('VIEWER', 'View-only access to positions, signals, and markets'),
        ('TRADER', 'Full trading execution and strategy management'),
        ('ADMIN', 'Full system administration and user management')
        """
    )

    # Insert default permissions
    op.execute(
        """
        INSERT INTO permissions (resource, action, description) VALUES
        -- Viewer permissions
        ('positions', 'read', 'View open positions'),
        ('signals', 'read', 'View trading signals'),
        ('markets', 'read', 'View market data'),
        ('dashboard', 'read', 'View dashboard'),
        -- Trader permissions
        ('positions', 'write', 'Manage positions'),
        ('trading', 'execute', 'Execute trades'),
        ('backtest', 'execute', 'Run backtests'),
        -- Admin permissions
        ('settings', 'write', 'Modify system settings'),
        ('users', 'write', 'Manage users'),
        ('system', 'write', 'System administration')
        """
    )

    # Assign permissions to roles
    op.execute(
        """
        -- VIEWER: read-only permissions
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'VIEWER' AND p.action = 'read';

        -- TRADER: all viewer permissions + write/execute permissions
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'TRADER' AND (p.action = 'read' OR p.resource IN ('positions', 'trading', 'backtest'));

        -- ADMIN: all permissions
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'ADMIN';
        """
    )


def downgrade() -> None:
    """Downgrade schema - Drop RBAC tables."""
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_permissions_action"), table_name="permissions")
    op.drop_index(op.f("ix_permissions_resource"), table_name="permissions")
    op.drop_table("permissions")
    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")
