import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from database.database import SessionLocal, get_db
from middleware.authentication import get_current_user
from services import image_service, inspection_service, ml_service
from database.models import Inspection, VALID_SIDES
from utils.helpers import error, ok

router = APIRouter(prefix="/api", tags=["scan"])

# The ML call is isolated to services/ml_service.process_image. When the ML
# team implements it, this endpoint's flow and the Flutter API stay unchanged:
# upload -> validate -> store -> inspection record -> ML -> persist results.


def _process_scan_in_background(
    inspection_id: str,
    image_bytes: bytes,
    extension: str,
) -> None:
    """Run legacy single-image ML after the upload response is sent."""
    db = SessionLocal()
    local_path = Path(tempfile.gettempdir()) / f"parakh_{inspection_id}{extension}"
    try:
        inspection = db.query(Inspection).filter(
            Inspection.inspection_id == inspection_id
        ).first()
        if inspection is None:
            return

        inspection.compliance_status = "PROCESSING"
        db.commit()
        local_path.write_bytes(image_bytes)
        raw_result = ml_service.process_inspection(
            inspection_id,
            [("front", str(local_path))],
        )
        ml_result = ml_service.validate_result(raw_result)
        inspection_service.apply_ml_result(db, inspection, ml_result)
    except ml_service.MLNotIntegratedError:
        inspection.compliance_status = "PENDING_ML"
        db.commit()
    except Exception:
        db.rollback()
        inspection = db.query(Inspection).filter(
            Inspection.inspection_id == inspection_id
        ).first()
        if inspection is not None:
            inspection.compliance_status = "FAILED"
            db.commit()
    finally:
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
    user_id = user["user_id"]

    declared_type = (image.content_type or "").lower().split(";")[0].strip()

    # Read in bounded chunks so an oversized body is rejected before it is
    # fully buffered into memory.
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

    inspection = inspection_service.create_inspection_for_scan(
        db, user_id, product_name, product_category, image_url
    )
    inspection.compliance_status = "PENDING_ML"
    db.commit()
    db.refresh(inspection)

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
