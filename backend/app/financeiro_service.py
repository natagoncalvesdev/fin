"""Serviço financeiro — dados por data, agrupados por mês na API."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import (
    MESES,
    Cartao,
    Categoria,
    CompraCartao,
    Conta,
    Debito,
    Entrada,
    FaturaCartao,
    Reservado,
    Usuario,
    periodo_mes,
)

MESES_DEFAULT: dict[str, Any] = {
    "contas": [],
    "adicionais": [],
    "cartao": [],
    "reservado": [],
    "debito": [],
    "cartaoStatus": "pendente",
}


@dataclass
class MesRef:
    """Referência a um mês financeiro do usuário."""

    id_usuario: int
    ano: int
    mes: str
    cartao_status: str = "pendente"


def _categoria_nome(cat: Categoria | None) -> str:
    return cat.nome if cat else ""


def _resolver_categoria(db: Session, id_usuario: int, nome: str) -> int | None:
    nome = (nome or "").strip()
    if not nome:
        return None
    cat = (
        db.query(Categoria)
        .filter(Categoria.id_usuario == id_usuario, Categoria.nome.ilike(nome))
        .first()
    )
    if cat:
        return cat.id
    nova = Categoria(id_usuario=id_usuario, nome=nome)
    db.add(nova)
    db.flush()
    return nova.id


def _resolver_cartao_id(db: Session, id_usuario: int, cartao_uuid: str) -> int | None:
    if not cartao_uuid:
        return None
    cartao = (
        db.query(Cartao)
        .filter(Cartao.uuid == cartao_uuid, Cartao.id_usuario == id_usuario)
        .first()
    )
    return cartao.id if cartao else None


def _parse_parcelas(parcelas: str) -> tuple[int, int]:
    if not parcelas or parcelas in ("À vista", "Recorrente"):
        return 1, 1
    match = re.match(r"^(\d+)\s*/\s*(\d+)$", parcelas.strip())
    if match:
        return int(match.group(1)), int(match.group(2))
    return 1, 1


def _format_parcelas(atual: int, total: int, recorrente: bool) -> str:
    if recorrente:
        return "Recorrente"
    if total <= 1:
        return "À vista"
    return f"{atual}/{total}"


def ano_tem_meses(db: Session, usuario: Usuario, ano: int) -> bool:
    uid = usuario.id
    inicio = date(ano, 1, 1)
    fim = date(ano + 1, 1, 1)

    if db.query(FaturaCartao.id).filter(FaturaCartao.id_usuario == uid, FaturaCartao.ano == ano).first():
        return True

    for model, col in (
        (Conta, Conta.data_conta),
        (Entrada, Entrada.data_entrada),
        (Debito, Debito.data_debito),
        (Reservado, Reservado.data_reservado),
        (CompraCartao, CompraCartao.data_competencia),
    ):
        if (
            db.query(model.id)
            .filter(model.id_usuario == uid, col >= inicio, col < fim)
            .first()
        ):
            return True
    return False


def get_or_create_mes(db: Session, usuario: Usuario, ano: int, mes: str) -> MesRef:
    fatura = (
        db.query(FaturaCartao)
        .filter(
            FaturaCartao.id_usuario == usuario.id,
            FaturaCartao.ano == ano,
            FaturaCartao.mes == mes,
        )
        .first()
    )
    if not fatura:
        fatura = FaturaCartao(id_usuario=usuario.id, ano=ano, mes=mes, situacao="pendente")
        db.add(fatura)
        db.commit()
        db.refresh(fatura)

    return MesRef(
        id_usuario=usuario.id,
        ano=ano,
        mes=mes,
        cartao_status=fatura.situacao,
    )


def init_ano_meses(db: Session, usuario: Usuario, ano: int) -> None:
    for mes in MESES:
        get_or_create_mes(db, usuario, ano, mes)


def _conta_to_dict(item: Conta) -> dict:
    return {
        "nome": item.nome,
        "valor": item.valor,
        "status": item.situacao,
        "categoria": _categoria_nome(item.categoria),
    }


def _entrada_to_dict(item: Entrada) -> dict:
    return {"nome": item.nome, "valor": item.valor}


def _debito_to_dict(item: Debito) -> dict:
    return {
        "nome": item.compra,
        "valor": item.valor,
        "categoria": _categoria_nome(item.categoria),
    }


def _reservado_to_dict(item: Reservado) -> dict:
    return {
        "nome": item.compra,
        "valor": item.valor,
        "categoria": _categoria_nome(item.categoria),
    }


def _compra_to_dict(item: CompraCartao) -> dict:
    data = {
        "nome": item.compra,
        "valor": item.valor,
        "parcelas": _format_parcelas(item.parcela_atual, item.parcela_total, item.recorrente),
        "cartaoId": item.cartao.uuid if item.cartao else "",
        "categoria": _categoria_nome(item.categoria),
    }
    if item.recorrente:
        data["recorrente"] = True
    return data


def mes_to_dict(db: Session, ref: MesRef) -> dict:
    uid = ref.id_usuario
    inicio, fim = periodo_mes(ref.ano, ref.mes)

    contas = [
        _conta_to_dict(c)
        for c in (
            db.query(Conta)
            .options(joinedload(Conta.categoria))
            .filter(Conta.id_usuario == uid, Conta.data_conta >= inicio, Conta.data_conta < fim)
            .order_by(Conta.id)
            .all()
        )
    ]
    adicionais = [
        _entrada_to_dict(e)
        for e in db.query(Entrada)
        .filter(Entrada.id_usuario == uid, Entrada.data_entrada >= inicio, Entrada.data_entrada < fim)
        .order_by(Entrada.id)
        .all()
    ]
    debito = [
        _debito_to_dict(d)
        for d in (
            db.query(Debito)
            .options(joinedload(Debito.categoria))
            .filter(Debito.id_usuario == uid, Debito.data_debito >= inicio, Debito.data_debito < fim)
            .order_by(Debito.id)
            .all()
        )
    ]
    reservado = [
        _reservado_to_dict(r)
        for r in (
            db.query(Reservado)
            .options(joinedload(Reservado.categoria))
            .filter(Reservado.id_usuario == uid, Reservado.data_reservado >= inicio, Reservado.data_reservado < fim)
            .order_by(Reservado.id)
            .all()
        )
    ]
    cartao = [
        _compra_to_dict(c)
        for c in (
            db.query(CompraCartao)
            .options(joinedload(CompraCartao.cartao), joinedload(CompraCartao.categoria))
            .filter(
                CompraCartao.id_usuario == uid,
                CompraCartao.data_competencia >= inicio,
                CompraCartao.data_competencia < fim,
            )
            .order_by(CompraCartao.id)
            .all()
        )
    ]

    fatura = (
        db.query(FaturaCartao)
        .filter(
            FaturaCartao.id_usuario == uid,
            FaturaCartao.ano == ref.ano,
            FaturaCartao.mes == ref.mes,
        )
        .first()
    )

    return {
        "contas": contas,
        "adicionais": adicionais,
        "cartao": cartao,
        "reservado": reservado,
        "debito": debito,
        "cartaoStatus": fatura.situacao if fatura else ref.cartao_status,
    }


def _items_equal(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(
        b, sort_keys=True, ensure_ascii=False
    )


def _is_init_wipe_payload(data: dict[str, Any]) -> bool:
    return (
        not (data.get("contas") or [])
        and not (data.get("adicionais") or [])
        and not (data.get("cartao") or [])
        and not (data.get("debito") or [])
        and not (data.get("reservado") or [])
        and data.get("cartaoStatus", "pendente") == "pendente"
    )


def _mes_tem_dados(db: Session, ref: MesRef) -> bool:
    uid = ref.id_usuario
    inicio, fim = periodo_mes(ref.ano, ref.mes)
    checks = [
        (Conta, Conta.data_conta),
        (Entrada, Entrada.data_entrada),
        (Debito, Debito.data_debito),
        (Reservado, Reservado.data_reservado),
        (CompraCartao, CompraCartao.data_competencia),
    ]
    for model, col in checks:
        if db.query(model.id).filter(model.id_usuario == uid, col >= inicio, col < fim).first():
            return True
    return False


def _replace_contas(db: Session, ref: MesRef, items: list) -> None:
    uid = ref.id_usuario
    inicio, fim = periodo_mes(ref.ano, ref.mes)
    db.query(Conta).filter(
        Conta.id_usuario == uid, Conta.data_conta >= inicio, Conta.data_conta < fim
    ).delete()
    for item in items:
        db.add(
            Conta(
                id_usuario=uid,
                id_categoria=_resolver_categoria(db, uid, item.get("categoria", "")),
                data_conta=inicio,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                situacao=item.get("status", "pendente"),
            )
        )


def _replace_entradas(db: Session, ref: MesRef, items: list) -> None:
    uid = ref.id_usuario
    inicio, fim = periodo_mes(ref.ano, ref.mes)
    db.query(Entrada).filter(
        Entrada.id_usuario == uid, Entrada.data_entrada >= inicio, Entrada.data_entrada < fim
    ).delete()
    for item in items:
        db.add(
            Entrada(
                id_usuario=uid,
                data_entrada=inicio,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
            )
        )


def _replace_debito(db: Session, ref: MesRef, items: list) -> None:
    uid = ref.id_usuario
    inicio, fim = periodo_mes(ref.ano, ref.mes)
    db.query(Debito).filter(
        Debito.id_usuario == uid, Debito.data_debito >= inicio, Debito.data_debito < fim
    ).delete()
    for item in items:
        db.add(
            Debito(
                id_usuario=uid,
                data_debito=inicio,
                id_categoria=_resolver_categoria(db, uid, item.get("categoria", "")),
                compra=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
            )
        )


def _replace_reservado(db: Session, ref: MesRef, items: list) -> None:
    uid = ref.id_usuario
    inicio, fim = periodo_mes(ref.ano, ref.mes)
    db.query(Reservado).filter(
        Reservado.id_usuario == uid, Reservado.data_reservado >= inicio, Reservado.data_reservado < fim
    ).delete()
    for item in items:
        db.add(
            Reservado(
                id_usuario=uid,
                data_reservado=inicio,
                id_categoria=_resolver_categoria(db, uid, item.get("categoria", "")),
                compra=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
            )
        )


def _replace_cartao(db: Session, ref: MesRef, items: list) -> None:
    uid = ref.id_usuario
    inicio, fim = periodo_mes(ref.ano, ref.mes)
    db.query(CompraCartao).filter(
        CompraCartao.id_usuario == uid,
        CompraCartao.data_competencia >= inicio,
        CompraCartao.data_competencia < fim,
    ).delete()
    for item in items:
        cartao_id = _resolver_cartao_id(db, uid, item.get("cartaoId", ""))
        if not cartao_id:
            continue
        parcela_atual, parcela_total = _parse_parcelas(item.get("parcelas", "À vista"))
        recorrente = bool(item.get("recorrente", False))
        db.add(
            CompraCartao(
                id_usuario=uid,
                id_cartao=cartao_id,
                data_compra_cartao=inicio,
                data_competencia=inicio,
                id_categoria=_resolver_categoria(db, uid, item.get("categoria", "")),
                compra=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                parcela_atual=parcela_atual,
                parcela_total=parcela_total,
                recorrente=recorrente,
            )
        )


def _update_fatura_status(db: Session, ref: MesRef, status: str) -> None:
    fatura = (
        db.query(FaturaCartao)
        .filter(
            FaturaCartao.id_usuario == ref.id_usuario,
            FaturaCartao.ano == ref.ano,
            FaturaCartao.mes == ref.mes,
        )
        .first()
    )
    if fatura:
        fatura.situacao = status
    else:
        db.add(
            FaturaCartao(
                id_usuario=ref.id_usuario,
                ano=ref.ano,
                mes=ref.mes,
                situacao=status,
            )
        )


def apply_mes_data(db: Session, ref: MesRef, data: dict[str, Any]) -> None:
    if _is_init_wipe_payload(data) and _mes_tem_dados(db, ref):
        return

    if "contas" in data:
        _replace_contas(db, ref, data["contas"] or [])
    if "adicionais" in data:
        _replace_entradas(db, ref, data["adicionais"] or [])
    if "debito" in data:
        _replace_debito(db, ref, data["debito"] or [])
    if "reservado" in data:
        _replace_reservado(db, ref, data["reservado"] or [])
    if "cartao" in data:
        _replace_cartao(db, ref, data["cartao"] or [])
    if "cartaoStatus" in data:
        _update_fatura_status(db, ref, data["cartaoStatus"])


def list_meses_ano(db: Session, usuario: Usuario, ano: int) -> list[MesRef]:
    faturas = (
        db.query(FaturaCartao)
        .filter(FaturaCartao.id_usuario == usuario.id, FaturaCartao.ano == ano)
        .all()
    )
    fatura_por_mes = {f.mes: f for f in faturas}

    refs: list[MesRef] = []
    for mes in MESES:
        fatura = fatura_por_mes.get(mes)
        ref = MesRef(
            id_usuario=usuario.id,
            ano=ano,
            mes=mes,
            cartao_status=fatura.situacao if fatura else "pendente",
        )
        if fatura or _mes_tem_dados(db, ref):
            refs.append(ref)
    return refs
