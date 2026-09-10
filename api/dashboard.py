from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.database import get_db
from middleware.authentication import get_current_user
from services import inspection_service
from utils.helpers import ok

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    # All statistics are computed on the backend, scoped to the token's user.
    return ok(data=inspection_service.dashboard_stats(db, user["user_id"]),
              message="Dashboard statistics retrieved")
