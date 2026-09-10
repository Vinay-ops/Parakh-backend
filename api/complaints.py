from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.database import get_db
from middleware.authentication import get_current_user
from schemas.complaint import ComplaintCreate, ComplaintOut, ComplaintUpdate
from services import complaint_service, inspection_service
from utils.helpers import error, ok

router = APIRouter(prefix="/api/complaints", tags=["complaints"])


def _out(db: Session, complaint) -> dict:
    """Serialize a Complaint ORM object to the ComplaintOut dict.

    `inspection_id` is replaced with the public INSP-XXXXXXXX identifier so
    that Flutter receives the human-readable public id, never the internal UUID.
    """
    return ComplaintOut.model_validate(
        complaint_service.complaint_response_dict(db, complaint)
    ).model_dump(mode="json")


@router.post("")
def create_complaint(
    payload: ComplaintCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # If the complaint references an inspection, that inspection must belong
    # to the authenticated user — never trust ids sent by the client. The
    # public id is resolved to the internal UUID before persisting.
    internal_inspection_id = None
    if payload.inspection_id:
        inspection = inspection_service.get_by_public_id(
            db, user["user_id"], payload.inspection_id
        )
        if not inspection:
            error("Referenced inspection not found", "NOT_FOUND", 404)
        internal_inspection_id = inspection.id
    complaint = complaint_service.create_complaint(
        db, user["user_id"], payload.model_dump(), inspection_id=internal_inspection_id
    )
    return ok(data=_out(db, complaint), message="Complaint created")


@router.get("")
def list_complaints(
    status: str | None = Query(None),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = complaint_service.list_complaints(
        db, user["user_id"], status=status, category=category, page=page, page_size=page_size
    )
    return ok(
        data={
            "items": [_out(db, c) for c in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        message="Complaints retrieved",
    )


@router.get("/{complaint_id}")
def get_complaint(
    complaint_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    complaint = complaint_service.get_by_public_id(db, user["user_id"], complaint_id)
    if not complaint:
        error("Complaint not found", "NOT_FOUND", 404)
    return ok(data=_out(db, complaint), message="Complaint retrieved")


@router.patch("/{complaint_id}")
def update_complaint(
    complaint_id: str,
    payload: ComplaintUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    complaint = complaint_service.get_by_public_id(db, user["user_id"], complaint_id)
    if not complaint:
        error("Complaint not found", "NOT_FOUND", 404)
    complaint = complaint_service.update_complaint(
        db, complaint, payload.model_dump(exclude_unset=True)
    )
    return ok(data=_out(db, complaint), message="Complaint updated")
