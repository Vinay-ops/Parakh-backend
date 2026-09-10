"""Authorization dependency for every protected endpoint.

The authenticated user id always comes from the validated Supabase access
token — never from request bodies or query parameters — so cross-user access
is impossible by construction.
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services import auth_service

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    from utils.helpers import error

    if credentials is None or credentials.scheme.lower() != "bearer":
        error("Missing or invalid Authorization header", "UNAUTHORIZED", 401)
    try:
        return auth_service.get_user_from_token(credentials.credentials)
    except auth_service.InvalidCredentialsError:
        error("Invalid or expired token", "UNAUTHORIZED", 401)