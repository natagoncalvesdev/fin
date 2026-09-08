"""Busca e resolução de usuários para os fluxos de convite (grupos, cofrinhos
compartilhados)."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Usuario


def buscar(db: Session, termo: str, excluir_id: int | None = None, limite: int = 8) -> list[Usuario]:
    """Casa email exato (case-insensitive) OU nome contendo `termo` (mín. 2
    caracteres). Exclui `excluir_id` (o próprio usuário)."""
    termo = (termo or "").strip()
    if len(termo) < 2:
        return []
    alvo = termo.lower()
    query = db.query(Usuario).filter(
        (func.lower(Usuario.email) == alvo) | (Usuario.nome.ilike(f"%{termo}%"))
    )
    if excluir_id is not None:
        query = query.filter(Usuario.id != excluir_id)
    return query.order_by(Usuario.nome.asc()).limit(limite).all()


def resolver(db: Session, *, email: str | None = None, usuario_id: str | None = None) -> Usuario:
    """Encontra o usuário por uuid (usuarioId) ou email. 404 se não existir."""
    usuario = None
    if usuario_id:
        usuario = db.query(Usuario).filter(Usuario.uuid == usuario_id).first()
    elif email:
        usuario = db.query(Usuario).filter(func.lower(Usuario.email) == email.strip().lower()).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return usuario
