from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/api/users", tags=["users"])


class UserDocResponse(BaseModel):
    id: str
    data: dict[str, Any]
    exists: bool


@router.get("/{user_id}")
def get_user_doc(
    user_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    if user_id != current_user.id:
        return UserDocResponse(id=user_id, data={}, exists=False)

    return UserDocResponse(
        id=current_user.id,
        data={
            "name": current_user.name,
            "email": current_user.email,
            "adm": current_user.adm,
            "createdAt": current_user.created_at.isoformat() + "Z",
        },
        exists=True,
    )
