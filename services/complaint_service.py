from sqlalchemy.orm import Session

from database.models import Complaint, Inspection
from utils.helpers import public_id


def create_complaint(
    db: Session, user_id: str, data: dict, inspection_id: str | None = None
) -> Complaint:
    """Create a complaint.

    `inspection_id` is the internal inspections.id (UUID), resolved from the
    client-supplied public id by the API layer after an ownership check.
    """
    complaint = Complaint(
        complaint_id=public_id("CMP"),
        user_id=user_id,
        inspection_id=inspection_id,
        product_name=data.get("product_name"),
        complaint_title=data["complaint_title"],
        description=data.get("description"),
        category=data.get("category"),
        priority=data.get("priority", "MEDIUM"),
        status="OPEN",
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


def get_by_public_id(db: Session, user_id: str, complaint_id: str) -> Complaint | None:
    """Ownership-scoped fetch: user_id always comes from the auth token."""
    return (
        db.query(Complaint)
        .filter(Complaint.complaint_id == complaint_id, Complaint.user_id == user_id)
        .first()
    )


def list_complaints(
    db: Session,
    user_id: str,
    status: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Complaint], int]:
    query = db.query(Complaint).filter(Complaint.user_id == user_id)
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


def update_complaint(db: Session, complaint: Complaint, data: dict) -> Complaint:
    for field in ("complaint_title", "description", "category", "priority", "status"):
        value = data.get(field)
        if value is not None:
            setattr(complaint, field, value)
    db.commit()
    db.refresh(complaint)
    return complaint


def resolve_inspection_public_id(db: Session, internal_inspection_id: str | None) -> str | None:
    """Return the public INSP-XXXXXXXX identifier for the given internal UUID.

    Used when building the ComplaintOut response so that Flutter receives the
    public id it can use for inspection lookups, never the internal UUID.
    """
    if not internal_inspection_id:
        return None
    row = (
        db.query(Inspection.inspection_id)
        .filter(Inspection.id == internal_inspection_id)
        .first()
    )
    return row[0] if row else None


def complaint_response_dict(db: Session, complaint: Complaint) -> dict:
    """Build the dict used to validate a ComplaintOut response.

    `inspection_id` is replaced with the public INSP-XXXXXXXX identifier so
    that Flutter can use it directly with the inspections endpoints.
    """
    return {
        "id": complaint.id,
        "complaint_id": complaint.complaint_id,
        "inspection_id": resolve_inspection_public_id(db, complaint.inspection_id),
        "user_id": complaint.user_id,
        "product_name": complaint.product_name,
        "complaint_title": complaint.complaint_title,
        "description": complaint.description,
        "category": complaint.category,
        "priority": complaint.priority,
        "status": complaint.status,
        "created_at": complaint.created_at,
        "updated_at": complaint.updated_at,
    }
