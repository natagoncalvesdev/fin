from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ManutencaoVeiculo, MESES, Usuario, Veiculo, VeiculoAbastecimento, VeiculoHistorico

router = APIRouter(prefix="/api/veiculos", tags=["veiculos"])


class VeiculoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    kmInicial: float = Field(gt=0)
    placa: str | None = None


class AbastecimentoCreate(BaseModel):
    kmAtual: float
    litros: float
    valor: float
    kmRodado: float = 0
    kmPorLitro: float = 0
    mes: str
    ano: str
    data: datetime | None = None
    tipoCombustivel: str | None = None


class AbastecimentoUpdate(BaseModel):
    kmAtual: float | None = None
    litros: float | None = None
    valor: float | None = None
    kmRodado: float | None = None
    kmPorLitro: float | None = None
    mes: str | None = None
    ano: str | None = None
    data: datetime | None = None
    tipoCombustivel: str | None = None


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


def _get_veiculo(db: Session, veiculo_uuid: str, usuario: Usuario) -> Veiculo | None:
    return (
        db.query(Veiculo)
        .filter(Veiculo.uuid == veiculo_uuid, Veiculo.id_usuario == usuario.id)
        .first()
    )


def get_veiculo_or_404(db: Session, veiculo_id: str, usuario: Usuario) -> Veiculo:
    veiculo = _get_veiculo(db, veiculo_id, usuario)
    if not veiculo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Veículo não encontrado.")
    return veiculo


def _get_abastecimento(db: Session, abastecimento_uuid: str, veiculo: Veiculo) -> VeiculoAbastecimento | None:
    return (
        db.query(VeiculoAbastecimento)
        .filter(
            VeiculoAbastecimento.uuid == abastecimento_uuid,
            VeiculoAbastecimento.id_veiculo == veiculo.id,
        )
        .first()
    )


def _get_manutencao(db: Session, manutencao_uuid: str, veiculo: Veiculo) -> ManutencaoVeiculo | None:
    return (
        db.query(ManutencaoVeiculo)
        .filter(
            ManutencaoVeiculo.uuid == manutencao_uuid,
            ManutencaoVeiculo.id_veiculo == veiculo.id,
        )
        .first()
    )


@router.get("")
def list_veiculos(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    items = (
        db.query(Veiculo)
        .filter(Veiculo.id_usuario == current_user.id)
        .order_by(Veiculo.nome)
        .all()
    )
    return [{"id": v.uuid, "data": v.to_dict()} for v in items]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_veiculo(
    body: VeiculoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = Veiculo(
        id_usuario=current_user.id,
        nome=body.nome.strip(),
        placa=(body.placa or "").strip() or None,
        km_inicial=body.kmInicial,
    )
    db.add(veiculo)
    db.flush()
    db.add(
        VeiculoHistorico(
            id_veiculo=veiculo.id,
            ultima_quilometragem=body.kmInicial,
        )
    )
    db.commit()
    db.refresh(veiculo)
    return {"id": veiculo.uuid, "data": veiculo.to_dict()}


@router.delete("/{veiculo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_veiculo(
    veiculo_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user)
    db.delete(veiculo)
    db.commit()


@router.get("/{veiculo_id}/abastecimentos")
def list_abastecimentos(
    veiculo_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    ano: str | None = Query(default=None),
    mes: str | None = Query(default=None),
    order_by: str = Query(default="data"),
    order_dir: str = Query(default="desc"),
    limit: int | None = Query(default=None),
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user)
    query = db.query(VeiculoAbastecimento).filter(VeiculoAbastecimento.id_veiculo == veiculo.id)

    if ano:
        query = query.filter(
            VeiculoAbastecimento.data_abastecimento >= datetime(int(ano), 1, 1),
            VeiculoAbastecimento.data_abastecimento < datetime(int(ano) + 1, 1, 1),
        )
    if mes and mes in MESES:
        mes_idx = MESES.index(mes) + 1
        year = int(ano) if ano else datetime.utcnow().year
        start = datetime(year, mes_idx, 1)
        end = datetime(year + 1, 1, 1) if mes_idx == 12 else datetime(year, mes_idx + 1, 1)
        query = query.filter(
            VeiculoAbastecimento.data_abastecimento >= start,
            VeiculoAbastecimento.data_abastecimento < end,
        )

    column = (
        VeiculoAbastecimento.quilometragem_atual
        if order_by == "kmAtual"
        else VeiculoAbastecimento.data_abastecimento
    )
    query = query.order_by(column.desc() if order_dir == "desc" else column.asc())
    if limit:
        query = query.limit(limit)

    items = query.all()
    return [{"id": a.uuid, "data": a.to_dict()} for a in items]


@router.post("/{veiculo_id}/abastecimentos", status_code=status.HTTP_201_CREATED)
def create_abastecimento(
    veiculo_id: str,
    body: AbastecimentoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user)
    dt = body.data or datetime.utcnow()
    abastecimento = VeiculoAbastecimento(
        id_veiculo=veiculo.id,
        quilometragem_atual=body.kmAtual,
        litros_abastecido=body.litros,
        valor_abastecido=body.valor,
        tipo_combustivel=body.tipoCombustivel,
        data_abastecimento=dt,
    )
    db.add(abastecimento)
    db.add(
        VeiculoHistorico(
            id_veiculo=veiculo.id,
            ultima_quilometragem=body.kmAtual,
        )
    )
    db.commit()
    db.refresh(abastecimento)
    result = abastecimento.to_dict()
    result["kmRodado"] = body.kmRodado
    result["kmPorLitro"] = body.kmPorLitro
    return {"id": abastecimento.uuid, "data": result}


@router.put("/{veiculo_id}/abastecimentos/{abastecimento_id}")
def update_abastecimento(
    veiculo_id: str,
    abastecimento_id: str,
    body: AbastecimentoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user)
    abastecimento = _get_abastecimento(db, abastecimento_id, veiculo)
    if not abastecimento:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Abastecimento não encontrado.")

    if body.kmAtual is not None:
        abastecimento.quilometragem_atual = body.kmAtual
    if body.litros is not None:
        abastecimento.litros_abastecido = body.litros
    if body.valor is not None:
        abastecimento.valor_abastecido = body.valor
    if body.tipoCombustivel is not None:
        abastecimento.tipo_combustivel = body.tipoCombustivel
    if body.data is not None:
        abastecimento.data_abastecimento = body.data
    elif body.mes is not None or body.ano is not None:
        dt = abastecimento.data_abastecimento
        mes_nome = body.mes or MESES[dt.month - 1]
        ano_val = int(body.ano) if body.ano else dt.year
        mes_idx = MESES.index(mes_nome) + 1
        abastecimento.data_abastecimento = dt.replace(year=ano_val, month=mes_idx)

    if body.kmAtual is not None:
        db.add(
            VeiculoHistorico(
                id_veiculo=veiculo.id,
                ultima_quilometragem=body.kmAtual,
            )
        )

    db.commit()
    db.refresh(abastecimento)
    result = abastecimento.to_dict()
    if body.kmRodado is not None:
        result["kmRodado"] = body.kmRodado
    if body.kmPorLitro is not None:
        result["kmPorLitro"] = body.kmPorLitro
    return {"id": abastecimento.uuid, "data": result}


@router.delete("/{veiculo_id}/abastecimentos/{abastecimento_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_abastecimento(
    veiculo_id: str,
    abastecimento_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user)
    abastecimento = _get_abastecimento(db, abastecimento_id, veiculo)
    if not abastecimento:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Abastecimento não encontrado.")
    db.delete(abastecimento)
    db.commit()


@router.get("/{veiculo_id}/manutencoes")
def list_manutencoes(
    veiculo_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    ano: str | None = Query(default=None),
    mes: str | None = Query(default=None),
    order_dir: str = Query(default="desc"),
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user)
    query = db.query(ManutencaoVeiculo).filter(ManutencaoVeiculo.id_veiculo == veiculo.id)

    if ano:
        query = query.filter(
            ManutencaoVeiculo.data_manutencao >= datetime(int(ano), 1, 1),
            ManutencaoVeiculo.data_manutencao < datetime(int(ano) + 1, 1, 1),
        )
    if mes and mes in MESES:
        mes_idx = MESES.index(mes) + 1
        year = int(ano) if ano else datetime.utcnow().year
        start = datetime(year, mes_idx, 1)
        end = datetime(year + 1, 1, 1) if mes_idx == 12 else datetime(year, mes_idx + 1, 1)
        query = query.filter(
            ManutencaoVeiculo.data_manutencao >= start,
            ManutencaoVeiculo.data_manutencao < end,
        )

    query = query.order_by(
        ManutencaoVeiculo.data_manutencao.desc()
        if order_dir == "desc"
        else ManutencaoVeiculo.data_manutencao.asc()
    )
    items = query.all()
    return [{"id": m.uuid, "data": m.to_dict()} for m in items]


@router.post("/{veiculo_id}/manutencoes", status_code=status.HTTP_201_CREATED)
def create_manutencao(
    veiculo_id: str,
    body: ManutencaoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user)
    manutencao = ManutencaoVeiculo(
        id_veiculo=veiculo.id,
        descricao=body.descricao,
        valor_manutencao=body.valor,
        tipo=body.tipo,
        data_manutencao=body.data or datetime.utcnow(),
    )
    db.add(manutencao)
    db.commit()
    db.refresh(manutencao)
    return {"id": manutencao.uuid, "data": manutencao.to_dict()}


@router.put("/{veiculo_id}/manutencoes/{manutencao_id}")
def update_manutencao(
    veiculo_id: str,
    manutencao_id: str,
    body: ManutencaoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user)
    manutencao = _get_manutencao(db, manutencao_id, veiculo)
    if not manutencao:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manutenção não encontrada.")

    if body.descricao is not None:
        manutencao.descricao = body.descricao
    if body.valor is not None:
        manutencao.valor_manutencao = body.valor
    if body.tipo is not None:
        manutencao.tipo = body.tipo
    if body.data is not None:
        manutencao.data_manutencao = body.data
    elif body.mes is not None or body.ano is not None:
        dt = manutencao.data_manutencao
        mes_nome = body.mes or MESES[dt.month - 1]
        ano_val = int(body.ano) if body.ano else dt.year
        mes_idx = MESES.index(mes_nome) + 1
        manutencao.data_manutencao = dt.replace(year=ano_val, month=mes_idx)

    db.commit()
    db.refresh(manutencao)
    return {"id": manutencao.uuid, "data": manutencao.to_dict()}


@router.delete("/{veiculo_id}/manutencoes/{manutencao_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_manutencao(
    veiculo_id: str,
    manutencao_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    veiculo = get_veiculo_or_404(db, veiculo_id, current_user)
    manutencao = _get_manutencao(db, manutencao_id, veiculo)
    if not manutencao:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manutenção não encontrada.")
    db.delete(manutencao)
    db.commit()
