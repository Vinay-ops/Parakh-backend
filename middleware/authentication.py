"""Authorization dependencies for protected endpoints.

The authenticated user id always comes from the validated Supabase access
token — never from request bodies or query parameters — so cross-user access
is impossible by construction.

get_current_user   → any authenticated user
get_current_admin  → authenticated user whose profiles.role == 'admin'
                     (role is read from the DB, never trusted from the token)
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database.database import get_db
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


def get_current_admin(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Verify the authenticated user has the 'admin' role.

    Role is determined by reading profiles.role from the database.
    The frontend cannot influence this check.
    """
    from database.models import Profile
    from utils.helpers import error

    profile = db.query(Profile).filter(Profile.user_id == user["user_id"]).first()
    if not profile or profile.role != "admin":
        error("Admin access required", "FORBIDDEN", 403)
    return user
