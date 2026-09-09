from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import usuarios_service
from app.auth import get_current_user
from app.database import get_db
from app.models import Usuario
from app.rate_limit import busca_limiter

router = APIRouter(prefix="/api/users", tags=["users"])


class UserDocResponse(BaseModel):
    id: str
    data: dict[str, Any]
    exists: bool


class UsuarioMini(BaseModel):
    id: str
    nome: str
    # Só uma dica ("an***@gmail.com"), não o e-mail inteiro — senão qualquer
    # usuário logado consegue raspar a base de e-mails buscando trechos de nome.
    emailDica: str


@router.get("/buscar", response_model=list[UsuarioMini])
def buscar_usuarios(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    q: str = Query(min_length=3, max_length=120),
):
    """Busca pessoas para convidar para um grupo ou cofrinho compartilhado."""
    busca_limiter.hit(str(current_user.id))
    achados = usuarios_service.buscar(db, q, excluir_id=current_user.id)
    return [
        UsuarioMini(id=u.uuid, nome=u.nome, emailDica=usuarios_service.mascarar_email(u.email))
        for u in achados
    ]


@router.get("/{user_id}")
def get_user_doc(
    user_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
):
    if user_id != current_user.uuid:
        return UserDocResponse(id=user_id, data={}, exists=False)

    return UserDocResponse(
        id=current_user.uuid,
        data={
            "name": current_user.nome,
            "email": current_user.email,
            "adm": current_user.adm,
            "createdAt": current_user.created_at.isoformat() + "Z",
        },
        exists=True,
    )
