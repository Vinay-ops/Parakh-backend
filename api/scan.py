"""Legacy single-image scan endpoint — thin wrapper around the multi-side flow.

POST /api/scan is kept for backwards-compatibility with existing Flutter callers
that use the single-image path. Internally it delegates entirely to the same
inspection-creation, image-upload, and ML-processing logic used by the multi-side
flow (POST /api/inspections → images → process).

This means:
  - All ML processing, error handling, and status transitions live in one place.
  - Any improvement to the multi-side flow is automatically picked up here.
  - When the legacy endpoint is retired it can be removed without touching ML code.
"""
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from database.database import SessionLocal, get_db
from database.models import Inspection, VALID_SIDES
from middleware.authentication import get_current_user
from services import image_service, inspection_service, ml_service
from utils.helpers import error, ok

router = APIRouter(prefix="/api", tags=["scan"])


def _process_scan_in_background(
    inspection_id: str,
    image_bytes: bytes,
    extension: str,
) -> None:
    """Run single-image ML processing after the upload response is sent.

    Opens its own DB session because FastAPI's request-scoped session is
    closed before background tasks execute. The session is always closed in
    the finally block regardless of success or failure.
    """
    db = SessionLocal()
    local_path: Path | None = None
    try:
        inspection = db.query(Inspection).filter(
            Inspection.inspection_id == inspection_id
        ).first()
        if inspection is None:
            return

        inspection.compliance_status = "PROCESSING"
        db.commit()

        # Write to a non-predictable temp file so different in-flight scans
        # don't race on the same path.
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
            local_path = Path(tmp.name)
        local_path.write_bytes(image_bytes)

        raw_result = ml_service.process_inspection(
            inspection_id,
            [("front", str(local_path))],
        )
        ml_result = ml_service.validate_result(raw_result)
        inspection_service.apply_ml_result(db, inspection, ml_result)

    except ml_service.MLNotIntegratedError:
        if inspection is not None:
            inspection.compliance_status = "PENDING_ML"
            db.commit()
    except Exception:
        db.rollback()
        # Re-fetch after rollback — the session state is invalid after rollback
        # so we need a fresh query.
        inspection = db.query(Inspection).filter(
            Inspection.inspection_id == inspection_id
        ).first()
        if inspection is not None:
            inspection.compliance_status = "FAILED"
            db.commit()
    finally:
        if local_path is not None:
            local_path.unlink(missing_ok=True)
        db.close()


@router.post("/scan")
async def scan(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    product_name: str | None = Form(None),
    product_category: str | None = Form(None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Legacy single-image scan.

    Accepts an image upload and optional product metadata, creates an
    inspection record (side_count=1), stores the image, and queues ML
    processing in the background.  Callers should poll
    GET /api/inspections/{inspection_id} for the final compliance status.
    """
    user_id = user["user_id"]

    declared_type = (image.content_type or "").lower().split(";")[0].strip()

    # Stream in bounded chunks — reject oversized images before fully buffering.
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

    storage_path = image_service.store_image(user_id, bytes(data), extension)
    image_url = image_service.public_url(storage_path)

    # Create a 1-sided inspection so it shares the same status machine as
    # multi-side inspections.
    inspection = inspection_service.create_inspection_record(
        db,
        user_id,
        product_name,
        product_category,
        image_url=image_url,
        side_count=1,
    )
    inspection.compliance_status = "PENDING_ML"
    db.commit()

    background_tasks.add_task(
        _process_scan_in_background,
        inspection.inspection_id,
        bytes(data),
        extension,
    )

    return ok(
        data={
            "inspection_id": inspection.inspection_id,
            "image_url": inspection.product_image_url,
            "status": inspection.compliance_status,
            "ml_pending": True,
        },
        message="Image stored and ML processing started.",
    )
