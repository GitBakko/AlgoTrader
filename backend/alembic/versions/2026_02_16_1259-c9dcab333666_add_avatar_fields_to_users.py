"""add_avatar_fields_to_users

Revision ID: c9dcab333666
Revises: a119a616d4b4
Create Date: 2026-02-16 12:59:28.016910

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c9dcab333666"
down_revision: Union[str, Sequence[str], None] = "a119a616d4b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))
    op.add_column(
        "users", sa.Column("avatar_storage_path", sa.String(500), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "avatar_storage_path")
    op.drop_column("users", "avatar_url")
