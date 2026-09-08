from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import cofrinhos_service
from app.auth import get_current_user
from app.database import get_db
from app.financeiro_service import criar_debito
from app.models import MESES, AporteCofrinho, Cofrinho, Debito, Usuario

router = APIRouter(prefix="/api/cofrinhos", tags=["cofrinhos"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class CofrinhoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    valorAlvo: float | None = Field(default=None, gt=0, le=1_000_000_000)
    aporteMensal: float | None = Field(default=None, gt=0, le=1_000_000_000)
    mesAlvo: str
    anoAlvo: int = Field(ge=2000, le=2100)


class CofrinhoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    valorAlvo: float | None = Field(default=None, gt=0, le=1_000_000_000)
    aporteMensal: float | None = Field(default=None, gt=0, le=1_000_000_000)
    mesAlvo: str | None = None
    anoAlvo: int | None = Field(default=None, ge=2000, le=2100)
    situacao: str | None = None


class AporteCreate(BaseModel):
    valor: float = Field(gt=0, le=1_000_000_000)
    data: date | None = None


class AporteUpdate(BaseModel):
    valor: float | None = Field(default=None, gt=0, le=1_000_000_000)
    data: date | None = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _checar_mes(mes: str) -> None:
    if mes not in MESES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mês inválido.")


def _checar_modo(valor_alvo: float | None, aporte_mensal: float | None) -> None:
    if (valor_alvo is None) == (aporte_mensal is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe um valor alvo OU um aporte mensal (apenas um dos dois).",
        )


def _get_cofrinho_or_404(db: Session, cofrinho_uuid: str, usuario: Usuario) -> Cofrinho:
    item = (
        db.query(Cofrinho)
        .filter(Cofrinho.uuid == cofrinho_uuid, Cofrinho.id_usuario == usuario.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cofrinho não encontrado.")
    return item


def _get_aporte_or_404(db: Session, aporte_uuid: str, cofrinho: Cofrinho) -> AporteCofrinho:
    item = (
        db.query(AporteCofrinho)
        .filter(AporteCofrinho.uuid == aporte_uuid, AporteCofrinho.id_cofrinho == cofrinho.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aporte não encontrado.")
    return item


def _debito_espelho(db: Session, usuario: Usuario, aporte: AporteCofrinho) -> Debito | None:
    if not aporte.id_debito:
        return None
    return (
        db.query(Debito)
        .filter(Debito.id == aporte.id_debito, Debito.id_usuario == usuario.id)
        .first()
    )


def _sincronizar_debito(db: Session, usuario: Usuario, cofrinho: Cofrinho, aporte: AporteCofrinho) -> None:
    """Mantém o débito-espelho do aporte (o aporte "conta como saída do mês")."""
    deb = _debito_espelho(db, usuario, aporte)
    if deb is None:
        mes_nome = MESES[aporte.data_aporte.month - 1]
        novo = criar_debito(
            db,
            usuario,
            ano=aporte.data_aporte.year,
            mes=mes_nome,
            nome=f"Cofrinho: {cofrinho.nome}",
            valor=aporte.valor,
            categoria="Cofrinho",
        )
        aporte.id_debito = novo.id
        return
    deb.valor = aporte.valor
    deb.compra = f"Cofrinho: {cofrinho.nome}"
    deb.data_debito = date(aporte.data_aporte.year, aporte.data_aporte.month, 1)


def _remover_debito(db: Session, usuario: Usuario, aporte: AporteCofrinho) -> None:
    deb = _debito_espelho(db, usuario, aporte)
    if deb is not None:
        db.delete(deb)
    aporte.id_debito = None


# --------------------------------------------------------------------------- #
# Cofrinhos
# --------------------------------------------------------------------------- #


@router.get("")
def list_cofrinhos(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if cofrinhos_service.sincronizar_todos(db, current_user):
        db.commit()
    itens = (
        db.query(Cofrinho)
        .filter(Cofrinho.id_usuario == current_user.id)
        .order_by(Cofrinho.created_at.desc(), Cofrinho.id.desc())
        .all()
    )
    return [cofrinhos_service.payload(c) for c in itens]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_cofrinho(
    body: CofrinhoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(body.mesAlvo)
    _checar_modo(body.valorAlvo, body.aporteMensal)
    cofrinho = Cofrinho(
        id_usuario=current_user.id,
        nome=body.nome.strip(),
        valor_alvo=body.valorAlvo,
        aporte_mensal=body.aporteMensal,
        mes_alvo=body.mesAlvo,
        ano_alvo=body.anoAlvo,
        data_inicio=date.today(),
        situacao="ativo",
    )
    db.add(cofrinho)
    db.flush()
    db.commit()
    db.refresh(cofrinho)
    return cofrinhos_service.payload(cofrinho)


@router.put("/{cofrinho_id}")
def update_cofrinho(
    cofrinho_id: str,
    body: CofrinhoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_cofrinho_or_404(db, cofrinho_id, current_user)
    enviados = body.model_fields_set

    if body.nome is not None:
        cofrinho.nome = body.nome.strip()
    if body.mesAlvo is not None:
        _checar_mes(body.mesAlvo)
        cofrinho.mes_alvo = body.mesAlvo
    if body.anoAlvo is not None:
        cofrinho.ano_alvo = body.anoAlvo
    if "valorAlvo" in enviados:
        cofrinho.valor_alvo = body.valorAlvo
    if "aporteMensal" in enviados:
        cofrinho.aporte_mensal = body.aporteMensal
    if "valorAlvo" in enviados or "aporteMensal" in enviados:
        _checar_modo(cofrinho.valor_alvo, cofrinho.aporte_mensal)
    if body.situacao is not None:
        if body.situacao not in ("ativo", "arquivado"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Situação deve ser 'ativo' ou 'arquivado'.",
            )
        cofrinho.situacao = body.situacao
        if body.situacao == "arquivado":
            cofrinho.data_concluido = None

    if body.nome is not None:
        for aporte in cofrinho.aportes:
            deb = _debito_espelho(db, current_user, aporte)
            if deb is not None:
                deb.compra = f"Cofrinho: {cofrinho.nome}"

    db.flush()
    cofrinhos_service.sincronizar(db, current_user, cofrinho)
    db.commit()
    db.refresh(cofrinho)
    return cofrinhos_service.payload(cofrinho)


@router.delete("/{cofrinho_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cofrinho(
    cofrinho_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_cofrinho_or_404(db, cofrinho_id, current_user)
    for aporte in list(cofrinho.aportes):
        _remover_debito(db, current_user, aporte)
    db.delete(cofrinho)
    db.commit()


# --------------------------------------------------------------------------- #
# Aportes
# --------------------------------------------------------------------------- #


@router.post("/{cofrinho_id}/aportes", status_code=status.HTTP_201_CREATED)
def create_aporte(
    cofrinho_id: str,
    body: AporteCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_cofrinho_or_404(db, cofrinho_id, current_user)
    aporte = AporteCofrinho(
        id_cofrinho=cofrinho.id,
        id_usuario=current_user.id,
        data_aporte=body.data or date.today(),
        valor=body.valor,
    )
    db.add(aporte)
    db.flush()
    _sincronizar_debito(db, current_user, cofrinho, aporte)
    db.flush()
    cofrinhos_service.sincronizar(db, current_user, cofrinho)
    db.commit()
    db.refresh(cofrinho)
    return cofrinhos_service.payload(cofrinho)


@router.put("/{cofrinho_id}/aportes/{aporte_id}")
def update_aporte(
    cofrinho_id: str,
    aporte_id: str,
    body: AporteUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_cofrinho_or_404(db, cofrinho_id, current_user)
    aporte = _get_aporte_or_404(db, aporte_id, cofrinho)
    if body.valor is not None:
        aporte.valor = body.valor
    if body.data is not None:
        aporte.data_aporte = body.data
    db.flush()
    _sincronizar_debito(db, current_user, cofrinho, aporte)
    db.flush()
    cofrinhos_service.sincronizar(db, current_user, cofrinho)
    db.commit()
    db.refresh(cofrinho)
    return cofrinhos_service.payload(cofrinho)


@router.delete("/{cofrinho_id}/aportes/{aporte_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_aporte(
    cofrinho_id: str,
    aporte_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_cofrinho_or_404(db, cofrinho_id, current_user)
    aporte = _get_aporte_or_404(db, aporte_id, cofrinho)
    _remover_debito(db, current_user, aporte)
    db.delete(aporte)
    db.flush()
    cofrinhos_service.sincronizar(db, current_user, cofrinho)
    db.commit()
