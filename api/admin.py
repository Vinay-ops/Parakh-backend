"""Admin API router.

All endpoints here require:
1. A valid Supabase access token
2. The authenticated user's profiles.role == 'admin'

The service-role key is used only within auth_service.create_user_with_service_role()
and never appears in responses or logs.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Inspection
from middleware.authentication import get_current_admin
from schemas.admin import AdminInspectionOut, InspectorCreate, InspectorOut, InspectorUpdate
from schemas.inspection import (
    ComplianceRuleOut,
    ExtractedInformationOut,
    InspectionImageOut,
    InspectionOut,
)
from services import admin_service, auth_service, image_service, inspection_service
from utils.helpers import error, ok

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Inspector management ──────────────────────────────────────────────────────

@router.get("/inspectors")
def list_inspectors(
    search: str | None = Query(None),
    department: str | None = Query(None),
    active: bool | None = Query(None),
    role: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    items, total = admin_service.list_inspectors(
        db,
        search=search,
        department=department,
        active=active,
        role=role,
        page=page,
        page_size=page_size,
    )
    return ok(
        data={
            "items": [InspectorOut.model_validate(p).model_dump(mode="json") for p in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        message="Inspectors retrieved",
    )


@router.post("/inspectors")
def create_inspector(
    payload: InspectorCreate,
    _admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Create a new inspector.

    Flow:
    1. Validate no duplicate email / employee_id in profiles.
    2. Call Supabase Auth Admin API (service-role, backend only) to create the auth user.
    3. Create the profile row.
    4. On profile creation failure, delete the auth user to avoid orphaned accounts.
    """
    # 1. Duplicate checks
    if admin_service.get_inspector_by_email(db, payload.email):
        error(f"An account with email '{payload.email}' already exists", "DUPLICATE_EMAIL", 409)
    if payload.employee_id and admin_service.get_inspector_by_employee_id(db, payload.employee_id):
        error(
            f"An account with employee ID '{payload.employee_id}' already exists",
            "DUPLICATE_EMPLOYEE_ID",
            409,
        )

    # 2. Create Supabase Auth user — service-role key stays on the backend
    try:
        auth_user = auth_service.create_user_with_service_role(payload.email, payload.password)
    except auth_service.UserAlreadyExistsError as exc:
        error(str(exc), "DUPLICATE_EMAIL", 409)
    except auth_service.AuthServiceError as exc:
        error(str(exc), "AUTH_SERVICE_ERROR", 502)

    auth_user_id = auth_user["id"]

    # 3. Create profile row — if this fails, clean up the auth user
    try:
        profile = admin_service.create_inspector_profile(
            db=db,
            user_id=auth_user_id,
            full_name=payload.full_name,
            email=payload.email,
            employee_id=payload.employee_id,
            department=payload.department,
            phone=payload.phone,
            role=payload.role,
            active=payload.active,
        )
    except Exception as exc:
        # 4. Rollback: delete the auth user so we don't leave orphaned accounts
        try:
            auth_service.delete_user_with_service_role(auth_user_id)
        except Exception:
            pass  # Best-effort — log in production
        error(
            f"Inspector profile creation failed after auth user was created. "
            f"Auth user has been deleted. Error: {exc}",
            "PROFILE_CREATION_FAILED",
            500,
        )

    return ok(
        data=InspectorOut.model_validate(profile).model_dump(mode="json"),
        message="Inspector created successfully",
    )


@router.get("/inspectors/{inspector_id}")
def get_inspector(
    inspector_id: str,
    _admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    profile = admin_service.get_inspector_by_id(db, inspector_id)
    if not profile:
        error("Inspector not found", "NOT_FOUND", 404)
    return ok(
        data=InspectorOut.model_validate(profile).model_dump(mode="json"),
        message="Inspector retrieved",
    )


@router.patch("/inspectors/{inspector_id}")
def update_inspector(
    inspector_id: str,
    payload: InspectorUpdate,
    _admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    profile = admin_service.get_inspector_by_id(db, inspector_id)
    if not profile:
        error("Inspector not found", "NOT_FOUND", 404)

    updates = payload.model_dump(exclude_unset=True)

    # Validate no duplicate employee_id if being changed
    if "employee_id" in updates and updates["employee_id"]:
        existing = admin_service.get_inspector_by_employee_id(db, updates["employee_id"])
        if existing and existing.id != inspector_id:
            error(
                f"An account with employee ID '{updates['employee_id']}' already exists",
                "DUPLICATE_EMPLOYEE_ID",
                409,
            )

    profile = admin_service.update_inspector_profile(db, profile, updates)
    return ok(
        data=InspectorOut.model_validate(profile).model_dump(mode="json"),
        message="Inspector updated",
    )


# ── Admin dashboard ───────────────────────────────────────────────────────────

@router.get("/dashboard")
def admin_dashboard(
    _admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    stats = admin_service.admin_dashboard_stats(db)
    return ok(data=stats, message="Admin dashboard statistics retrieved")


# ── Admin inspection list (unscoped) ─────────────────────────────────────────

@router.get("/inspections")
def list_all_inspections(
    inspector_id: str | None = Query(None, description="Filter by inspector user_id"),
    status: str | None = Query(None),
    compliance: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None),
    product_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows, total = admin_service.admin_list_inspections(
        db,
        inspector_id=inspector_id,
        status=status,
        compliance=compliance,
        date_from=date_from,
        date_to=date_to,
        search=search,
        product_type=product_type,
        page=page,
        page_size=page_size,
    )
    items = []
    for inspection, profile in rows:
        items.append(AdminInspectionOut(
            id=inspection.id,
            inspection_id=inspection.inspection_id,
            inspector_name=profile.full_name if profile else None,
            inspector_email=profile.email if profile else None,
            inspector_employee_id=profile.employee_id if profile else None,
            product_name=inspection.product_name,
            product_category=inspection.product_category,
            product_type=inspection.product_type,
            side_count=inspection.side_count,
            compliance_status=inspection.compliance_status,
            compliance_score=inspection.compliance_score,
            inspection_date=str(inspection.inspection_date) if inspection.inspection_date else None,
            created_at=inspection.created_at,
            updated_at=inspection.updated_at,
        ).model_dump(mode="json"))
    return ok(
        data={"items": items, "total": total, "page": page, "page_size": page_size},
        message="Inspections retrieved",
    )


@router.get("/inspections/{inspection_id}")
def get_inspection_detail(
    inspection_id: str,
    _admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    row = admin_service.admin_get_inspection_by_public_id(db, inspection_id)
    if not row:
        error("Inspection not found", "NOT_FOUND", 404)
    inspection, profile = row

    images = inspection_service.get_inspection_images(db, inspection.id)
    extracted = inspection_service.get_extracted_info(db, inspection.id)
    rules = inspection_service.get_compliance_results(db, inspection.id)

    return ok(
        data={
            "inspection": InspectionOut.model_validate(inspection).model_dump(mode="json"),
            "inspector": {
                "user_id": profile.user_id if profile else None,
                "full_name": profile.full_name if profile else None,
                "email": profile.email if profile else None,
                "employee_id": profile.employee_id if profile else None,
                "department": profile.department if profile else None,
            },
            "images": [
                InspectionImageOut.model_validate(img).model_copy(
                    update={"public_url": image_service.public_url(img.storage_path)}
                ).model_dump(mode="json")
                for img in images
            ],
            "extracted_info": (
                ExtractedInformationOut.model_validate(extracted).model_dump(mode="json")
                if extracted else None
            ),
            "compliance": {
                "status": inspection.compliance_status,
                "score": inspection.compliance_score,
                "rules": [
                    ComplianceRuleOut.model_validate(r).model_dump(mode="json") for r in rules
                ],
            },
        },
        message="Inspection detail retrieved",
    )


# ── Admin complaints (all, unscoped) ─────────────────────────────────────────

@router.get("/complaints")
def list_all_complaints(
    status: str | None = Query(None),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from database.models import Complaint
    from schemas.complaint import ComplaintOut
    from services import complaint_service

    items, total = admin_service.admin_list_complaints(
        db, status=status, category=category, page=page, page_size=page_size
    )
    return ok(
        data={
            "items": [
                ComplaintOut.model_validate(
                    complaint_service.complaint_response_dict(db, c)
                ).model_dump(mode="json")
                for c in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        message="Complaints retrieved",
    )
