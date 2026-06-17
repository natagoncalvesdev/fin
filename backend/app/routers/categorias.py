from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Categoria, Usuario

router = APIRouter(prefix="/api/categorias", tags=["categorias"])


class CategoriaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=255)


class CategoriaResponse(BaseModel):
    id: str
    nome: str


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
    return [CategoriaResponse(id=c.uuid, nome=c.nome) for c in items]


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

    categoria = Categoria(id_usuario=current_user.id, nome=nome)
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return CategoriaResponse(id=categoria.uuid, nome=categoria.nome)


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
