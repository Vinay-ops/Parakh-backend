import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api import admin, auth, complaints, dashboard, inspections, profile, scan
from database.database import engine

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

# CORS: optional, configurable via ALLOWED_ORIGINS (comma-separated exact
# origins). Mobile (Flutter) clients do not need CORS, so no middleware is
# added when the variable is unset.
allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
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