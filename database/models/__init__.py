from sqlalchemy import Column, Table, Uuid

from database.database import Base

# Supabase stores identities in auth.users, which lives outside this
# application's metadata. Register a minimal reference so the ORM can resolve
# foreign keys targeting it at DML-compile time. The table itself is created
# and managed by Supabase — never by this application or by Alembic.
Table("users", Base.metadata, Column("id", Uuid(as_uuid=False)), schema="auth")

from database.models.complaint import Complaint, COMPLAINT_STATUSES
from database.models.compliance_result import ComplianceResult
from database.models.extracted_information import ExtractedInformation
from database.models.inspection import Inspection, INSPECTION_STATUSES
from database.models.inspection_image import InspectionImage, VALID_SIDES
from database.models.profile import Profile

__all__ = [
    "Complaint",
    "COMPLAINT_STATUSES",
    "ComplianceResult",
    "ExtractedInformation",
    "Inspection",
    "INSPECTION_STATUSES",
    "InspectionImage",
    "VALID_SIDES",
    "Profile",
]