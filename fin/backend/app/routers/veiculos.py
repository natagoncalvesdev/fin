from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Abastecimento, Manutencao, User, Veiculo

router = APIRouter(prefix="/api/veiculos", tags=["veiculos"])


class VeiculoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    kmInicial: float = Field(gt=0)


class AbastecimentoCreate(BaseModel):
    kmAtual: float
    litros: float
    valor: float
    kmRodado: float = 0
    kmPorLitro: float = 0
    mes: str
    ano: str
    data: datetime | None = None


class AbastecimentoUpdate(BaseModel):
    kmAtual: float | None = None
    litros: float | None = None
    valor: float | None = None
    kmRodado: float | None = None
    kmPorLitro: float | None = None
    mes: str | None = None
    ano: str | None = None
    data: datetime | None = None


class ManutencaoCreate(BaseModel):
    descricao: str
    valor: float
    tipo: str = "Preventiva"
    mes: str
    ano: str
    data: datetime | None = None


class ManutencaoUpdate(BaseModel):
    descricao: str | None = None
    valor: float | None = None
    tipo: str | None = None
    mes: str | None = None
    ano: str | None = None
    data: datetime | None = None


def get_veiculo_or_404(db: Session, veiculo_id: str, user_id: str) -> Veiculo:
    veiculo = db.get(Veiculo, veiculo_id)
    if not veiculo or veiculo.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Veículo não encontrado.")
    return veiculo


@router.get("")
def list_veiculos(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    items = db.query(Veiculo).filter(Veiculo.user_id == current_user.id).order_by(Veiculo.nome).all()
    return [{"id": v.id, "data": v.to_dict()} for v in items]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_veiculo(
    body: VeiculoCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = Veiculo(user_id=current_user.id, nome=body.nome.strip(), km_inicial=body.kmInicial)
    db.add(veiculo)
    db.commit()
    db.refresh(veiculo)
    return {"id": veiculo.id, "data": veiculo.to_dict()}


@router.delete("/{veiculo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_veiculo(
    veiculo_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user.id)
    db.delete(veiculo)
    db.commit()


@router.get("/{veiculo_id}/abastecimentos")
def list_abastecimentos(
    veiculo_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    ano: str | None = Query(default=None),
    mes: str | None = Query(default=None),
    order_by: str = Query(default="data"),
    order_dir: str = Query(default="desc"),
    limit: int | None = Query(default=None),
):
    get_veiculo_or_404(db, veiculo_id, current_user.id)
    query = db.query(Abastecimento).filter(Abastecimento.veiculo_id == veiculo_id)
    if ano:
        query = query.filter(Abastecimento.ano == ano)
    if mes:
        query = query.filter(Abastecimento.mes == mes)

    if order_by == "kmAtual":
        column = Abastecimento.km_atual
    else:
        column = Abastecimento.data

    query = query.order_by(column.desc() if order_dir == "desc" else column.asc())
    if limit:
        query = query.limit(limit)

    items = query.all()
    return [{"id": a.id, "data": a.to_dict()} for a in items]


@router.post("/{veiculo_id}/abastecimentos", status_code=status.HTTP_201_CREATED)
def create_abastecimento(
    veiculo_id: str,
    body: AbastecimentoCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    get_veiculo_or_404(db, veiculo_id, current_user.id)
    abastecimento = Abastecimento(
        veiculo_id=veiculo_id,
        km_atual=body.kmAtual,
        litros=body.litros,
        valor=body.valor,
        km_rodado=body.kmRodado,
        km_por_litro=body.kmPorLitro,
        mes=body.mes,
        ano=body.ano,
        data=body.data or datetime.utcnow(),
    )
    db.add(abastecimento)
    db.commit()
    db.refresh(abastecimento)
    return {"id": abastecimento.id, "data": abastecimento.to_dict()}


@router.put("/{veiculo_id}/abastecimentos/{abastecimento_id}")
def update_abastecimento(
    veiculo_id: str,
    abastecimento_id: str,
    body: AbastecimentoUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    get_veiculo_or_404(db, veiculo_id, current_user.id)
    abastecimento = db.get(Abastecimento, abastecimento_id)
    if not abastecimento or abastecimento.veiculo_id != veiculo_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Abastecimento não encontrado.")

    if body.kmAtual is not None:
        abastecimento.km_atual = body.kmAtual
    if body.litros is not None:
        abastecimento.litros = body.litros
    if body.valor is not None:
        abastecimento.valor = body.valor
    if body.kmRodado is not None:
        abastecimento.km_rodado = body.kmRodado
    if body.kmPorLitro is not None:
        abastecimento.km_por_litro = body.kmPorLitro
    if body.mes is not None:
        abastecimento.mes = body.mes
    if body.ano is not None:
        abastecimento.ano = body.ano
    if body.data is not None:
        abastecimento.data = body.data

    db.commit()
    db.refresh(abastecimento)
    return {"id": abastecimento.id, "data": abastecimento.to_dict()}


@router.delete("/{veiculo_id}/abastecimentos/{abastecimento_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_abastecimento(
    veiculo_id: str,
    abastecimento_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    get_veiculo_or_404(db, veiculo_id, current_user.id)
    abastecimento = db.get(Abastecimento, abastecimento_id)
    if not abastecimento or abastecimento.veiculo_id != veiculo_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Abastecimento não encontrado.")
    db.delete(abastecimento)
    db.commit()


@router.get("/{veiculo_id}/manutencoes")
def list_manutencoes(
    veiculo_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    ano: str | None = Query(default=None),
    mes: str | None = Query(default=None),
    order_dir: str = Query(default="desc"),
):
    get_veiculo_or_404(db, veiculo_id, current_user.id)
    query = db.query(Manutencao).filter(Manutencao.veiculo_id == veiculo_id)
    if ano:
        query = query.filter(Manutencao.ano == ano)
    if mes:
        query = query.filter(Manutencao.mes == mes)
    query = query.order_by(Manutencao.data.desc() if order_dir == "desc" else Manutencao.data.asc())
    items = query.all()
    return [{"id": m.id, "data": m.to_dict()} for m in items]


@router.post("/{veiculo_id}/manutencoes", status_code=status.HTTP_201_CREATED)
def create_manutencao(
    veiculo_id: str,
    body: ManutencaoCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    get_veiculo_or_404(db, veiculo_id, current_user.id)
    manutencao = Manutencao(
        veiculo_id=veiculo_id,
        descricao=body.descricao,
        valor=body.valor,
        tipo=body.tipo,
        mes=body.mes,
        ano=body.ano,
        data=body.data or datetime.utcnow(),
    )
    db.add(manutencao)
    db.commit()
    db.refresh(manutencao)
    return {"id": manutencao.id, "data": manutencao.to_dict()}


@router.put("/{veiculo_id}/manutencoes/{manutencao_id}")
def update_manutencao(
    veiculo_id: str,
    manutencao_id: str,
    body: ManutencaoUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    get_veiculo_or_404(db, veiculo_id, current_user.id)
    manutencao = db.get(Manutencao, manutencao_id)
    if not manutencao or manutencao.veiculo_id != veiculo_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manutenção não encontrada.")

    if body.descricao is not None:
        manutencao.descricao = body.descricao
    if body.valor is not None:
        manutencao.valor = body.valor
    if body.tipo is not None:
        manutencao.tipo = body.tipo
    if body.mes is not None:
        manutencao.mes = body.mes
    if body.ano is not None:
        manutencao.ano = body.ano
    if body.data is not None:
        manutencao.data = body.data

    db.commit()
    db.refresh(manutencao)
    return {"id": manutencao.id, "data": manutencao.to_dict()}


@router.delete("/{veiculo_id}/manutencoes/{manutencao_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_manutencao(
    veiculo_id: str,
    manutencao_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    get_veiculo_or_404(db, veiculo_id, current_user.id)
    manutencao = db.get(Manutencao, manutencao_id)
    if not manutencao or manutencao.veiculo_id != veiculo_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manutenção não encontrada.")
    db.delete(manutencao)
    db.commit()
