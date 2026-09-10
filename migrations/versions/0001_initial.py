"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("profile_image_url", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"], unique=True)

    op.create_table(
        "inspections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("product_category", sa.String(length=100), nullable=True),
        sa.Column("product_image_url", sa.Text(), nullable=True),
        sa.Column("inspection_date", sa.Date(), nullable=True),
        sa.Column("inspection_time", sa.Time(), nullable=True),
        sa.Column("compliance_status", sa.String(length=32), server_default=sa.text("'PENDING_ML'"), nullable=True),
        sa.Column("compliance_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inspections_inspection_id", "inspections", ["inspection_id"], unique=True)
    op.create_index("ix_inspections_user_id", "inspections", ["user_id"], unique=False)

    op.create_table(
        "extracted_information",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("common_product_name", sa.String(length=255), nullable=True),
        sa.Column("manufacturer_name", sa.String(length=255), nullable=True),
        sa.Column("manufacturer_address", sa.String(length=255), nullable=True),
        sa.Column("packer_name", sa.String(length=255), nullable=True),
        sa.Column("packer_address", sa.String(length=255), nullable=True),
        sa.Column("importer_name", sa.String(length=255), nullable=True),
        sa.Column("importer_address", sa.String(length=255), nullable=True),
        sa.Column("multi_product_names", sa.JSON(), nullable=True),
        sa.Column("multi_product_quantities", sa.JSON(), nullable=True),
        sa.Column("net_quantity_value", sa.Float(), nullable=True),
        sa.Column("net_quantity_unit", sa.String(length=50), nullable=True),
        sa.Column("number_count", sa.Integer(), nullable=True),
        sa.Column("mrp", sa.Float(), nullable=True),
        sa.Column("mrp_tax_wording", sa.String(length=255), nullable=True),
        sa.Column("manufacture_or_import_date", sa.String(length=255), nullable=True),
        sa.Column("consumer_care_name", sa.String(length=255), nullable=True),
        sa.Column("consumer_care_address", sa.String(length=255), nullable=True),
        sa.Column("consumer_care_phone", sa.String(length=50), nullable=True),
        sa.Column("consumer_care_email", sa.String(length=255), nullable=True),
        sa.Column("commodity_dimensions", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extracted_information_inspection_id", "extracted_information", ["inspection_id"], unique=False)

    op.create_table(
        "compliance_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("required_value", sa.String(length=255), nullable=True),
        sa.Column("detected_value", sa.String(length=255), nullable=True),
        sa.Column("bounding_box", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_results_inspection_id", "compliance_results", ["inspection_id"], unique=False)

    op.create_table(
        "complaints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("complaint_id", sa.String(length=32), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("complaint_title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.String(length=20), server_default=sa.text("'MEDIUM'"), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'OPEN'"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_complaints_complaint_id", "complaints", ["complaint_id"], unique=True)
    op.create_index("ix_complaints_inspection_id", "complaints", ["inspection_id"], unique=False)
    op.create_index("ix_complaints_user_id", "complaints", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_complaints_user_id", table_name="complaints")
    op.drop_index("ix_complaints_inspection_id", table_name="complaints")
    op.drop_index("ix_complaints_complaint_id", table_name="complaints")
    op.drop_table("complaints")
    op.drop_index("ix_compliance_results_inspection_id", table_name="compliance_results")
    op.drop_table("compliance_results")
    op.drop_index("ix_extracted_information_inspection_id", table_name="extracted_information")
    op.drop_table("extracted_information")
    op.drop_index("ix_inspections_user_id", table_name="inspections")
    op.drop_index("ix_inspections_inspection_id", table_name="inspections")
    op.drop_table("inspections")
    op.drop_index("ix_profiles_user_id", table_name="profiles")
    op.drop_table("profiles")