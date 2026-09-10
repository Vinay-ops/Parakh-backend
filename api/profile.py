from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Profile
from middleware.authentication import get_current_user
from schemas.profile import ProfileOut, ProfileUpdate
from utils.helpers import ok

router = APIRouter(prefix="/api/profile", tags=["profile"])


def get_or_create_profile(db: Session, user_id: str, email: str | None = None) -> Profile:
    """Return the profile for the given user, creating it if it does not exist.

    `email` is the address from the validated Supabase token.  It is written
    on creation and kept in sync on every subsequent fetch so that the profile
    always reflects the current Supabase Auth email.  The client cannot set
    this field (it is not in ProfileUpdate).
    """
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not profile:
        profile = Profile(user_id=user_id, email=email)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    elif email and profile.email != email:
        # Keep in sync if the Supabase email has changed.
        profile.email = email
        db.commit()
        db.refresh(profile)
    return profile


@router.get("")
def get_profile(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = get_or_create_profile(db, user["user_id"], email=user.get("email"))
    return ok(data=ProfileOut.model_validate(profile).model_dump(mode="json"),
              message="Profile retrieved")


@router.patch("")
def update_profile(
    payload: ProfileUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = get_or_create_profile(db, user["user_id"], email=user.get("email"))
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return ok(data=ProfileOut.model_validate(profile).model_dump(mode="json"),
              message="Profile updated")
