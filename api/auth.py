from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from middleware.authentication import get_current_user
from schemas.auth import LoginRequest
from services import auth_service
from utils.helpers import error, ok

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Rate limiter — shared instance from app.state (set in main.py).
# Using a module-level Limiter with the same key_func so the decorator
# resolves correctly regardless of import order.
_limiter = Limiter(key_func=get_remote_address)

# LOGIN ONLY — there is intentionally no signup/registration endpoint.
# Accounts are provisioned in Supabase Auth (dashboard or API).


@router.post("/login")
@_limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest):
    """Proxy login to Supabase Auth and return the Supabase session token.

    Rate-limited to 10 requests per minute per IP to prevent brute-force
    attacks against inspector accounts.
    """
    try:
        result = auth_service.authenticate(payload.email, payload.password)
    except auth_service.InvalidCredentialsError:
        error("Invalid email or password", "INVALID_CREDENTIALS", 401)
    return ok(data=result, message="Login successful")


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    """Return the authenticated user derived from the Supabase access token."""
    return ok(
        data={"user_id": user["user_id"], "email": user.get("email")},
        message="Authenticated",
    )