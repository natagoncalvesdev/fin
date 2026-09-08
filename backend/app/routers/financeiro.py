from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.financeiro_service import (
    ano_tem_meses,
    atualizar_compra_cartao,
    atualizar_conta,
    atualizar_debito,
    atualizar_entrada,
    atualizar_reservado,
    atualizar_status_fatura,
    compra_to_dict,
    conta_to_dict,
    criar_conta,
    criar_debito,
    criar_entrada,
    criar_reservado,
    debito_to_dict,
    entrada_to_dict,
    init_ano_meses,
    inserir_compra_cartao,
    list_meses_ano,
    mes_ref_somente_leitura,
    mes_to_dict,
    resumo_ano,
    mover_compra_cartao,
    remover_compra_cartao,
    remover_conta,
    remover_debito,
    remover_entrada,
    remover_reservado,
    reservado_to_dict,
)
from app import cofrinhos_service
from app.models import MESES, Cofrinho, CofrinhoParticipante, Conta, Usuario, periodo_mes

router = APIRouter(prefix="/api/financeiro", tags=["financeiro"])


def _repercutir_no_cofrinho(db: Session, usuario: Usuario, id_cofrinho: int | None) -> None:
    """Uma parcela de cofrinho foi paga/editada/removida na tela de Contas —
    redistribui as pendentes e reavalia a conclusão do cofrinho. Vale tanto para
    o dono quanto para um participante ativo de uma caixinha compartilhada."""
    if not id_cofrinho:
        return
    cofrinho = db.query(Cofrinho).filter(Cofrinho.id == id_cofrinho).first()
    if not cofrinho:
        return
    if cofrinho.id_usuario != usuario.id:
        participa = (
            db.query(CofrinhoParticipante)
            .filter(
                CofrinhoParticipante.id_cofrinho == cofrinho.id,
                CofrinhoParticipante.id_usuario == usuario.id,
                CofrinhoParticipante.situacao == "ativo",
            )
            .first()
        )
        if not participa:
            return
    cofrinhos_service.apos_mudanca_conta(db, cofrinho)


class ItemResponse(BaseModel):
    id: str
    data: dict[str, Any]


def _checar_mes(mes: str) -> None:
    if mes not in MESES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mês inválido.")


def _not_found(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


class StatusFaturaUpdate(BaseModel):
    status: str


@router.get("/anos/{ano}/exists")
def ano_exists(
    ano: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return {"exists": ano_tem_meses(db, current_user, ano), "ano": ano}


@router.post("/anos/{ano}/init")
def init_ano(
    ano: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    init_ano_meses(db, current_user, ano)
    return {"ok": True, "ano": ano}


@router.get("/anos/{ano}/resumo")
def get_resumo_ano(
    ano: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Ano inteiro numa requisição — usado pelo relatório e pelo resumo anual."""
    return {"ano": ano, "meses": resumo_ano(db, current_user, ano)}


@router.get("/anos/{ano}/meses/{mes}")
def get_mes(
    ano: int,
    mes: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(mes)
    ref = mes_ref_somente_leitura(db, current_user, ano, mes)
    return {"id": f"{ano}_{mes}", "data": mes_to_dict(db, ref), "exists": True}


@router.put("/anos/{ano}/meses/{mes}/status-fatura")
def update_status_fatura(
    ano: int,
    mes: str,
    body: StatusFaturaUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(mes)
    atualizar_status_fatura(db, current_user, ano, mes, body.status)
    db.commit()
    return {"ok": True, "status": body.status}


@router.get("/anos/{ano}/meses")
def list_meses_ano_endpoint(
    ano: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    refs = list_meses_ano(db, current_user, ano)
    return [{"mes": r.mes, "data": mes_to_dict(db, r)} for r in refs]


# ---------------------------------------------------------------------------
# Escrita granular por item — cada chamada é um INSERT/UPDATE/DELETE atômico
# de uma linha (por uuid), sem a race condition de leitura-modificação-escrita
# que existia no antigo PUT do mês inteiro.
# ---------------------------------------------------------------------------


class ContaCreate(BaseModel):
    ano: int
    mes: str
    nome: str = Field(min_length=1, max_length=255)
    valor: float = Field(gt=0)
    status: str = "pendente"
    categoria: str = ""


class ContaUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=255)
    valor: float | None = Field(default=None, gt=0)
    status: str | None = None
    categoria: str | None = None


@router.post("/contas", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_conta(
    body: ContaCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(body.mes)
    item = criar_conta(
        db,
        current_user,
        ano=body.ano,
        mes=body.mes,
        nome=body.nome.strip(),
        valor=body.valor,
        status=body.status,
        categoria=body.categoria,
    )
    db.commit()
    return ItemResponse(id=item.uuid, data=conta_to_dict(item))


@router.put("/contas/{item_id}", response_model=ItemResponse)
def update_conta(
    item_id: str,
    body: ContaUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        item = atualizar_conta(
            db,
            current_user,
            item_id,
            nome=body.nome.strip() if body.nome is not None else None,
            valor=body.valor,
            status=body.status,
            categoria=body.categoria,
        )
    except ValueError as exc:
        raise _not_found(exc) from exc
    _repercutir_no_cofrinho(db, current_user, item.id_cofrinho)
    db.commit()
    return ItemResponse(id=item.uuid, data=conta_to_dict(item))


@router.delete("/contas/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conta(
    item_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    alvo = (
        db.query(Conta)
        .filter(Conta.uuid == item_id, Conta.id_usuario == current_user.id)
        .first()
    )
    id_cofrinho = alvo.id_cofrinho if alvo else None
    try:
        remover_conta(db, current_user, item_id)
    except ValueError as exc:
        raise _not_found(exc) from exc
    _repercutir_no_cofrinho(db, current_user, id_cofrinho)
    db.commit()


class EntradaCreate(BaseModel):
    ano: int
    mes: str
    nome: str = Field(min_length=1, max_length=255)
    valor: float = Field(gt=0)


class EntradaUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=255)
    valor: float | None = Field(default=None, gt=0)


@router.post("/entradas", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_entrada(
    body: EntradaCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(body.mes)
    item = criar_entrada(db, current_user, ano=body.ano, mes=body.mes, nome=body.nome.strip(), valor=body.valor)
    db.commit()
    return ItemResponse(id=item.uuid, data=entrada_to_dict(item))


@router.put("/entradas/{item_id}", response_model=ItemResponse)
def update_entrada(
    item_id: str,
    body: EntradaUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        item = atualizar_entrada(
            db, current_user, item_id, nome=body.nome.strip() if body.nome is not None else None, valor=body.valor
        )
    except ValueError as exc:
        raise _not_found(exc) from exc
    db.commit()
    return ItemResponse(id=item.uuid, data=entrada_to_dict(item))


@router.delete("/entradas/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entrada(
    item_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        remover_entrada(db, current_user, item_id)
    except ValueError as exc:
        raise _not_found(exc) from exc
    db.commit()


class DebitoCreate(BaseModel):
    ano: int
    mes: str
    nome: str = Field(min_length=1, max_length=255)
    valor: float = Field(gt=0)
    categoria: str = ""


class DebitoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=255)
    valor: float | None = Field(default=None, gt=0)
    categoria: str | None = None


@router.post("/debitos", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_debito(
    body: DebitoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(body.mes)
    item = criar_debito(
        db, current_user, ano=body.ano, mes=body.mes, nome=body.nome.strip(), valor=body.valor, categoria=body.categoria
    )
    db.commit()
    return ItemResponse(id=item.uuid, data=debito_to_dict(item))


@router.put("/debitos/{item_id}", response_model=ItemResponse)
def update_debito(
    item_id: str,
    body: DebitoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        item = atualizar_debito(
            db,
            current_user,
            item_id,
            nome=body.nome.strip() if body.nome is not None else None,
            valor=body.valor,
            categoria=body.categoria,
        )
    except ValueError as exc:
        raise _not_found(exc) from exc
    db.commit()
    return ItemResponse(id=item.uuid, data=debito_to_dict(item))


@router.delete("/debitos/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_debito(
    item_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        remover_debito(db, current_user, item_id)
    except ValueError as exc:
        raise _not_found(exc) from exc
    db.commit()


class ReservadoCreate(BaseModel):
    ano: int
    mes: str
    nome: str = Field(min_length=1, max_length=255)
    valor: float = Field(gt=0)
    categoria: str = ""


class ReservadoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=255)
    valor: float | None = Field(default=None, gt=0)
    categoria: str | None = None


@router.post("/reservados", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_reservado(
    body: ReservadoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(body.mes)
    item = criar_reservado(
        db, current_user, ano=body.ano, mes=body.mes, nome=body.nome.strip(), valor=body.valor, categoria=body.categoria
    )
    db.commit()
    return ItemResponse(id=item.uuid, data=reservado_to_dict(item))


@router.put("/reservados/{item_id}", response_model=ItemResponse)
def update_reservado(
    item_id: str,
    body: ReservadoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        item = atualizar_reservado(
            db,
            current_user,
            item_id,
            nome=body.nome.strip() if body.nome is not None else None,
            valor=body.valor,
            categoria=body.categoria,
        )
    except ValueError as exc:
        raise _not_found(exc) from exc
    db.commit()
    return ItemResponse(id=item.uuid, data=reservado_to_dict(item))


@router.delete("/reservados/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reservado(
    item_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        remover_reservado(db, current_user, item_id)
    except ValueError as exc:
        raise _not_found(exc) from exc
    db.commit()


class CompraCartaoCreate(BaseModel):
    ano: int
    mes: str
    nome: str = Field(min_length=1, max_length=255)
    valor: float = Field(gt=0)
    cartaoId: str = Field(min_length=1)
    categoria: str = ""
    totalParcelas: int = Field(default=1, ge=1, le=48)
    recorrente: bool = False


class CompraCartaoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=255)
    valor: float | None = Field(default=None, gt=0)
    categoria: str | None = None


class CompraCartaoMover(BaseModel):
    ano: int
    mes: str


class ComprasCartaoResponse(BaseModel):
    criadas: int
    itens: list[ItemResponse]


@router.post("/compras-cartao", response_model=ComprasCartaoResponse, status_code=status.HTTP_201_CREATED)
def create_compra_cartao(
    body: CompraCartaoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(body.mes)
    inicio, _ = periodo_mes(body.ano, body.mes)
    try:
        resultado = inserir_compra_cartao(
            db,
            current_user,
            data_lanc=inicio,
            descricao=body.nome.strip(),
            valor=body.valor,
            categoria=body.categoria,
            cartao_id=body.cartaoId,
            total_parcelas=body.totalParcelas,
            recorrente=body.recorrente,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    db.commit()
    registros = resultado["registros"]
    return ComprasCartaoResponse(
        criadas=len(registros),
        itens=[ItemResponse(id=r.uuid, data=compra_to_dict(r)) for r in registros],
    )


@router.put("/compras-cartao/{item_id}", response_model=ItemResponse)
def update_compra_cartao(
    item_id: str,
    body: CompraCartaoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        item = atualizar_compra_cartao(
            db,
            current_user,
            item_id,
            nome=body.nome.strip() if body.nome is not None else None,
            valor=body.valor,
            categoria=body.categoria,
        )
    except ValueError as exc:
        raise _not_found(exc) from exc
    db.commit()
    return ItemResponse(id=item.uuid, data=compra_to_dict(item))


@router.put("/compras-cartao/{item_id}/mover", response_model=ItemResponse)
def move_compra_cartao(
    item_id: str,
    body: CompraCartaoMover,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(body.mes)
    try:
        item = mover_compra_cartao(db, current_user, item_id, ano=body.ano, mes=body.mes)
    except ValueError as exc:
        raise _not_found(exc) from exc
    db.commit()
    return ItemResponse(id=item.uuid, data=compra_to_dict(item))


@router.delete("/compras-cartao/{item_id}", status_code=status.HTTP_200_OK)
def delete_compra_cartao(
    item_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    futuras: bool = False,
):
    try:
        removidas = remover_compra_cartao(db, current_user, item_id, futuras=futuras)
    except ValueError as exc:
        raise _not_found(exc) from exc
    db.commit()
    return {"ok": True, "removidas": removidas}
