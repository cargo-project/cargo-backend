"""códigos de un solo uso para recuperar la contraseña por Telegram

Revision ID: 8b1f4d2e6a90
Revises: 5c3e9a1d7b42
Create Date: 2026-11-24 20:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b1f4d2e6a90"
down_revision: str | None = "5c3e9a1d7b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_password_reset_codes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_codes")),
    )
    op.create_index("ix_password_reset_codes_user_created", "password_reset_codes", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_codes_user_created", table_name="password_reset_codes")
    op.drop_table("password_reset_codes")
