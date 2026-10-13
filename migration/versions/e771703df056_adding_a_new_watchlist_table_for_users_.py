"""adding a new watchlist table for users personal selected coins

Revision ID: e771703df056
Revises: e6bc828467c9
Create Date: 2026-10-09 18:29:41.058158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e771703df056'
down_revision: Union[str, Sequence[str], None] = 'e6bc828467c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_watchlist",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("coin_id", sa.String(length=128), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("alert_above", sa.Float(), nullable=True),
        sa.Column("alert_below", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "coin_id", name="uq_user_watchlist_user_id_coin_id"),
        sa.CheckConstraint("coin_id = lower(coin_id)", name="watchlist_coin_id_lowercase"),
        sa.CheckConstraint("alert_above IS NULL OR alert_above > 0", name="watchlist_alert_above_positive"),
        sa.CheckConstraint("alert_below IS NULL OR alert_below > 0", name="watchlist_alert_below_positive"),
    )
    op.create_index("ix_user_watchlist_user_id", "user_watchlist", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_watchlist_user_id", table_name="user_watchlist")
    # Dropping the table also drops its constraints.
    op.drop_table("user_watchlist")
