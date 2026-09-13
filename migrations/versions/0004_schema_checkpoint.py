"""Schema checkpoint — no DDL changes.

Revision ID: 0004_schema_checkpoint
Revises: 0003_admin_profile
Create Date: 2026-09-13

This migration is a snapshot-forward checkpoint. It contains no DDL changes.

Purpose:
  - Establishes this commit as the agreed baseline for schema history.
  - Ensures ``alembic current`` and ``alembic heads`` reflect the deployed
    schema accurately.
  - All future schema changes should be tracked as Alembic migrations from
    this point forward.

Current schema (as of this checkpoint):
  Tables:
    profiles          — inspector/admin user profiles (links to auth.users)
    inspections       — one row per inspection attempt
    inspection_images — per-side image uploads (0002)
    extracted_information — OCR/ML extracted field values
    compliance_results    — per-rule compliance evaluation rows
    complaints            — user-filed complaints

  Notable columns added since 0001_initial:
    inspections.product_type   (0002)
    inspections.side_count     (0002)
    profiles.employee_id       (0003)
    profiles.phone             (0003)
    profiles.active            (0003)
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004_schema_checkpoint"
down_revision: Union[str, None] = "0003_admin_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No DDL — this migration is documentation only.
    pass


def downgrade() -> None:
    # No DDL to reverse.
    pass
