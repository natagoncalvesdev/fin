from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Cartao, User

router = APIRouter(prefix="/api/cartoes", tags=["cartoes"])


class CartaoCreate(BaseModel):
    tipo: str = "credito"
    bandeira: str | None = None
    numero: str | None = None
    nome: str | None = None


class CartaoUpdate(BaseModel):
    tipo: str | None = None
    bandeira: str | None = None
    numero: str | None = None
    nome: str | None = None


class CartaoResponse(BaseModel):
    id: str
    data: dict


@router.get("", response_model=list[CartaoResponse])
def list_cartoes(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    items = (
        db.query(Cartao)
        .filter(Cartao.user_id == current_user.id)
        .order_by(Cartao.data_criacao.desc())
        .all()
    )
    return [CartaoResponse(id=c.id, data=c.to_dict()) for c in items]


@router.post("", response_model=CartaoResponse, status_code=status.HTTP_201_CREATED)
def create_cartao(
    body: CartaoCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cartao = Cartao(
        user_id=current_user.id,
        tipo=body.tipo,
        bandeira=body.bandeira,
        numero=body.numero,
        nome=body.nome,
        data_criacao=datetime.utcnow(),
    )
    db.add(cartao)
    db.commit()
    db.refresh(cartao)
    return CartaoResponse(id=cartao.id, data=cartao.to_dict())


@router.get("/{cartao_id}", response_model=CartaoResponse)
def get_cartao(
    cartao_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cartao = db.get(Cartao, cartao_id)
    if not cartao or cartao.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")
    return CartaoResponse(id=cartao.id, data=cartao.to_dict())


@router.put("/{cartao_id}", response_model=CartaoResponse)
def update_cartao(
    cartao_id: str,
    body: CartaoUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cartao = db.get(Cartao, cartao_id)
    if not cartao or cartao.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")

    if body.tipo is not None:
        cartao.tipo = body.tipo
    if body.bandeira is not None:
        cartao.bandeira = body.bandeira
    if body.numero is not None:
        cartao.numero = body.numero
    if body.nome is not None:
        cartao.nome = body.nome

    db.commit()
    db.refresh(cartao)
    return CartaoResponse(id=cartao.id, data=cartao.to_dict())


@router.delete("/{cartao_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cartao(
    cartao_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cartao = db.get(Cartao, cartao_id)
    if not cartao or cartao.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")
    db.delete(cartao)
    db.commit()
