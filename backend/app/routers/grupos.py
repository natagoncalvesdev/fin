from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import grupos_service, usuarios_service
from app.auth import get_current_user
from app.database import get_db
from app.models import Grupo, GrupoMembro, Usuario
from app.validators import nome_sem_html

router = APIRouter(prefix="/api/grupos", tags=["grupos"])

TIPOS_VALIDOS = {"saude"}


class GrupoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    tipo: str = "saude"

    @field_validator("nome")
    @classmethod
    def _valida_nome(cls, v: str) -> str:
        return nome_sem_html(v)


class MembroInvite(BaseModel):
    email: str | None = None
    usuarioId: str | None = None


def _participacao(db: Session, grupo: Grupo, usuario: Usuario) -> GrupoMembro | None:
    return (
        db.query(GrupoMembro)
        .filter(GrupoMembro.id_grupo == grupo.id, GrupoMembro.id_usuario == usuario.id)
        .first()
    )


def _get_grupo_membro(db: Session, grupo_uuid: str, usuario: Usuario) -> tuple[Grupo, GrupoMembro]:
    grupo = db.query(Grupo).filter(Grupo.uuid == grupo_uuid).first()
    membro = _participacao(db, grupo, usuario) if grupo else None
    if not grupo or not membro or membro.situacao != "ativo":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo não encontrado.")
    return grupo, membro


def _get_grupo_dono(db: Session, grupo_uuid: str, usuario: Usuario) -> Grupo:
    grupo = db.query(Grupo).filter(Grupo.uuid == grupo_uuid, Grupo.id_dono == usuario.id).first()
    if not grupo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo não encontrado.")
    return grupo


def _membros_payload(db: Session, grupo: Grupo) -> list[dict]:
    membros = db.query(GrupoMembro).filter(GrupoMembro.id_grupo == grupo.id).order_by(GrupoMembro.id.asc()).all()
    nomes = {
        u.id: u.nome
        for u in db.query(Usuario).filter(Usuario.id.in_([m.id_usuario for m in membros] or [0])).all()
    }
    return [
        {
            "id": m.uuid,
            "nome": nomes.get(m.id_usuario, "—"),
            "papel": m.papel,
            "situacao": m.situacao,
        }
        for m in membros
    ]


def _grupo_resumo(db: Session, grupo: Grupo, usuario: Usuario) -> dict:
    total = (
        db.query(GrupoMembro)
        .filter(GrupoMembro.id_grupo == grupo.id, GrupoMembro.situacao == "ativo")
        .count()
    )
    return {
        "id": grupo.uuid,
        "nome": grupo.nome,
        "tipo": grupo.tipo,
        "souDono": grupo.id_dono == usuario.id,
        "totalMembros": total,
    }


@router.get("")
def list_grupos(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    tipo: str | None = Query(default=None),
):
    query = (
        db.query(Grupo)
        .join(GrupoMembro, GrupoMembro.id_grupo == Grupo.id)
        .filter(GrupoMembro.id_usuario == current_user.id, GrupoMembro.situacao == "ativo")
    )
    if tipo:
        query = query.filter(Grupo.tipo == tipo)
    grupos = query.order_by(Grupo.created_at.desc(), Grupo.id.desc()).all()
    return [_grupo_resumo(db, g, current_user) for g in grupos]


@router.get("/convites")
def list_convites(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    pendentes = (
        db.query(GrupoMembro)
        .filter(GrupoMembro.id_usuario == current_user.id, GrupoMembro.situacao == "pendente")
        .all()
    )
    out = []
    for m in pendentes:
        grupo = db.query(Grupo).filter(Grupo.id == m.id_grupo).first()
        if not grupo:
            continue
        dono = db.query(Usuario).filter(Usuario.id == grupo.id_dono).first()
        out.append(
            {
                "id": m.uuid,
                "grupoNome": grupo.nome,
                "tipo": grupo.tipo,
                "donoNome": dono.nome if dono else "—",
            }
        )
    return out


@router.post("/convites/{convite_id}/aceitar")
def aceitar_convite(
    convite_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    m = (
        db.query(GrupoMembro)
        .filter(
            GrupoMembro.uuid == convite_id,
            GrupoMembro.id_usuario == current_user.id,
            GrupoMembro.situacao == "pendente",
        )
        .first()
    )
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite não encontrado.")
    m.situacao = "ativo"
    m.entrou_em = date.today()
    db.commit()
    return {"ok": True}


@router.post("/convites/{convite_id}/recusar")
def recusar_convite(
    convite_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    m = (
        db.query(GrupoMembro)
        .filter(
            GrupoMembro.uuid == convite_id,
            GrupoMembro.id_usuario == current_user.id,
            GrupoMembro.situacao == "pendente",
        )
        .first()
    )
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite não encontrado.")
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_grupo(
    body: GrupoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    tipo = body.tipo.strip().lower()
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de grupo inválido.")
    grupo = Grupo(id_dono=current_user.id, tipo=tipo, nome=body.nome.strip())
    db.add(grupo)
    db.flush()
    db.add(
        GrupoMembro(
            id_grupo=grupo.id,
            id_usuario=current_user.id,
            papel="dono",
            situacao="ativo",
            entrou_em=date.today(),
        )
    )
    db.commit()
    db.refresh(grupo)
    return _grupo_resumo(db, grupo, current_user)


@router.get("/{grupo_id}")
def get_grupo(
    grupo_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    grupo, membro = _get_grupo_membro(db, grupo_id, current_user)
    payload = _grupo_resumo(db, grupo, current_user)
    payload["meuMembroId"] = membro.uuid
    payload["membros"] = _membros_payload(db, grupo)
    if grupo.tipo == "saude":
        payload["resumo"] = grupos_service.resumo_saude(db, grupo)
    return payload


@router.delete("/{grupo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_grupo(
    grupo_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    grupo = _get_grupo_dono(db, grupo_id, current_user)
    db.delete(grupo)  # cascade remove grupo_membro
    db.commit()


@router.post("/{grupo_id}/membros", status_code=status.HTTP_201_CREATED)
def add_membro(
    grupo_id: str,
    body: MembroInvite,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    grupo = _get_grupo_dono(db, grupo_id, current_user)
    alvo = usuarios_service.resolver(db, email=body.email, usuario_id=body.usuarioId)
    if alvo.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Você já está no grupo.")
    if _participacao(db, grupo, alvo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Essa pessoa já foi convidada."
        )
    db.add(
        GrupoMembro(
            id_grupo=grupo.id,
            id_usuario=alvo.id,
            papel="membro",
            situacao="pendente",
            convidado_por=current_user.id,
        )
    )
    db.commit()
    return {"ok": True}


@router.delete("/{grupo_id}/membros/{membro_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_membro(
    grupo_id: str,
    membro_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    grupo = db.query(Grupo).filter(Grupo.uuid == grupo_id).first()
    if not grupo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo não encontrado.")
    m = (
        db.query(GrupoMembro)
        .filter(GrupoMembro.uuid == membro_id, GrupoMembro.id_grupo == grupo.id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membro não encontrado.")
    if grupo.id_dono != current_user.id and m.id_usuario != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
    if m.papel == "dono":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="O dono não pode sair do próprio grupo."
        )
    db.delete(m)
    db.commit()
