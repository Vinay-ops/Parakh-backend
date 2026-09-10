"""Add multi-side inspection support

Adds product_type and side_count to inspections, and creates the
inspection_images table for per-side captured images.

Revision ID: 0002_multi_side
Revises: 0001_initial
Create Date: 2026-09-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_multi_side"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Add product_type and side_count to existing inspections table ─────────
    op.add_column("inspections", sa.Column("product_type", sa.String(length=64), nullable=True))
    op.add_column("inspections", sa.Column("side_count", sa.Integer(), nullable=True))

    # ── Create inspection_images table ────────────────────────────────────────
    op.create_table(
        "inspection_images",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("inspection_id", sa.Text(), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("side_order", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("public_url", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=64), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["inspection_id"], ["inspections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # Prevent duplicate side entries per inspection — retaking a side must
        # update the existing row, never insert a second one.
        sa.UniqueConstraint("inspection_id", "side", name="uq_inspection_images_inspection_side"),
    )
    op.create_index(
        "ix_inspection_images_inspection_id",
        "inspection_images",
        ["inspection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_inspection_images_inspection_id", table_name="inspection_images")
    op.drop_table("inspection_images")
    op.drop_column("inspections", "side_count")
    op.drop_column("inspections", "product_type")
