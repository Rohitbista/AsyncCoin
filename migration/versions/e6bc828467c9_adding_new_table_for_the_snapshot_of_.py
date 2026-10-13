"""adding new table for the snapshot of crypto currency information

Revision ID: e6bc828467c9
Revises: 136fcdf90e16
Create Date: 2026-10-08 17:28:46.848249

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6bc828467c9'
down_revision: Union[str, Sequence[str], None] = '136fcdf90e16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crypto_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coin_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("image", sa.String(length=512), nullable=True),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("market_cap_rank", sa.Integer(), nullable=True),
        sa.Column("fully_diluted_valuation", sa.Float(), nullable=True),
        sa.Column("total_volume", sa.Float(), nullable=True),
        sa.Column("high_24h", sa.Float(), nullable=True),
        sa.Column("low_24h", sa.Float(), nullable=True),
        sa.Column("price_change_24h", sa.Float(), nullable=True),
        sa.Column("price_change_percentage_24h", sa.Float(), nullable=True),
        sa.Column("market_cap_change_24h", sa.Float(), nullable=True),
        sa.Column("market_cap_change_percentage_24h", sa.Float(), nullable=True),
        sa.Column("circulating_supply", sa.Float(), nullable=True),
        sa.Column("total_supply", sa.Float(), nullable=True),
        sa.Column("max_supply", sa.Float(), nullable=True),
        sa.Column("ath", sa.Float(), nullable=True),
        sa.Column("ath_change_percentage", sa.Float(), nullable=True),
        sa.Column("ath_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atl", sa.Float(), nullable=True),
        sa.Column("atl_change_percentage", sa.Float(), nullable=True),
        sa.Column("atl_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crypto_snapshots")),
    )
    op.create_index(
        "ix_crypto_snapshots_coin_id_fetched_at",
        "crypto_snapshots",
        ["coin_id", "fetched_at"],
    )
    op.create_index(
        "ix_crypto_snapshots_fetched_at_rank",
        "crypto_snapshots",
        ["fetched_at", "market_cap_rank"],
    )
 
 
def downgrade() -> None:
    op.drop_index("ix_crypto_snapshots_fetched_at_rank", table_name="crypto_snapshots")
    op.drop_index("ix_crypto_snapshots_coin_id_fetched_at", table_name="crypto_snapshots")
    op.drop_table("crypto_snapshots")
