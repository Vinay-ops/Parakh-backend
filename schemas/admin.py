"""Pydantic schemas for admin endpoints."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Inspector creation ────────────────────────────────────────────────────────

class InspectorCreate(BaseModel):
    """Body for POST /api/admin/inspectors.

    The password is forwarded to Supabase Auth Admin API only — it is never
    stored in the application database.
    """
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, description="Initial password for Supabase Auth")
    employee_id: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    role: str = Field(default="inspector", max_length=100)
    active: bool = True


class InspectorUpdate(BaseModel):
    """Body for PATCH /api/admin/inspectors/{id}."""
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    employee_id: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    active: Optional[bool] = None
    # role can only be set by admin, never by the inspector themselves
    role: Optional[str] = Field(None, max_length=100)


class InspectorOut(BaseModel):
    """Safe representation of an inspector profile — no passwords, no secrets."""
    id: str
    user_id: str
    full_name: Optional[str]
    email: Optional[str]
    employee_id: Optional[str]
    department: Optional[str]
    phone: Optional[str]
    role: Optional[str]
    active: bool
    profile_image_url: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ── Admin dashboard ───────────────────────────────────────────────────────────

class AdminDashboardOut(BaseModel):
    total_inspectors: int
    active_inspectors: int
    inactive_inspectors: int
    total_inspections: int
    pending_inspections: int
    completed_inspections: int
    compliant_inspections: int
    non_compliant_inspections: int
    total_complaints: int
    recent_inspections: list[dict]


# ── Admin inspection list ─────────────────────────────────────────────────────

class AdminInspectionOut(BaseModel):
    """Inspection row enriched with inspector profile for admin views."""
    id: str
    inspection_id: str
    inspector_name: Optional[str]
    inspector_email: Optional[str]
    inspector_employee_id: Optional[str]
    product_name: Optional[str]
    product_category: Optional[str]
    product_type: Optional[str]
    side_count: Optional[int]
    compliance_status: Optional[str]
    compliance_score: Optional[float]
    inspection_date: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
