from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Categoria, Usuario

router = APIRouter(prefix="/api/categorias", tags=["categorias"])

ICONES_CATEGORIA = {
    "alimentacao",
    "mercado",
    "transporte",
    "combustivel",
    "moradia",
    "contas",
    "saude",
    "educacao",
    "lazer",
    "vestuario",
    "eletronicos",
    "viagem",
    "pet",
    "dinheiro",
    "presente",
    "beleza",
    "familia",
    "outros",
}


def normalizar_icone(icone: str | None) -> str | None:
    if icone is None:
        return None
    chave = icone.strip()
    if not chave:
        return None
    if chave not in ICONES_CATEGORIA:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ícone inválido.")
    return chave


class CategoriaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    icone: str | None = None


class CategoriaUpdate(BaseModel):
    icone: str | None = None


class CategoriaResponse(BaseModel):
    id: str
    nome: str
    icone: str | None = None


@router.get("", response_model=list[CategoriaResponse])
def list_categorias(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    items = (
        db.query(Categoria)
        .filter(Categoria.id_usuario == current_user.id)
        .order_by(Categoria.nome)
        .all()
    )
    return [CategoriaResponse(id=c.uuid, nome=c.nome, icone=c.icone) for c in items]


@router.post("", response_model=CategoriaResponse, status_code=status.HTTP_201_CREATED)
def create_categoria(
    body: CategoriaCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    nome = body.nome.strip()
    existing = (
        db.query(Categoria)
        .filter(Categoria.id_usuario == current_user.id, Categoria.nome.ilike(nome))
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Categoria já existe.")

    categoria = Categoria(
        id_usuario=current_user.id,
        nome=nome,
        icone=normalizar_icone(body.icone),
    )
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return CategoriaResponse(id=categoria.uuid, nome=categoria.nome, icone=categoria.icone)


@router.put("/{categoria_id}", response_model=CategoriaResponse)
def update_categoria(
    categoria_id: str,
    body: CategoriaUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    categoria = (
        db.query(Categoria)
        .filter(Categoria.uuid == categoria_id, Categoria.id_usuario == current_user.id)
        .first()
    )
    if not categoria:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria não encontrada.")
    categoria.icone = normalizar_icone(body.icone)
    db.commit()
    db.refresh(categoria)
    return CategoriaResponse(id=categoria.uuid, nome=categoria.nome, icone=categoria.icone)


@router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_categoria(
    categoria_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    categoria = (
        db.query(Categoria)
        .filter(Categoria.uuid == categoria_id, Categoria.id_usuario == current_user.id)
        .first()
    )
    if not categoria:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria não encontrada.")
    db.delete(categoria)
    db.commit()
