"""Supabase Auth integration — the ONLY authentication provider.

Flutter signs in through Supabase Auth (directly or via POST /api/auth/login,
which proxies to Supabase) and sends the resulting access token as:

    Authorization: Bearer <supabase_access_token>

The backend validates that token with Supabase's /auth/v1/user endpoint and
derives the authenticated user id from the response. The backend never issues
its own JWT, never sees stored passwords, and never keeps credentials.

No registration endpoints exist — accounts are provisioned in Supabase Auth.
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


class InvalidCredentialsError(Exception):
    pass


def _auth_headers() -> dict:
    return {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}


def sign_in_with_password(email: str, password: str) -> dict:
    """Exchange email/password for a Supabase Auth session."""
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    try:
        resp = httpx.post(
            url,
            json={"email": email, "password": password},
            headers=_auth_headers(),
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
    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"}
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
    except httpx.HTTPError as exc:
        raise InvalidCredentialsError("Authentication service unavailable") from exc
    if resp.status_code != 200:
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