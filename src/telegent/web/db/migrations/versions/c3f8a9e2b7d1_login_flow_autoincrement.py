"""login_flow memakai AUTOINCREMENT (id tidak dipakai ulang)

Revision ID: c3f8a9e2b7d1
Revises: b7c2d41f9a10
Create Date: 2026-10-11 10:04:12.773915
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3f8a9e2b7d1'
down_revision: str | None = 'b7c2d41f9a10'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite tidak mendukung ubah AUTOINCREMENT secara in-place: tabel dibuat
    # ulang oleh mode batch Alembic.
    with op.batch_alter_table(
        'login_flow', table_kwargs={'sqlite_autoincrement': True}
    ) as batch_op:
        batch_op.alter_column(
            'status', existing_type=sa.String(length=32), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table(
        'login_flow', table_kwargs={'sqlite_autoincrement': False}
    ) as batch_op:
        batch_op.alter_column(
            'status', existing_type=sa.String(length=32), nullable=False
        )