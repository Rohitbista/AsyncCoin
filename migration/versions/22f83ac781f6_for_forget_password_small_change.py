"""for forget password small change

Revision ID: 22f83ac781f6
Revises: e771703df056
Create Date: 2026-10-15 10:45:36.845111

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
CONSTRAINT = "ck_user_tokens_purpose_valid"


# revision identifiers, used by Alembic.
revision: str = '22f83ac781f6'
down_revision: Union[str, Sequence[str], None] = 'e771703df056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "UPDATE user_tokens SET purpose = 'reset_password' WHERE purpose = 'password_reset'"
    )
    op.drop_constraint(op.f(CONSTRAINT), "user_tokens", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "user_tokens",
        "purpose IN ('verify_email', 'reset_password')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM user_tokens WHERE purpose = 'reset_password'")
    op.drop_constraint(op.f(CONSTRAINT), "user_tokens", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "user_tokens",
        "purpose IN ('verify_email', 'password_reset')",
    )
