import os

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text

from api import admin, auth, complaints, dashboard, inspections, profile, scan
from database.database import engine
from middleware.logging import RequestLoggingMiddleware
from middleware.security import SecurityHeadersMiddleware

load_dotenv()

REQUIRED_ENV = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "DATABASE_URL",
)


def _validate_config() -> None:
    """Fail fast when required production configuration is missing.

    There is intentionally no silent fallback to SQLite or local storage:
    the deployment must be configured explicitly.
    """
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Refusing to start."
        )


def _build_allowed_origins() -> list[str]:
    """Build the CORS allowed-origins list from environment configuration.

    ALLOWED_ORIGINS is a comma-separated list of exact origins (no wildcards).
    Localhost variants are appended only in development mode so the dev server
    works without touching production config.

    Preview deployments on Vercel are NOT used for this project, so a single
    fixed production origin is sufficient. If preview deployments are ever
    enabled, replace this with a custom allow_origin_regex or a
    CORSMiddleware subclass that does pattern matching against the Vercel
    preview URL pattern (e.g. https://parakh-web-sih-*.vercel.app).
    """
    raw = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    dev_origins: list[str] = []
    if os.getenv("ENVIRONMENT", "production").lower() == "development":
        dev_origins = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
    # Deduplicate while preserving order (production origins first).
    return list(dict.fromkeys(raw + dev_origins))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_config()
    yield
    engine.dispose()


app = FastAPI(
    title="Parakh Backend",
    version="2.0.0",
    description=(
        "Backend for the Parakh product-label inspection app. "
        "Authentication (Supabase Auth) and storage (Supabase Storage) are "
        "provided by Supabase; ML/OCR integration is a defined interface only "
        "(see docs/ML_INTEGRATION.md)."
    ),
    lifespan=lifespan,
)

# Rate limiter (S2) — limits per-IP using the client's remote address.
# The limiter instance is shared with routers via app.state.
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware registration order ─────────────────────────────────────────────
# Starlette applies middleware in REVERSE registration order: the LAST
# add_middleware() call produces the OUTERMOST layer (runs first on every
# inbound request, last on every outbound response).
#
# Execution order (outermost → innermost):
#   1. CORSMiddleware          — outermost. Intercepts OPTIONS preflight
#                                requests and short-circuits them with 200 +
#                                CORS headers before they reach any route
#                                handler, rate limiter, or body validator.
#                                Must be registered LAST so it runs FIRST.
#   2. RequestLoggingMiddleware — logs after CORS decides; the logged status
#                                 code reflects the actual response (200 for
#                                 a well-formed preflight, not a false 400).
#   3. SecurityHeadersMiddleware — innermost; stamps security headers onto
#                                  the response returned by the route handler.
#
# Root cause of the OPTIONS 400 (Bug 3 — documented here for posterity):
#   Starlette's CORSMiddleware only short-circuits a preflight when the
#   request's Origin is present in allow_origins. Before Bug 1 was fixed,
#   ALLOWED_ORIGINS contained only https://parakh-web.onrender.com while the
#   real admin web lives at https://parakh-web-sih.vercel.app. Because the
#   origin didn't match, CORSMiddleware passed the OPTIONS request through to
#   the POST /api/auth/login handler. That handler has a required Pydantic
#   body (LoginRequest), so the empty OPTIONS body triggered a 400 validation
#   error. The primary fix is the correct ALLOWED_ORIGINS value (Bug 1).
#   The middleware order below is already correct and has not changed.

app.add_middleware(SecurityHeadersMiddleware)   # registered 1st → runs LAST (innermost)
app.add_middleware(RequestLoggingMiddleware)    # registered 2nd → runs 2nd
app.add_middleware(                            # registered LAST → runs FIRST (outermost)
    CORSMiddleware,
    allow_origins=_build_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],   # includes OPTIONS — required for preflight handling
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(scan.router)
app.include_router(inspections.router)
app.include_router(complaints.router)
app.include_router(dashboard.router)
app.include_router(profile.router)


@app.get("/api/health", tags=["health"])
def health():
    """Liveness + database connectivity check."""
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    if not db_ok:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "data": {"status": "degraded", "database": "unreachable"},
                "message": "Database unreachable",
                "error_code": "DB_UNAVAILABLE",
            },
        )
    from utils.helpers import ok
    return ok(data={"status": "ok", "database": "connected"}, message="OK")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = ".".join(str(part) for part in first.get("loc", []))
    detail = first.get("msg", "Invalid request")
    message = f"Validation error: {loc}: {detail}" if loc else f"Validation error: {detail}"
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "message": message,
            "error_code": "VALIDATION_ERROR",
        },
    )


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "success" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "message": str(exc.detail),
            "error_code": f"HTTP_{exc.status_code}",
        },
    )


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak stack traces or internal configuration to clients.
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "message": "Internal server error",
            "error_code": "INTERNAL_ERROR",
        },
    )
