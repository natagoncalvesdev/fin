from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Cartao, Usuario

router = APIRouter(prefix="/api/cartoes", tags=["cartoes"])


class CartaoCreate(BaseModel):
    bandeira: str | None = None
    numero: str | None = None
    nome: str | None = None
    vencimento: int | None = Field(default=None, ge=1, le=31)


class CartaoUpdate(BaseModel):
    bandeira: str | None = None
    numero: str | None = None
    nome: str | None = None
    vencimento: int | None = Field(default=None, ge=1, le=31)
    situacao: str | None = None


class CartaoResponse(BaseModel):
    id: str
    data: dict


def _get_cartao(db: Session, cartao_uuid: str, usuario: Usuario) -> Cartao | None:
    return (
        db.query(Cartao)
        .filter(Cartao.uuid == cartao_uuid, Cartao.id_usuario == usuario.id)
        .first()
    )


@router.get("", response_model=list[CartaoResponse])
def list_cartoes(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    items = (
        db.query(Cartao)
        .filter(Cartao.id_usuario == current_user.id)
        .order_by(Cartao.created_at.desc())
        .all()
    )
    return [CartaoResponse(id=c.uuid, data=c.to_dict()) for c in items]


@router.post("", response_model=CartaoResponse, status_code=status.HTTP_201_CREATED)
def create_cartao(
    body: CartaoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cartao = Cartao(
        id_usuario=current_user.id,
        bandeira=body.bandeira,
        final_cartao=body.numero,
        nome=body.nome,
        vencimento=body.vencimento,
        created_at=datetime.utcnow(),
    )
    db.add(cartao)
    db.commit()
    db.refresh(cartao)
    return CartaoResponse(id=cartao.uuid, data=cartao.to_dict())


@router.get("/{cartao_id}", response_model=CartaoResponse)
def get_cartao(
    cartao_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cartao = _get_cartao(db, cartao_id, current_user)
    if not cartao:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")
    return CartaoResponse(id=cartao.uuid, data=cartao.to_dict())


@router.put("/{cartao_id}", response_model=CartaoResponse)
def update_cartao(
    cartao_id: str,
    body: CartaoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cartao = _get_cartao(db, cartao_id, current_user)
    if not cartao:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")

    if body.bandeira is not None:
        cartao.bandeira = body.bandeira
    if body.numero is not None:
        cartao.final_cartao = body.numero
    if body.nome is not None:
        cartao.nome = body.nome
    if body.vencimento is not None:
        cartao.vencimento = body.vencimento
    if body.situacao is not None:
        cartao.situacao = body.situacao

    db.commit()
    db.refresh(cartao)
    return CartaoResponse(id=cartao.uuid, data=cartao.to_dict())


@router.delete("/{cartao_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cartao(
    cartao_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cartao = _get_cartao(db, cartao_id, current_user)
    if not cartao:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")
    db.delete(cartao)
    db.commit()
