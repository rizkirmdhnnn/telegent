"""simpan nama sesi pada telegram_account

Revision ID: b7c2d41f9a10
Revises: 3a09799f1dae
Create Date: 2026-10-11 09:12:44.118902
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7c2d41f9a10'
down_revision: str | None = '3a09799f1dae'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('telegram_account', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_name', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('telegram_account', schema=None) as batch_op:
        batch_op.drop_column('session_name')