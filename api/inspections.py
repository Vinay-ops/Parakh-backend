import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import VALID_SIDES
from middleware.authentication import get_current_user
from schemas.inspection import (
    ComplianceRuleOut,
    ExtractedInformationOut,
    ExtractedInformationUpdate,
    InspectionCreate,
    InspectionImageOut,
    InspectionOut,
)
from services import image_service, inspection_service, ml_service
from utils.helpers import error, ok

router = APIRouter(prefix="/api/inspections", tags=["inspections"])


def _required_sides(side_count: int) -> tuple[str, ...]:
    return VALID_SIDES[:side_count]


def _image_out(image):
    return InspectionImageOut.model_validate(image).model_copy(
        update={"public_url": image_service.public_url(image.storage_path)}
    ).model_dump(mode="json")


@router.post("")
def create_inspection(
    payload: InspectionCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an inspection record — entry point for the multi-side scan flow.

    Call this first, then POST per-side images to
    /api/inspections/{id}/images, then POST /api/inspections/{id}/process.
    """
    inspection = inspection_service.create_inspection_record(
        db,
        user["user_id"],
        payload.product_name,
        payload.product_category,
        product_type=payload.product_type,
        side_count=payload.side_count,
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


@router.post("/{inspection_id}/images")
async def upload_inspection_image(
    inspection_id: str,
    image: UploadFile = File(...),
    side: str = Form(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload one side image for an existing inspection.

    `side` must be one of: front, back, left, right.
    Uploading a side that was already captured replaces the previous image
    (upsert on (inspection_id, side)).
    """
    inspection = inspection_service.get_by_public_id(db, user["user_id"], inspection_id)
    if not inspection:
        error("Inspection not found", "NOT_FOUND", 404)

    side = side.lower().strip()
    if side not in _required_sides(inspection.side_count):
        error(
            f"Invalid side '{side}' for this inspection.",
            "INVALID_SIDE",
            422,
        )

    declared_type = (image.content_type or "").lower().split(";")[0].strip()

    data = bytearray()
    while True:
        chunk = await image.read(64 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > image_service.MAX_IMAGE_SIZE_BYTES:
            error(
                f"Image exceeds the {image_service.MAX_IMAGE_SIZE_MB} MB limit.",
                "IMAGE_TOO_LARGE",
                400,
            )

    try:
        extension = image_service.validate_image(declared_type, bytes(data))
    except image_service.ImageValidationError as exc:
        error(str(exc), exc.error_code, 400)

    # Use a deterministic path so retaking a side overwrites the previous file.
    storage_path = f"inspections/{inspection.id}/{side}{extension}"
    image_service.store_image_at_path(user["user_id"], bytes(data), extension, storage_path)

    img_record = inspection_service.upsert_inspection_image(
        db=db,
        inspection_id=inspection.id,
        side=side,
        side_order=_required_sides(inspection.side_count).index(side) + 1,
        storage_path=storage_path,
        public_url=image_service.public_url(storage_path),
        mime_type=declared_type or f"image/{extension.lstrip('.')}",
        file_size=len(data),
    )

    inspection.compliance_status = "CAPTURING"
    db.commit()

    return ok(
        data=_image_out(img_record),
        message=f"Side '{side}' image uploaded",
    )


@router.get("/{inspection_id}/images")
def list_inspection_images(
    inspection_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all uploaded side images for an inspection."""
    inspection = inspection_service.get_by_public_id(db, user["user_id"], inspection_id)
    if not inspection:
        error("Inspection not found", "NOT_FOUND", 404)
    images = inspection_service.get_inspection_images(db, inspection.id)
    return ok(
        data=[_image_out(i) for i in images],
        message="Images retrieved",
    )


@router.post("/{inspection_id}/process")
def process_inspection(
    inspection_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger ML processing for an inspection that has all images uploaded.

    The ML call is synchronous in the current architecture. Until the ML model
    is integrated, the inspection stays in PENDING_ML and the client polls
    GET /api/inspections/{id} for status changes.
    """
    inspection = inspection_service.get_by_public_id(db, user["user_id"], inspection_id)
    if not inspection:
        error("Inspection not found", "NOT_FOUND", 404)

    images = inspection_service.get_inspection_images(db, inspection.id)
    required_sides = set(_required_sides(inspection.side_count))
    captured_sides = {image.side for image in images}
    if captured_sides != required_sides:
        missing = ", ".join(sorted(required_sides - captured_sides))
        error(f"All required sides must be uploaded before processing. Missing: {missing}", "INCOMPLETE_CAPTURE", 422)

    inspection.compliance_status = "PROCESSING"
    db.commit()

    # Build a list of (side, local_temp_path) pairs for the ML service.
    ml_pending = True
    try:
        side_paths: list[tuple[str, str]] = []
        tmp_files: list[Path] = []
        for img in images:
            # Download image bytes from Supabase Storage for the ML pipeline.
            img_bytes = image_service.download_image(img.storage_path)
            ext = Path(img.storage_path).suffix or ".jpg"
            tmp = Path(tempfile.gettempdir()) / f"parakh_{inspection.id}_{img.side}{ext}"
            tmp.write_bytes(img_bytes)
            tmp_files.append(tmp)
            side_paths.append((img.side, str(tmp)))

        try:
            raw_result = ml_service.process_inspection(inspection.inspection_id, side_paths)
            ml_result = ml_service.validate_result(raw_result)
            inspection = inspection_service.apply_ml_result(db, inspection, ml_result)
            ml_pending = False
        except ml_service.MLNotIntegratedError:
            inspection.compliance_status = "PENDING_ML"
            db.commit()
        except ValueError as exc:
            # ML pipeline raised a recoverable error (image decode, OCR failure, etc.)
            # Mark the inspection FAILED so the client knows processing did not succeed.
            import logging as _logging
            _logging.getLogger(__name__).error(
                "ML pipeline error for %s: %s", inspection_id, exc
            )
            inspection.compliance_status = "FAILED"
            db.commit()
            error(str(exc), "ML_PIPELINE_ERROR", 422)
    except image_service.ImageValidationError as exc:
        inspection.compliance_status = "FAILED"
        db.commit()
        error(str(exc), exc.error_code, 502)
    finally:
        for tmp in tmp_files:
            tmp.unlink(missing_ok=True)

    return ok(
        data={
            "inspection_id": inspection.inspection_id,
            "status": inspection.compliance_status,
            "ml_pending": ml_pending,
        },
        message=(
            "ML processing pending integration."
            if ml_pending
            else "Inspection processed."
        ),
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
