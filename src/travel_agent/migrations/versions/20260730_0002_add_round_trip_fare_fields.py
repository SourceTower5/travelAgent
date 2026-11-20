"""add round-trip fare fields

Revision ID: 20260730_0002
Revises: 20260709_0001
Create Date: 2026-07-30

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_0002"
down_revision = "20260709_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("return_date", sa.String(), nullable=True))
    op.add_column(
        "fares",
        sa.Column("trip_type", sa.String(), nullable=False, server_default="one_way"),
    )
    op.add_column(
        "fares",
        sa.Column("price_kind", sa.String(), nullable=False, server_default="displayed"),
    )
    op.add_column("fares", sa.Column("source_freshness", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "source_freshness")
    op.drop_column("fares", "price_kind")
    op.drop_column("fares", "trip_type")
    op.drop_column("fares", "return_date")
