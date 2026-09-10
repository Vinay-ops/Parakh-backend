"""Supabase Storage image storage.

Production uses Supabase Storage exclusively. Images are uploaded with the
backend service-role credentials into the configured public bucket. There is
no local filesystem fallback and no unauthenticated /uploads route.

The service-role key lives only on the backend; it is never returned to
clients and never exposed to Flutter.
"""
import os
import secrets

import httpx
from dotenv import load_dotenv

load_dotenv()

ALLOWED_CONTENT_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MIME_BY_EXTENSION = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

MAX_IMAGE_SIZE_MB = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "product-images")


class ImageValidationError(Exception):
    def __init__(self, message: str, error_code: str = "INVALID_IMAGE"):
        super().__init__(message)
        self.error_code = error_code


def _detect_image_type(data: bytes) -> str | None:
    """Sniff magic bytes; returns the matching file extension or None."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def validate_image(content_type: str, data: bytes) -> str:
    """Validate declared content type, size, and actual image content."""
    ext = ALLOWED_CONTENT_TYPES.get((content_type or "").lower())
    if ext is None:
        raise ImageValidationError(
            "Unsupported image type. Allowed: JPEG, PNG, WebP.", "UNSUPPORTED_IMAGE_TYPE"
        )
    if len(data) == 0:
        raise ImageValidationError("Empty file.", "EMPTY_FILE")
    if len(data) > MAX_IMAGE_SIZE_BYTES:
        raise ImageValidationError(
            f"Image exceeds the {MAX_IMAGE_SIZE_MB} MB limit.", "IMAGE_TOO_LARGE"
        )
    if _detect_image_type(data) != ext:
        raise ImageValidationError(
            "File content does not match its declared image type.", "INVALID_IMAGE"
        )
    return ext


def _storage_headers() -> dict:
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        raise ImageValidationError("Supabase Storage is not configured.", "STORAGE_ERROR")
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }


def store_image(user_id: str, data: bytes, extension: str) -> str:
    """Upload an image under a random path and return that internal path."""
    filename = f"{secrets.token_hex(16)}{extension}"
    path = f"{user_id}/{filename}"
    return store_image_at_path(user_id, data, extension, path)


def store_image_at_path(user_id: str, data: bytes, extension: str, storage_path: str) -> str:
    """Upload the image to Supabase Storage and return its internal path.

    Using a deterministic path (e.g. inspections/{inspection_id}/{side}.jpg)
    means uploading the same side again overwrites the previous file in Storage,
    consistent with the upsert behaviour in the database.
    """
    headers = _storage_headers()
    mime = MIME_BY_EXTENSION.get(extension, "application/octet-stream")
    headers["Content-Type"] = mime

    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{storage_path}"
    try:
        resp = httpx.put(url, content=data, headers=headers, timeout=30)
    except httpx.HTTPError as exc:
        raise ImageValidationError(
            "Failed to upload image to Supabase Storage.", "STORAGE_ERROR"
        ) from exc

    if resp.status_code not in (200, 201):
        # If bucket doesn't exist (404/400), give a clear error.
        if resp.status_code in (400, 404):
            raise ImageValidationError(
                f"Supabase Storage bucket '{SUPABASE_STORAGE_BUCKET}' does not exist or is "
                "inaccessible. Create the bucket in the Supabase dashboard before uploading.",
                "STORAGE_BUCKET_MISSING",
            )
        raise ImageValidationError(
            f"Failed to upload image to Supabase Storage (HTTP {resp.status_code}).",
            "STORAGE_ERROR",
        )

    return storage_path


def public_url(storage_path: str) -> str:
    """Return the public URL for an object in the configured public bucket."""
    if not SUPABASE_URL:
        raise ImageValidationError("Supabase Storage is not configured.", "STORAGE_ERROR")
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{storage_path}"


def download_image(storage_path: str) -> bytes:
    """Download image bytes from Supabase Storage (for ML pipeline)."""
    headers = _storage_headers()
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{storage_path}"
    try:
        resp = httpx.get(url, headers=headers, timeout=30)
    except httpx.HTTPError as exc:
        raise ImageValidationError(
            "Failed to download image from Supabase Storage.", "STORAGE_ERROR"
        ) from exc
    if resp.status_code != 200:
        raise ImageValidationError(
            f"Failed to download image from Supabase Storage (HTTP {resp.status_code}).",
            "STORAGE_ERROR",
        )
    return resp.content
