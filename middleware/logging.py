"""Structured request logging middleware (A3).

Logs every HTTP request with:
  - request_id: a short random hex ID for correlation across log lines
  - method and path
  - status code
  - duration in milliseconds
  - user_id: extracted from the Bearer token's sub claim when available
    (JWT is decoded without signature verification here — we just want the
     subject for log correlation; auth enforcement is in authentication.py)
  - inspection_id: extracted from the URL path when present

Log format is structured key=value so it can be parsed by Render's log drain
or any structured-log aggregator without a custom parser.

Example output:
  INFO parakh.request request_id=a3f9c21b method=POST path=/api/inspections/INSP-ABC/process
    status=200 duration_ms=312.4 user_id=uuid-... inspection_id=INSP-ABC
"""
import logging
import re
import secrets
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("parakh.request")

# Regex to pull the inspection public ID out of the URL path
_INSPECTION_ID_RE = re.compile(r"/inspections/([A-Z]+-[A-F0-9]+)", re.IGNORECASE)


def _extract_user_id(request: Request) -> str | None:
    """Extract the user_id from the Bearer token subject claim without full verification.

    We parse the JWT payload (base64 middle segment) without signature
    verification — the purpose here is log correlation only, not auth.
    Auth enforcement is done by get_current_user() in authentication.py.
    """
    try:
        auth = request.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1]
        # JWT is header.payload.signature — decode the payload segment.
        import base64
        import json

        payload_b64 = token.split(".")[1]
        # Add padding so base64 doesn't choke on unpadded strings.
        padding = 4 - len(payload_b64) % 4
        payload_b64 += "=" * (padding % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("sub")
    except Exception:
        return None


def _extract_inspection_id(path: str) -> str | None:
    m = _INSPECTION_ID_RE.search(path)
    return m.group(1) if m else None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = secrets.token_hex(4)
        start = time.perf_counter()

        user_id = _extract_user_id(request)
        inspection_id = _extract_inspection_id(request.url.path)

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000

        # Build a structured log line as key=value pairs.
        parts = [
            f"request_id={request_id}",
            f"method={request.method}",
            f"path={request.url.path}",
            f"status={response.status_code}",
            f"duration_ms={duration_ms:.1f}",
        ]
        if user_id:
            parts.append(f"user_id={user_id}")
        if inspection_id:
            parts.append(f"inspection_id={inspection_id}")

        level = logging.WARNING if response.status_code >= 500 else logging.INFO
        logger.log(level, " ".join(parts))

        # Propagate the request_id to the client for support correlation.
        response.headers["X-Request-ID"] = request_id
        return response
