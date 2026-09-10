"""Supabase Auth integration — the ONLY authentication provider.

Flutter signs in through Supabase Auth (directly or via POST /api/auth/login,
which proxies to Supabase) and sends the resulting access token as:

    Authorization: Bearer <supabase_access_token>

The backend validates that token with Supabase's /auth/v1/user endpoint and
derives the authenticated user id from the response. The backend never issues
its own JWT, never sees stored passwords, and never keeps credentials.

No registration endpoints exist for inspectors — accounts are provisioned by
admins via the backend using the Supabase Auth Admin API (service-role key).
The service-role key NEVER leaves the backend.
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


class InvalidCredentialsError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    pass


class AuthServiceError(Exception):
    pass


def _anon_headers() -> dict:
    return {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}


def _service_role_headers() -> dict:
    """Headers using the service-role key — ONLY for server-side admin operations."""
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def sign_in_with_password(email: str, password: str) -> dict:
    """Exchange email/password for a Supabase Auth session."""
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    try:
        resp = httpx.post(
            url,
            json={"email": email, "password": password},
            headers=_anon_headers(),
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise InvalidCredentialsError("Authentication service unavailable") from exc
    if resp.status_code != 200:
        raise InvalidCredentialsError("Invalid email or password")
    return resp.json()


def get_user_from_token(access_token: str) -> dict:
    """Validate a Supabase access token and return the authenticated user.

    Verification is delegated to Supabase Auth itself (GET /auth/v1/user), so
    the backend never needs to manage JWT signing secrets.
    """
    url = f"{SUPABASE_URL}/auth/v1/user"
    # Token validation is a backend operation. Prefer the service-role key so
    # validation does not fail when the public anon key has been rotated, while
    # keeping the credential entirely inside the backend process.
    api_keys = [key for key in (SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY) if key]
    if not api_keys:
        raise InvalidCredentialsError("Authentication service is not configured")
    try:
        resp = None
        for api_key in api_keys:
            resp = httpx.get(
                url,
                headers={
                    "apikey": api_key,
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                break
    except httpx.HTTPError as exc:
        raise InvalidCredentialsError("Authentication service unavailable") from exc
    if resp is None or resp.status_code != 200:
        raise InvalidCredentialsError("Invalid or expired token")
    data = resp.json()
    return {"user_id": data["id"], "email": data.get("email")}


def authenticate(email: str, password: str) -> dict:
    """Login proxy: verify credentials against Supabase Auth, return the session."""
    session = sign_in_with_password(email, password)
    user = session["user"]
    return {
        "access_token": session["access_token"],
        "refresh_token": session.get("refresh_token"),
        "expires_in": session.get("expires_in"),
        "token_type": "bearer",
        "user_id": user["id"],
        "email": user.get("email"),
    }


def create_user_with_service_role(email: str, password: str) -> dict:
    """Create a new Supabase Auth user using the Admin API (service-role key).

    This function MUST ONLY be called from the backend. The service-role key
    is never exposed to the browser.

    Returns the created user dict: {"id", "email", ...}
    Raises:
        UserAlreadyExistsError: if a user with that email already exists.
        AuthServiceError: on any other Supabase error.
    """
    url = f"{SUPABASE_URL}/auth/v1/admin/users"
    try:
        resp = httpx.post(
            url,
            json={
                "email": email,
                "password": password,
                "email_confirm": True,  # Auto-confirm so inspector can log in immediately
            },
            headers=_service_role_headers(),
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise AuthServiceError(f"Auth service unavailable: {exc}") from exc

    if resp.status_code == 422:
        body = resp.json()
        msg = body.get("msg") or body.get("message") or str(body)
        if "already" in msg.lower() or "duplicate" in msg.lower() or "exists" in msg.lower():
            raise UserAlreadyExistsError(f"A user with email '{email}' already exists")
        raise AuthServiceError(f"Supabase validation error: {msg}")

    if resp.status_code not in (200, 201):
        body = resp.json()
        msg = body.get("msg") or body.get("message") or body.get("error_description") or str(body)
        if "already registered" in msg.lower() or "already exists" in msg.lower():
            raise UserAlreadyExistsError(f"A user with email '{email}' already exists")
        raise AuthServiceError(f"Failed to create user: {msg}")

    return resp.json()


def delete_user_with_service_role(user_id: str) -> None:
    """Delete a Supabase Auth user by ID — used for rollback on partial failures.

    MUST ONLY be called from the backend.
    """
    url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    try:
        resp = httpx.delete(url, headers=_service_role_headers(), timeout=15)
    except httpx.HTTPError as exc:
        raise AuthServiceError(f"Auth service unavailable: {exc}") from exc
    if resp.status_code not in (200, 204):
        raise AuthServiceError(f"Failed to delete user {user_id}: {resp.text}")
