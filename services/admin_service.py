"""Admin business logic: inspector management, admin dashboard stats, admin inspection access.

All functions here operate without user_id scoping — they can access any
record.  They MUST only be called from endpoints protected by get_current_admin.
"""
import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import (
    Complaint,
    Inspection,
    Profile,
)
from services import auth_service


# ── Inspector management ──────────────────────────────────────────────────────

def get_inspector_by_user_id(db: Session, user_id: str) -> Profile | None:
    return db.query(Profile).filter(Profile.user_id == user_id).first()


def get_inspector_by_id(db: Session, profile_id: str) -> Profile | None:
    return db.query(Profile).filter(Profile.id == profile_id).first()


def get_inspector_by_email(db: Session, email: str) -> Profile | None:
    return db.query(Profile).filter(Profile.email == email).first()


def get_inspector_by_employee_id(db: Session, employee_id: str) -> Profile | None:
    return (
        db.query(Profile)
        .filter(Profile.employee_id == employee_id, Profile.employee_id.isnot(None))
        .first()
    )


def list_inspectors(
    db: Session,
    search: str | None = None,
    department: str | None = None,
    active: bool | None = None,
    role: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Profile], int]:
    query = db.query(Profile)
    if search:
        term = f"%{search}%"
        from sqlalchemy import or_
        query = query.filter(
            or_(
                Profile.full_name.ilike(term),
                Profile.email.ilike(term),
                Profile.employee_id.ilike(term),
            )
        )
    if department:
        query = query.filter(Profile.department == department)
    if active is not None:
        query = query.filter(Profile.active == active)
    if role:
        query = query.filter(Profile.role == role)
    total = query.count()
    items = (
        query.order_by(Profile.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def create_inspector_profile(
    db: Session,
    user_id: str,
    full_name: str,
    email: str,
    employee_id: str | None,
    department: str | None,
    phone: str | None,
    role: str = "inspector",
    active: bool = True,
) -> Profile:
    profile = Profile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        full_name=full_name,
        email=email,
        employee_id=employee_id,
        department=department,
        phone=phone,
        role=role,
        active=active,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_inspector_profile(db: Session, profile: Profile, updates: dict) -> Profile:
    for key, value in updates.items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


# ── Admin dashboard ───────────────────────────────────────────────────────────

def admin_dashboard_stats(db: Session) -> dict:
    total_inspectors = db.query(func.count(Profile.id)).scalar() or 0
    active_inspectors = (
        db.query(func.count(Profile.id)).filter(Profile.active == True).scalar() or 0  # noqa: E712
    )
    inactive_inspectors = total_inspectors - active_inspectors

    total_inspections = db.query(func.count(Inspection.id)).scalar() or 0

    terminal_statuses = ("COMPLIANT", "NON_COMPLIANT", "COMPLIANCE_READY", "EXTRACTED")
    pending_statuses = ("CREATED", "CAPTURING", "PENDING_ML", "PROCESSING")

    pending_inspections = (
        db.query(func.count(Inspection.id))
        .filter(Inspection.compliance_status.in_(pending_statuses))
        .scalar() or 0
    )
    completed_inspections = (
        db.query(func.count(Inspection.id))
        .filter(Inspection.compliance_status.in_(terminal_statuses))
        .scalar() or 0
    )
    compliant_inspections = (
        db.query(func.count(Inspection.id))
        .filter(Inspection.compliance_status == "COMPLIANT")
        .scalar() or 0
    )
    non_compliant_inspections = (
        db.query(func.count(Inspection.id))
        .filter(Inspection.compliance_status == "NON_COMPLIANT")
        .scalar() or 0
    )
    total_complaints = db.query(func.count(Complaint.id)).scalar() or 0

    recent = (
        db.query(Inspection, Profile)
        .outerjoin(Profile, Profile.user_id == Inspection.user_id)
        .order_by(Inspection.created_at.desc())
        .limit(10)
        .all()
    )
    recent_list = []
    for inspection, profile in recent:
        recent_list.append({
            "inspection_id": inspection.inspection_id,
            "product_name": inspection.product_name,
            "compliance_status": inspection.compliance_status,
            "inspection_date": str(inspection.inspection_date) if inspection.inspection_date else None,
            "inspector_name": profile.full_name if profile else None,
            "inspector_email": profile.email if profile else None,
        })

    return {
        "total_inspectors": total_inspectors,
        "active_inspectors": active_inspectors,
        "inactive_inspectors": inactive_inspectors,
        "total_inspections": total_inspections,
        "pending_inspections": pending_inspections,
        "completed_inspections": completed_inspections,
        "compliant_inspections": compliant_inspections,
        "non_compliant_inspections": non_compliant_inspections,
        "total_complaints": total_complaints,
        "recent_inspections": recent_list,
    }


# ── Admin inspection access (unscoped) ───────────────────────────────────────

def admin_list_inspections(
    db: Session,
    inspector_id: str | None = None,
    status: str | None = None,
    compliance: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    product_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple], int]:
    """Return (Inspection, Profile) tuples with full inspector info — no user_id filter."""
    query = db.query(Inspection, Profile).outerjoin(
        Profile, Profile.user_id == Inspection.user_id
    )
    if inspector_id:
        query = query.filter(Inspection.user_id == inspector_id)
    if status:
        query = query.filter(Inspection.compliance_status == status.upper())
    if compliance:
        query = query.filter(Inspection.compliance_status == compliance.upper())
    if date_from:
        query = query.filter(Inspection.inspection_date >= date_from)
    if date_to:
        query = query.filter(Inspection.inspection_date <= date_to)
    if search:
        term = f"%{search}%"
        from sqlalchemy import or_
        query = query.filter(
            or_(
                Inspection.product_name.ilike(term),
                Inspection.inspection_id.ilike(term),
            )
        )
    if product_type:
        query = query.filter(Inspection.product_type == product_type)

    total = query.count()
    rows = (
        query.order_by(Inspection.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def admin_get_inspection_by_public_id(
    db: Session, inspection_id: str
) -> tuple[Inspection, Profile | None] | None:
    """Fetch an inspection (unscoped) with its inspector profile."""
    row = (
        db.query(Inspection, Profile)
        .outerjoin(Profile, Profile.user_id == Inspection.user_id)
        .filter(Inspection.inspection_id == inspection_id)
        .first()
    )
    return row


def admin_list_complaints(
    db: Session,
    status: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    query = db.query(Complaint)
    if status:
        query = query.filter(Complaint.status == status.upper())
    if category:
        query = query.filter(Complaint.category == category)
    total = query.count()
    items = (
        query.order_by(Complaint.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total
