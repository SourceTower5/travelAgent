"""create history tables

Revision ID: 20260709_0001
Revises:
Create Date: 2026-07-09

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260709_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("destination", sa.String(), nullable=False),
        sa.Column("departure_date", sa.String(), nullable=False),
        sa.Column("passengers", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "fares",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("destination", sa.String(), nullable=False),
        sa.Column("departure_date", sa.String(), nullable=False),
        sa.Column("cabin", sa.String(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("available_seats", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.String(), nullable=False),
        sa.Column("booking_url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("fares")
    op.drop_table("searches")
