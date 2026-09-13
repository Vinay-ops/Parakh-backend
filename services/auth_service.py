"""Supabase Auth integration — the ONLY authentication provider.

Flutter signs in through Supabase Auth (directly or via POST /api/auth/login,
which proxies to Supabase) and sends the resulting access token as:

    Authorization: Bearer <supabase_access_token>

Token validation strategy (P2 — eliminates per-request Supabase round-trip):
  1. Fetch Supabase's JWKS from /auth/v1/.well-known/jwks.json on first use
     and cache it in memory (refreshed every 10 minutes or on signature failure).
  2. Verify the JWT signature locally with python-jose.
  3. Fall back to the network /auth/v1/user call only if local verification
     fails (handles key rotation, malformed tokens, etc.).

The backend never issues its own JWT, never sees stored passwords, and never
keeps credentials.

No registration endpoints exist for inspectors — accounts are provisioned by
admins via the backend using the Supabase Auth Admin API (service-role key).
The service-role key NEVER leaves the backend.
"""
import logging
import os
import threading
import time as _time
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Try to import python-jose for local JWT verification.
try:
    from jose import JWTError, jwt as _jwt
    from jose.exceptions import ExpiredSignatureError

    _jose_available = True
except ImportError:
    _jose_available = False
    logger.warning(
        "python-jose not installed — falling back to remote JWT validation on every request. "
        "Install with: pip install 'python-jose[cryptography]'"
    )


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


# ---------------------------------------------------------------------------
# JWKS cache for local JWT verification
# ---------------------------------------------------------------------------

_jwks_cache: Optional[dict] = None
_jwks_fetched_at: float = 0.0
_jwks_lock = threading.Lock()
_JWKS_TTL = 600  # seconds — refresh key set every 10 minutes


def _fetch_jwks(force: bool = False) -> Optional[dict]:
    """Return cached JWKS, refreshing from Supabase if stale or forced."""
    global _jwks_cache, _jwks_fetched_at
    now = _time.monotonic()
    with _jwks_lock:
        if not force and _jwks_cache is not None and (now - _jwks_fetched_at) < _JWKS_TTL:
            return _jwks_cache
        try:
            url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
            resp = httpx.get(url, timeout=10)
            if resp.status_code == 200:
                _jwks_cache = resp.json()
                _jwks_fetched_at = now
                logger.debug("JWKS refreshed from Supabase.")
                return _jwks_cache
        except httpx.HTTPError as exc:
            logger.warning("Could not fetch JWKS: %s", exc)
        return _jwks_cache  # return stale cache if refresh fails


def _verify_jwt_locally(access_token: str) -> Optional[dict]:
    """Attempt local RS256 JWT verification using Supabase's JWKS.

    Returns the decoded claims dict on success, or None if local verification
    cannot be performed (jose not installed, no JWKS, or signature mismatch).
    On a definitive failure (expired, bad audience), raises InvalidCredentialsError.
    """
    if not _jose_available:
        return None

    jwks = _fetch_jwks()
    if not jwks:
        return None

    # Extract all public keys from the JWKS.
    keys = jwks.get("keys")
    if not keys:
        return None

    for key in keys:
        try:
            claims = _jwt.decode(
                access_token,
                key,
                algorithms=["RS256", "HS256"],
                options={"verify_aud": False},  # Supabase JWTs have no aud by default
            )
            user_id = claims.get("sub")
            email = claims.get("email")
            if not user_id:
                continue
            return {"user_id": user_id, "email": email}
        except ExpiredSignatureError:
            raise InvalidCredentialsError("Token has expired")
        except JWTError:
            # Try next key in the set.
            continue

    return None  # No key matched — caller should fall back to remote validation


def get_user_from_token(access_token: str) -> dict:
    """Validate a Supabase access token and return the authenticated user.

    Strategy:
      1. Verify locally via JWKS (fast — no network round-trip on hot path).
      2. If local verification fails (unknown key, jose not available), fall
         back to Supabase's /auth/v1/user endpoint to handle key rotation and
         edge cases. On fallback success, refresh the JWKS cache.
    """
    # --- Local verification (fast path) ---
    try:
        local_result = _verify_jwt_locally(access_token)
        if local_result is not None:
            return local_result
    except InvalidCredentialsError:
        raise  # Expired / definitively invalid — no point hitting the network.

    # --- Remote fallback ---
    logger.debug("Local JWT verification inconclusive — falling back to Supabase /auth/v1/user")

    url = f"{SUPABASE_URL}/auth/v1/user"
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

    # Remote validation succeeded — the JWKS may have been rotated; refresh cache.
    _fetch_jwks(force=True)

    data = resp.json()
    return {"user_id": data["id"], "email": data.get("email")}


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
