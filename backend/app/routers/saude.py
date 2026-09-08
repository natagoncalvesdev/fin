from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Conquista, MetaPeso, RegistroMedidas, RegistroPeso, Usuario

router = APIRouter(prefix="/api/saude", tags=["saude"])


# ---------------------------------------------------------------------------
# Peso
# ---------------------------------------------------------------------------


class PesoCreate(BaseModel):
    peso: float = Field(gt=0, le=1000)
    data: date | None = None


class PesoUpdate(BaseModel):
    peso: float | None = Field(default=None, gt=0, le=1000)
    data: date | None = None


def _get_peso_or_404(db: Session, peso_uuid: str, usuario: Usuario) -> RegistroPeso:
    item = (
        db.query(RegistroPeso)
        .filter(RegistroPeso.uuid == peso_uuid, RegistroPeso.id_usuario == usuario.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro de peso não encontrado.")
    return item


def _peso_atual(db: Session, usuario: Usuario) -> float | None:
    ultimo = (
        db.query(RegistroPeso)
        .filter(RegistroPeso.id_usuario == usuario.id)
        .order_by(RegistroPeso.data_registro.desc(), RegistroPeso.id.desc())
        .first()
    )
    return ultimo.peso if ultimo else None


def _peso_atinge_meta(peso: float, meta: MetaPeso) -> bool:
    base = meta.peso_inicial
    if base is None:
        return abs(peso - meta.peso_alvo) <= 0.05
    if meta.peso_alvo <= base:
        return peso <= meta.peso_alvo
    return peso >= meta.peso_alvo


def _nivel_medalha(delta_kg: float | None) -> str:
    """Nível da medalha pela distância percorrida (peso inicial -> alvo)."""
    if delta_kg is None:
        return "bronze"
    if delta_kg >= 10:
        return "ouro"
    if delta_kg >= 5:
        return "prata"
    return "bronze"


def _conceder_conquista(db: Session, usuario: Usuario, meta: MetaPeso) -> bool:
    """Cria a medalha da meta atingida (uma por meta, idempotente pelo uuid da
    meta). Retorna True se criou."""
    ja_tem = (
        db.query(Conquista)
        .filter(Conquista.id_usuario == usuario.id, Conquista.meta_uuid == meta.uuid)
        .first()
    )
    if ja_tem:
        return False

    delta = abs(meta.peso_inicial - meta.peso_alvo) if meta.peso_inicial is not None else None
    alvo_txt = f"{meta.peso_alvo:.1f}".replace(".", ",")
    quando = meta.data_atingida or date.today()
    db.add(
        Conquista(
            id_usuario=usuario.id,
            tipo="meta_peso",
            titulo=f"Meta de {alvo_txt} kg",
            descricao=f"Você atingiu {alvo_txt} kg em {quando.strftime('%d/%m/%Y')}.",
            nivel=_nivel_medalha(delta),
            peso_alvo=meta.peso_alvo,
            meta_uuid=meta.uuid,
            data_conquista=quando,
        )
    )
    return True


def _sincronizar_metas(db: Session, usuario: Usuario) -> bool:
    """Recalcula do zero a situação de cada meta não arquivada a partir de todo
    o histórico de peso. Idempotente: só promove "ativa" -> "atingida" (com a
    data do primeiro registro, posterior à criação da meta, que bate o alvo) ou
    volta para "ativa" se nenhum registro bate mais. "arquivada" nunca muda
    automaticamente. Cada meta atingida rende uma medalha permanente (Conquista).
    Retorna True se algo mudou."""
    metas = (
        db.query(MetaPeso)
        .filter(MetaPeso.id_usuario == usuario.id, MetaPeso.situacao != "arquivada")
        .all()
    )
    if not metas:
        return False

    pesos = (
        db.query(RegistroPeso)
        .filter(RegistroPeso.id_usuario == usuario.id)
        .order_by(RegistroPeso.data_registro.asc(), RegistroPeso.id.asc())
        .all()
    )

    mudou = False
    for meta in metas:
        atingida_em = next(
            (
                p.data_registro
                for p in pesos
                if p.data_registro >= meta.data_criacao and _peso_atinge_meta(p.peso, meta)
            ),
            None,
        )
        nova = "atingida" if atingida_em else "ativa"
        if meta.situacao != nova or meta.data_atingida != atingida_em:
            meta.situacao = nova
            meta.data_atingida = atingida_em
            mudou = True
        if nova == "atingida" and _conceder_conquista(db, usuario, meta):
            mudou = True
    return mudou


@router.get("/peso")
def list_peso(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    dias: int | None = Query(default=None, ge=1, le=3660),
):
    query = db.query(RegistroPeso).filter(RegistroPeso.id_usuario == current_user.id)
    if dias:
        limite = date.today() - timedelta(days=dias)
        query = query.filter(RegistroPeso.data_registro >= limite)
    itens = query.order_by(RegistroPeso.data_registro.asc(), RegistroPeso.id.asc()).all()
    return [{"id": p.uuid, "data": p.to_dict()} for p in itens]


@router.post("/peso", status_code=status.HTTP_201_CREATED)
def create_peso(
    body: PesoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    item = RegistroPeso(
        id_usuario=current_user.id,
        peso=body.peso,
        data_registro=body.data or date.today(),
    )
    db.add(item)
    db.flush()
    _sincronizar_metas(db, current_user)
    db.commit()
    db.refresh(item)
    return {"id": item.uuid, "data": item.to_dict()}


@router.put("/peso/{peso_id}")
def update_peso(
    peso_id: str,
    body: PesoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    item = _get_peso_or_404(db, peso_id, current_user)
    if body.peso is not None:
        item.peso = body.peso
    if body.data is not None:
        item.data_registro = body.data
    db.flush()
    _sincronizar_metas(db, current_user)
    db.commit()
    db.refresh(item)
    return {"id": item.uuid, "data": item.to_dict()}


@router.delete("/peso/{peso_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_peso(
    peso_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    item = _get_peso_or_404(db, peso_id, current_user)
    db.delete(item)
    db.flush()
    _sincronizar_metas(db, current_user)
    db.commit()


# ---------------------------------------------------------------------------
# Medidas
# ---------------------------------------------------------------------------

_MEDIDA_CAMPOS = {
    "pescoco": "pescoco",
    "peito": "peito",
    "cintura": "cintura",
    "abdomen": "abdomen",
    "quadril": "quadril",
    "bracoDir": "braco_dir",
    "bracoEsq": "braco_esq",
    "coxaDir": "coxa_dir",
    "coxaEsq": "coxa_esq",
    "panturrilhaDir": "panturrilha_dir",
    "panturrilhaEsq": "panturrilha_esq",
}

_MedidaValor = float | None


class MedidasCreate(BaseModel):
    data: date | None = None
    pescoco: _MedidaValor = Field(default=None, ge=0, le=500)
    peito: _MedidaValor = Field(default=None, ge=0, le=500)
    cintura: _MedidaValor = Field(default=None, ge=0, le=500)
    abdomen: _MedidaValor = Field(default=None, ge=0, le=500)
    quadril: _MedidaValor = Field(default=None, ge=0, le=500)
    bracoDir: _MedidaValor = Field(default=None, ge=0, le=500)
    bracoEsq: _MedidaValor = Field(default=None, ge=0, le=500)
    coxaDir: _MedidaValor = Field(default=None, ge=0, le=500)
    coxaEsq: _MedidaValor = Field(default=None, ge=0, le=500)
    panturrilhaDir: _MedidaValor = Field(default=None, ge=0, le=500)
    panturrilhaEsq: _MedidaValor = Field(default=None, ge=0, le=500)


class MedidasUpdate(MedidasCreate):
    pass


def _get_medida_or_404(db: Session, medida_uuid: str, usuario: Usuario) -> RegistroMedidas:
    item = (
        db.query(RegistroMedidas)
        .filter(RegistroMedidas.uuid == medida_uuid, RegistroMedidas.id_usuario == usuario.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro de medidas não encontrado.")
    return item


def _aplicar_medidas(item: RegistroMedidas, body: MedidasCreate, *, apenas_enviados: set[str] | None) -> None:
    for chave_api, coluna in _MEDIDA_CAMPOS.items():
        if apenas_enviados is not None and chave_api not in apenas_enviados:
            continue
        setattr(item, coluna, getattr(body, chave_api))


@router.get("/medidas")
def list_medidas(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    itens = (
        db.query(RegistroMedidas)
        .filter(RegistroMedidas.id_usuario == current_user.id)
        .order_by(RegistroMedidas.data_registro.desc(), RegistroMedidas.id.desc())
        .all()
    )
    return [{"id": m.uuid, "data": m.to_dict()} for m in itens]


@router.post("/medidas", status_code=status.HTTP_201_CREATED)
def create_medidas(
    body: MedidasCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    item = RegistroMedidas(
        id_usuario=current_user.id,
        data_registro=body.data or date.today(),
    )
    _aplicar_medidas(item, body, apenas_enviados=None)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.uuid, "data": item.to_dict()}


@router.put("/medidas/{medida_id}")
def update_medidas(
    medida_id: str,
    body: MedidasUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    item = _get_medida_or_404(db, medida_id, current_user)
    enviados = set(body.model_fields_set)
    if "data" in enviados and body.data is not None:
        item.data_registro = body.data
    _aplicar_medidas(item, body, apenas_enviados=enviados - {"data"})
    db.commit()
    db.refresh(item)
    return {"id": item.uuid, "data": item.to_dict()}


@router.delete("/medidas/{medida_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medidas(
    medida_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    item = _get_medida_or_404(db, medida_id, current_user)
    db.delete(item)
    db.commit()


# ---------------------------------------------------------------------------
# Metas de peso (histórico)
# ---------------------------------------------------------------------------

_SITUACOES_EDITAVEIS = {"ativa", "arquivada"}


class MetaCreate(BaseModel):
    pesoAlvo: float = Field(gt=0, le=1000)
    pesoInicial: float | None = Field(default=None, gt=0, le=1000)
    dataAlvo: date | None = None


class MetaUpdate(BaseModel):
    pesoAlvo: float | None = Field(default=None, gt=0, le=1000)
    dataAlvo: date | None = None
    situacao: str | None = None


def _get_meta_or_404(db: Session, meta_uuid: str, usuario: Usuario) -> MetaPeso:
    item = (
        db.query(MetaPeso)
        .filter(MetaPeso.uuid == meta_uuid, MetaPeso.id_usuario == usuario.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta não encontrada.")
    return item


def _listar_metas(db: Session, usuario: Usuario) -> list[dict]:
    itens = (
        db.query(MetaPeso)
        .filter(MetaPeso.id_usuario == usuario.id)
        .order_by(MetaPeso.data_criacao.desc(), MetaPeso.id.desc())
        .all()
    )
    return [{"id": m.uuid, "data": m.to_dict()} for m in itens]


@router.get("/metas")
def list_metas(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if _sincronizar_metas(db, current_user):
        db.commit()
    return _listar_metas(db, current_user)


@router.post("/metas", status_code=status.HTTP_201_CREATED)
def create_meta(
    body: MetaCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    meta = MetaPeso(
        id_usuario=current_user.id,
        peso_alvo=body.pesoAlvo,
        peso_inicial=body.pesoInicial if body.pesoInicial is not None else _peso_atual(db, current_user),
        data_alvo=body.dataAlvo,
        data_criacao=date.today(),
        situacao="ativa",
    )
    db.add(meta)
    db.flush()
    _sincronizar_metas(db, current_user)
    db.commit()
    db.refresh(meta)
    return {"id": meta.uuid, "data": meta.to_dict()}


@router.put("/metas/{meta_id}")
def update_meta(
    meta_id: str,
    body: MetaUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    meta = _get_meta_or_404(db, meta_id, current_user)
    if body.pesoAlvo is not None:
        meta.peso_alvo = body.pesoAlvo
    if "dataAlvo" in body.model_fields_set:
        meta.data_alvo = body.dataAlvo
    if body.situacao is not None:
        if body.situacao not in _SITUACOES_EDITAVEIS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Situação deve ser 'ativa' ou 'arquivada'.",
            )
        meta.situacao = body.situacao
        if body.situacao == "arquivada":
            meta.data_atingida = None
    db.flush()
    _sincronizar_metas(db, current_user)
    db.commit()
    db.refresh(meta)
    return {"id": meta.uuid, "data": meta.to_dict()}


@router.delete("/metas/{meta_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meta(
    meta_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    meta = _get_meta_or_404(db, meta_id, current_user)
    db.delete(meta)
    db.commit()


# ---------------------------------------------------------------------------
# Conquistas (medalhas)
# ---------------------------------------------------------------------------


@router.get("/conquistas")
def list_conquistas(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    # Garante que metas já batidas (ex.: antes desta feature existir) rendam a
    # medalha ao abrir a página.
    if _sincronizar_metas(db, current_user):
        db.commit()
    itens = (
        db.query(Conquista)
        .filter(Conquista.id_usuario == current_user.id)
        .order_by(Conquista.data_conquista.desc(), Conquista.id.desc())
        .all()
    )
    return [{"id": c.uuid, "data": c.to_dict()} for c in itens]
