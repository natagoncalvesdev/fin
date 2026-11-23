import re
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Cartao, Usuario

router = APIRouter(prefix="/api/cartoes", tags=["cartoes"])

TEMAS_PREDEFINIDOS = {
    "bandeira",
    "nubank",
    "itau",
    "santander",
    "bradesco",
    "bb",
    "caixa",
    "inter",
    "c6",
    "xp",
    "btg",
    "picpay",
    "mercadopago",
    "neon",
    "pagbank",
    "will",
    "porto",
    "original",
    "next",
    "sicoob",
    "sicredi",
}


class CartaoCreate(BaseModel):
    bandeira: str | None = None
    numero: str | None = None
    nome: str | None = None
    vencimento: int | None = Field(default=None, ge=1, le=31)
    tema: str | None = None
    corInicio: str | None = None
    corFim: str | None = None


class CartaoUpdate(BaseModel):
    bandeira: str | None = None
    numero: str | None = None
    nome: str | None = None
    vencimento: int | None = Field(default=None, ge=1, le=31)
    situacao: str | None = None
    tema: str | None = None
    corInicio: str | None = None
    corFim: str | None = None


def _normalizar_cor(valor: str | None) -> str | None:
    if valor is None or not str(valor).strip():
        return None
    cor = str(valor).strip()
    curto = re.fullmatch(r"#([0-9a-fA-F]{3})", cor)
    if curto:
        cor = "#" + "".join(ch * 2 for ch in curto.group(1))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", cor):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use uma cor no formato #RRGGBB.",
        )
    return cor.lower()


def _definir_aparencia(
    cartao: Cartao,
    tema: str | None,
    cor_inicio: str | None,
    cor_fim: str | None,
) -> None:
    tema_id = (tema or "bandeira").strip().lower()
    if tema_id == "personalizado":
        inicio = _normalizar_cor(cor_inicio)
        fim = _normalizar_cor(cor_fim)
        if not inicio or not fim:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Escolha a cor inicial e a cor final do degradê.",
            )
        cartao.tema = "personalizado"
        cartao.cor_inicio = inicio
        cartao.cor_fim = fim
        return
    if tema_id not in TEMAS_PREDEFINIDOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Escolha um visual de cartão válido.",
        )
    cartao.tema = None if tema_id == "bandeira" else tema_id
    cartao.cor_inicio = None
    cartao.cor_fim = None


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
    _definir_aparencia(cartao, body.tema, body.corInicio, body.corFim)
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
    if "tema" in body.model_fields_set:
        _definir_aparencia(cartao, body.tema, body.corInicio, body.corFim)

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
