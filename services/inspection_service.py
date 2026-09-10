"""Inspection persistence and ML-result persistence.

The only place inspection records are created is `create_inspection_for_scan`,
called by POST /api/scan. ML results are persisted through
`apply_ml_result`, which the ML integration will invoke (synchronously from
within the scan flow, or later from a worker) — it never changes the Flutter
API contract.
"""
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import ComplianceResult, ExtractedInformation, Inspection
from utils.helpers import now_utc, public_id


def create_inspection_for_scan(
    db: Session, user_id: str, product_name: str | None, product_category: str | None, image_url: str
) -> Inspection:
    now = now_utc()
    inspection = Inspection(
        inspection_id=public_id("INSP"),
        user_id=user_id,
        product_name=product_name,
        product_category=product_category,
        product_image_url=image_url,
        inspection_date=now.date(),
        inspection_time=now.time().replace(microsecond=0),
        compliance_status="PENDING_ML",
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


def get_by_public_id(db: Session, user_id: str, inspection_id: str) -> Inspection | None:
    """Ownership-scoped fetch: user_id always comes from the auth token."""
    return (
        db.query(Inspection)
        .filter(Inspection.inspection_id == inspection_id, Inspection.user_id == user_id)
        .first()
    )


def list_inspections(
    db: Session,
    user_id: str,
    status: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Inspection], int]:
    query = db.query(Inspection).filter(Inspection.user_id == user_id)
    if status:
        query = query.filter(Inspection.compliance_status == status.upper())
    if category:
        query = query.filter(Inspection.product_category == category)
    if date_from:
        query = query.filter(Inspection.inspection_date >= date_from)
    if date_to:
        query = query.filter(Inspection.inspection_date <= date_to)
    total = query.count()
    items = (
        query.order_by(Inspection.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_extracted_info(db: Session, inspection_id: str) -> ExtractedInformation | None:
    return (
        db.query(ExtractedInformation)
        .filter(ExtractedInformation.inspection_id == inspection_id)
        .first()
    )


def update_extracted_info(db: Session, extracted: ExtractedInformation, values: dict) -> ExtractedInformation:
    for key, value in values.items():
        setattr(extracted, key, value)
    db.commit()
    db.refresh(extracted)
    return extracted


def get_compliance_results(db: Session, inspection_id: str) -> list[ComplianceResult]:
    return (
        db.query(ComplianceResult)
        .filter(ComplianceResult.inspection_id == inspection_id)
        .order_by(ComplianceResult.created_at.asc())
        .all()
    )


def apply_ml_result(db: Session, inspection: Inspection, ml_result: dict) -> Inspection:
    """Persist a validated ML result (see services/ml_service.ML_RESULT_SCHEMA).

    Called once the ML model is integrated. Creates/replaces the
    extracted_information row, replaces compliance_results rows, and updates
    the inspection's compliance status and score. The canonical result shape
    is {"product_information": {...}, "compliance": {"status", "score", "rules"}}
    (see docs/ML_INTEGRATION.md).
    """
    product_information = ml_result["product_information"]
    compliance = ml_result["compliance"]
    rules = compliance.get("rules") or []

    existing = get_extracted_info(db, inspection.id)
    if existing:
        db.delete(existing)
        db.query(ComplianceResult).filter(
            ComplianceResult.inspection_id == inspection.id
        ).delete()

    extracted = ExtractedInformation(inspection_id=inspection.id, **{
        key: product_information.get(key)
        for key in (
            "common_product_name", "manufacturer_name", "manufacturer_address",
            "packer_name", "packer_address", "importer_name", "importer_address",
            "multi_product_names", "multi_product_quantities", "net_quantity_value",
            "net_quantity_unit", "number_count", "mrp", "mrp_tax_wording",
            "manufacture_or_import_date", "consumer_care_name", "consumer_care_address",
            "consumer_care_phone", "consumer_care_email", "commodity_dimensions",
        )
    })
    db.add(extracted)
    for rule in rules:
        db.add(ComplianceResult(inspection_id=inspection.id, **{
            key: rule.get(key)
            for key in ("rule_name", "status", "reason", "required_value", "detected_value", "bounding_box")
        }))
    inspection.compliance_status = compliance.get("status") or "FAILED"
    inspection.compliance_score = compliance.get("score")
    db.commit()
    db.refresh(inspection)
    return inspection


def dashboard_stats(db: Session, user_id: str) -> dict:
    total_inspections = (
        db.query(func.count(Inspection.id)).filter(Inspection.user_id == user_id).scalar() or 0
    )
    from database.models import Complaint

    total_complaints = (
        db.query(func.count(Complaint.id)).filter(Complaint.user_id == user_id).scalar() or 0
    )
    reviewed = (
        db.query(func.count(Complaint.id))
        .filter(Complaint.user_id == user_id, Complaint.status.in_(("RESOLVED", "REJECTED")))
        .scalar() or 0
    )
    pending = (
        db.query(func.count(Complaint.id))
        .filter(Complaint.user_id == user_id, Complaint.status.in_(("OPEN", "UNDER_REVIEW")))
        .scalar() or 0
    )
    recent = (
        db.query(Inspection)
        .filter(Inspection.user_id == user_id)
        .order_by(Inspection.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "total_inspections": total_inspections,
        "total_complaints": total_complaints,
        "reviewed_complaints": reviewed,
        "pending_complaints": pending,
        "recent_inspections": [
            {
                "inspection_id": i.inspection_id,
                "product_name": i.product_name,
                "compliance_status": i.compliance_status,
                "inspection_date": str(i.inspection_date) if i.inspection_date else None,
            }
            for i in recent
        ],
    }
