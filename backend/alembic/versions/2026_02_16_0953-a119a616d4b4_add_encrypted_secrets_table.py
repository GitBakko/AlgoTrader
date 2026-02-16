"""add_encrypted_secrets_table

Revision ID: a119a616d4b4
Revises: 2a157d127ac0
Create Date: 2026-02-16 09:53:55.436101

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a119a616d4b4"
down_revision: Union[str, Sequence[str], None] = "2a157d127ac0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add encrypted_secrets table."""
    op.create_table(
        "encrypted_secrets",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("key_name", sa.String(length=100), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_name"),
    )
    op.create_index(
        op.f("ix_encrypted_secrets_key_name"), "encrypted_secrets", ["key_name"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema - Drop encrypted_secrets table."""
    op.drop_index(op.f("ix_encrypted_secrets_key_name"), table_name="encrypted_secrets")
    op.drop_table("encrypted_secrets")
