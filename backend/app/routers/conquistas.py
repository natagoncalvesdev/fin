from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import cofrinhos_service, conquistas_service, saude_service
from app.auth import get_current_user
from app.database import get_db
from app.models import Usuario

router = APIRouter(prefix="/api/conquistas", tags=["conquistas"])


@router.get("")
def list_conquistas(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    # Concede medalhas pendentes antes de listar (marcos de peso, metas já
    # batidas, cofrinhos já cheios) — cobre dados criados antes desta feature.
    mudou = saude_service.sincronizar(db, current_user)
    mudou = cofrinhos_service.sincronizar_todos(db, current_user) or mudou
    if mudou:
        db.commit()
    return conquistas_service.listar(db, current_user)
