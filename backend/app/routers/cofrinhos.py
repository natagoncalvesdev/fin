from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import cofrinhos_service
from app.auth import get_current_user
from app.database import get_db
from app.models import MESES, Cofrinho, Conta, Usuario

router = APIRouter(prefix="/api/cofrinhos", tags=["cofrinhos"])


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


def _checar_mes(mes: str) -> None:
    if mes not in MESES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mês inválido.")


def _checar_modo(valor_alvo: float | None, aporte_mensal: float | None) -> None:
    if (valor_alvo is None) == (aporte_mensal is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe um valor alvo OU um aporte mensal (apenas um dos dois).",
        )


def _get_or_404(db: Session, cofrinho_uuid: str, usuario: Usuario) -> Cofrinho:
    item = (
        db.query(Cofrinho)
        .filter(Cofrinho.uuid == cofrinho_uuid, Cofrinho.id_usuario == usuario.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cofrinho não encontrado.")
    return item


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
    return [cofrinhos_service.payload(db, c) for c in itens]


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
    cofrinhos_service.gerar_parcelas(db, current_user, cofrinho)
    db.commit()
    db.refresh(cofrinho)
    return cofrinhos_service.payload(db, cofrinho)


@router.put("/{cofrinho_id}")
def update_cofrinho(
    cofrinho_id: str,
    body: CofrinhoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_or_404(db, cofrinho_id, current_user)
    enviados = body.model_fields_set
    cronograma_mudou = False

    if body.nome is not None and body.nome.strip() != cofrinho.nome:
        cofrinho.nome = body.nome.strip()
        for conta in db.query(Conta).filter(Conta.id_cofrinho == cofrinho.id):
            conta.nome = f"Cofrinho: {cofrinho.nome}"
    if body.mesAlvo is not None:
        _checar_mes(body.mesAlvo)
        cofrinho.mes_alvo = body.mesAlvo
        cronograma_mudou = True
    if body.anoAlvo is not None:
        cofrinho.ano_alvo = body.anoAlvo
        cronograma_mudou = True
    if "valorAlvo" in enviados:
        cofrinho.valor_alvo = body.valorAlvo
        cronograma_mudou = True
    if "aporteMensal" in enviados:
        cofrinho.aporte_mensal = body.aporteMensal
        cronograma_mudou = True
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

    db.flush()
    if cronograma_mudou:
        cofrinhos_service.apagar_parcelas_pendentes(db, cofrinho)
        cofrinhos_service.gerar_parcelas(db, current_user, cofrinho)
        cofrinhos_service.recalcular_pendentes(db, cofrinho)
    cofrinhos_service.sincronizar(db, current_user, cofrinho)
    db.commit()
    db.refresh(cofrinho)
    return cofrinhos_service.payload(db, cofrinho)


@router.delete("/{cofrinho_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cofrinho(
    cofrinho_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_or_404(db, cofrinho_id, current_user)
    # Parcelas pendentes somem; as já pagas ficam no financeiro (só perdem o
    # vínculo com o cofrinho) — são dinheiro que de fato saiu da conta.
    for conta in db.query(Conta).filter(Conta.id_cofrinho == cofrinho.id).all():
        if conta.situacao == "pago":
            conta.id_cofrinho = None
        else:
            db.delete(conta)
    db.flush()
    db.delete(cofrinho)
    db.commit()
