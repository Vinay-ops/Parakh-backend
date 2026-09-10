from fastapi import APIRouter, Depends

from middleware.authentication import get_current_user
from schemas.auth import LoginRequest
from services import auth_service
from utils.helpers import error, ok

router = APIRouter(prefix="/api/auth", tags=["auth"])

# LOGIN ONLY — there is intentionally no signup/registration endpoint.
# Accounts are provisioned in Supabase Auth (dashboard or API).


@router.post("/login")
def login(payload: LoginRequest):
    """Proxy login to Supabase Auth and return the Supabase session token."""
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