import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from database.database import get_db
from middleware.authentication import get_current_user
from services import image_service, inspection_service, ml_service
from utils.helpers import error, ok

router = APIRouter(prefix="/api", tags=["scan"])

# The ML call is isolated to services/ml_service.process_image. When the ML
# team implements it, this endpoint's flow and the Flutter API stay unchanged:
# upload -> validate -> store -> inspection record -> ML -> persist results.


@router.post("/scan")
async def scan(
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

    image_url = image_service.store_image(user_id, bytes(data), extension)

    inspection = inspection_service.create_inspection_for_scan(
        db, user_id, product_name, product_category, image_url
    )

    # --- ML pipeline boundary: everything below is the ML team's slot. ---
    # The stored image is materialised to a local path for the ML pipeline.
    # process_image raises NotImplementedError until the model is integrated,
    # in which case the inspection stays in PENDING_ML and the app shows the
    # "processing" state until the backend is upgraded.
    ml_pending = True
    local_path = Path(tempfile.gettempdir()) / f"parakh_{inspection.id}{extension}"
    local_path.write_bytes(data)
    try:
        raw_result = ml_service.process_image(str(local_path))
        ml_result = ml_service.validate_result(raw_result)
        inspection = inspection_service.apply_ml_result(db, inspection, ml_result)
        ml_pending = False
    except ml_service.MLNotIntegratedError:
        pass
    finally:
        local_path.unlink(missing_ok=True)

    return ok(
        data={
            "inspection_id": inspection.inspection_id,
            "image_url": inspection.product_image_url,
            "status": inspection.compliance_status,
            "ml_pending": ml_pending,
        },
        message=(
            "Image stored and inspection created. ML processing pending integration."
            if ml_pending
            else "Inspection completed."
        ),
    )