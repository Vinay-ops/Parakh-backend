from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.database import get_db
from middleware.authentication import get_current_user
from schemas.inspection import (
    ComplianceRuleOut,
    ExtractedInformationOut,
    ExtractedInformationUpdate,
    InspectionCreate,
    InspectionOut,
)
from services import inspection_service
from utils.helpers import error, ok

router = APIRouter(prefix="/api/inspections", tags=["inspections"])


@router.post("")
def create_inspection(
    payload: InspectionCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an inspection record without an image scan.

    The primary flow is POST /api/scan (upload + ML). This endpoint exists for
    the Flutter history/manual-entry flow: it accepts product_name and
    product_category, and creates a PENDING_ML inspection.
    """
    inspection = inspection_service.create_inspection_for_scan(
        db, user["user_id"], payload.product_name, payload.product_category, None
    )
    return ok(
        data=InspectionOut.model_validate(inspection).model_dump(mode="json"),
        message="Inspection created",
    )


@router.get("")
def list_inspections(
    status: str | None = Query(None),
    category: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = inspection_service.list_inspections(
        db,
        user["user_id"],
        status=status,
        category=category,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return ok(
        data={
            "items": [InspectionOut.model_validate(i).model_dump(mode="json") for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        message="Inspections retrieved",
    )


@router.get("/{inspection_id}")
def get_inspection(
    inspection_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inspection = inspection_service.get_by_public_id(db, user["user_id"], inspection_id)
    if not inspection:
        error("Inspection not found", "NOT_FOUND", 404)
    return ok(
        data=InspectionOut.model_validate(inspection).model_dump(mode="json"),
        message="Inspection retrieved",
    )


@router.get("/{inspection_id}/extracted-info")
def get_extracted_info(
    inspection_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inspection = inspection_service.get_by_public_id(db, user["user_id"], inspection_id)
    if not inspection:
        error("Inspection not found", "NOT_FOUND", 404)
    extracted = inspection_service.get_extracted_info(db, inspection.id)
    if not extracted:
        error(
            "No extracted information available yet. ML processing is pending.",
            "NO_EXTRACTED_INFO",
            404,
        )
    return ok(
        data=ExtractedInformationOut.model_validate(extracted).model_dump(mode="json"),
        message="Extracted information retrieved",
    )


@router.patch("/{inspection_id}/extracted-info")
def update_extracted_info(
    inspection_id: str,
    payload: ExtractedInformationUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inspection = inspection_service.get_by_public_id(db, user["user_id"], inspection_id)
    if not inspection:
        error("Inspection not found", "NOT_FOUND", 404)
    extracted = inspection_service.get_extracted_info(db, inspection.id)
    if not extracted:
        error("No extracted information available yet. ML processing is pending.", "NO_EXTRACTED_INFO", 404)
    updated = inspection_service.update_extracted_info(
        db, extracted, payload.model_dump(exclude_unset=True)
    )
    return ok(
        data=ExtractedInformationOut.model_validate(updated).model_dump(mode="json"),
        message="Extracted information updated",
    )


@router.get("/{inspection_id}/compliance")
def get_compliance(
    inspection_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inspection = inspection_service.get_by_public_id(db, user["user_id"], inspection_id)
    if not inspection:
        error("Inspection not found", "NOT_FOUND", 404)
    rules = inspection_service.get_compliance_results(db, inspection.id)
    return ok(
        data={
            "inspection_id": inspection.inspection_id,
            "status": inspection.compliance_status,
            "score": inspection.compliance_score,
            "rules": [ComplianceRuleOut.model_validate(r).model_dump(mode="json") for r in rules],
        },
        message="Compliance results retrieved",
    )
