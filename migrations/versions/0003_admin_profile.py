"""Add employee_id, phone, active to profiles; add admin RLS policies

Revision ID: 0003_admin_profile
Revises: 0002_multi_side
Create Date: 2026-09-10

NOTE: The RLS policy SQL at the bottom of upgrade() must be executed once
against your Supabase PostgreSQL instance (via Supabase Dashboard → SQL Editor
or psql). It is included here for documentation and can be run directly.
Alembic will run the column changes; the RLS statements require the
supabase_admin role and may fail if run via the standard connection string —
in that case, run them manually in the Supabase SQL Editor.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_admin_profile"
down_revision: Union[str, None] = "0002_multi_side"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Add new columns to profiles ────────────────────────────────────────────
    op.add_column(
        "profiles",
        sa.Column("employee_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "profiles",
        sa.Column("phone", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "profiles",
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # ── Index on employee_id for fast lookup ──────────────────────────────────
    op.create_index(
        "ix_profiles_employee_id",
        "profiles",
        ["employee_id"],
        unique=False,
    )

    # ── RLS policies for admin access ─────────────────────────────────────────
    # These policies allow a row in profiles with role='admin' to bypass the
    # owner-only restriction on inspections/complaints for reading.
    # Run via Supabase SQL Editor if the migration connection lacks privileges:
    #
    # -- Admin can read all profiles
    # DROP POLICY IF EXISTS profiles_admin_read ON public.profiles;
    # CREATE POLICY profiles_admin_read ON public.profiles
    #   FOR SELECT
    #   USING (
    #     EXISTS (
    #       SELECT 1 FROM public.profiles p
    #       WHERE p.user_id = auth.uid() AND p.role = 'admin'
    #     )
    #   );
    #
    # -- Admin can read all inspections
    # DROP POLICY IF EXISTS inspections_admin_read ON public.inspections;
    # CREATE POLICY inspections_admin_read ON public.inspections
    #   FOR SELECT
    #   USING (
    #     EXISTS (
    #       SELECT 1 FROM public.profiles p
    #       WHERE p.user_id = auth.uid() AND p.role = 'admin'
    #     )
    #   );
    #
    # -- Admin can read all complaints
    # DROP POLICY IF EXISTS complaints_admin_read ON public.complaints;
    # CREATE POLICY complaints_admin_read ON public.complaints
    #   FOR SELECT
    #   USING (
    #     EXISTS (
    #       SELECT 1 FROM public.profiles p
    #       WHERE p.user_id = auth.uid() AND p.role = 'admin'
    #     )
    #   );
    #
    # Note: Backend API enforces admin role at the application layer via
    # get_current_admin(). The RLS policies are a defence-in-depth measure.
    # The backend uses the DATABASE_URL which connects as the postgres role
    # (which bypasses RLS by default in Supabase). RLS applies to direct
    # Supabase JS client connections only.
    pass


def downgrade() -> None:
    op.drop_index("ix_profiles_employee_id", table_name="profiles")
    op.drop_column("profiles", "active")
    op.drop_column("profiles", "phone")
    op.drop_column("profiles", "employee_id")
