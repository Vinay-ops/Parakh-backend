"""Shared response-formatting helpers.

Every endpoint returns the envelope:
    {"success": true,  "data": ..., "message": "..."}
Errors return:
    {"success": false, "data": None, "message": "...", "error_code": "..."}
"""
import secrets
from datetime import datetime, timezone


def ok(data=None, message: str = "OK") -> dict:
    return {"success": True, "data": data, "message": message}


def error(message: str, error_code: str, status_code: int):
    from fastapi import HTTPException

    # Raising HTTPException with the detail already in the envelope keeps the
    # exception handler in main.py simple.
    raise HTTPException(
        status_code=status_code,
        detail={"success": False, "data": None, "message": message, "error_code": error_code},
    )


def public_id(prefix: str) -> str:
    """Human-readable business identifier, e.g. INSP-7F3A9C2B."""
    return f"{prefix}-{secrets.token_hex(4).upper()}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
