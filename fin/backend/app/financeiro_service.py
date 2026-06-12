import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    AdicionalFinanceiro,
    CompraCartao,
    ContaFinanceira,
    DebitoFinanceiro,
    MesFinanceiro,
    ReservadoFinanceiro,
    ValeCarga,
)

MESES_DEFAULT = {
    "contas": [],
    "adicionais": [],
    "cartao": [],
    "reservado": [],
    "debito": [],
    "cartaoStatus": "pendente",
    "valeCarga": {},
}


def ano_tem_meses(db: Session, user_id: str, ano: int) -> bool:
    return (
        db.query(MesFinanceiro.id)
        .filter(MesFinanceiro.user_id == user_id, MesFinanceiro.ano == ano)
        .first()
        is not None
    )


def _mes_has_contas(db: Session, mes_id: int, user_id: str) -> bool:
    return (
        db.query(ContaFinanceira.id)
        .filter(ContaFinanceira.mes_id == mes_id, ContaFinanceira.user_id == user_id)
        .first()
        is not None
    )


def _mes_has_adicionais(db: Session, mes_id: int, user_id: str) -> bool:
    return (
        db.query(AdicionalFinanceiro.id)
        .filter(AdicionalFinanceiro.mes_id == mes_id, AdicionalFinanceiro.user_id == user_id)
        .first()
        is not None
    )


def _mes_has_debito(db: Session, mes_id: int, user_id: str) -> bool:
    return (
        db.query(DebitoFinanceiro.id)
        .filter(DebitoFinanceiro.mes_id == mes_id, DebitoFinanceiro.user_id == user_id)
        .first()
        is not None
    )


def _mes_has_reservado(db: Session, mes_id: int, user_id: str) -> bool:
    return (
        db.query(ReservadoFinanceiro.id)
        .filter(ReservadoFinanceiro.mes_id == mes_id, ReservadoFinanceiro.user_id == user_id)
        .first()
        is not None
    )


def _mes_has_cartao(db: Session, mes_id: int, user_id: str) -> bool:
    return (
        db.query(CompraCartao.id)
        .filter(CompraCartao.mes_id == mes_id, CompraCartao.user_id == user_id)
        .first()
        is not None
    )


def _mes_has_vale(db: Session, mes_id: int, user_id: str) -> bool:
    return (
        db.query(ValeCarga.id)
        .filter(ValeCarga.mes_id == mes_id, ValeCarga.user_id == user_id)
        .first()
        is not None
    )


def _is_init_wipe_payload(data: dict[str, Any]) -> bool:
    return (
        not (data.get("contas") or [])
        and not (data.get("adicionais") or [])
        and not (data.get("cartao") or [])
        and not (data.get("debito") or [])
        and not (data.get("reservado") or [])
        and not (data.get("valeCarga") or {})
        and data.get("cartaoStatus", "pendente") == "pendente"
    )


def get_or_create_mes(db: Session, user_id: str, ano: int, mes: str) -> MesFinanceiro:
    record = (
        db.query(MesFinanceiro)
        .filter(MesFinanceiro.user_id == user_id, MesFinanceiro.ano == ano, MesFinanceiro.mes == mes)
        .first()
    )
    if record:
        migrate_legacy_json_if_needed(db, record)
        return record

    record = MesFinanceiro(
        user_id=user_id,
        ano=ano,
        mes=mes,
        cartao_status="pendente",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def init_ano_meses(db: Session, user_id: str, ano: int) -> None:
    from app.models import MESES

    for mes in MESES:
        get_or_create_mes(db, user_id, ano, mes)


def _items_equal(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(
        b, sort_keys=True, ensure_ascii=False
    )


def _conta_to_dict(item: ContaFinanceira) -> dict:
    return {
        "nome": item.nome,
        "valor": item.valor,
        "status": item.status,
        "categoria": item.categoria or "",
    }


def _adicional_to_dict(item: AdicionalFinanceiro) -> dict:
    return {"nome": item.nome, "valor": item.valor}


def _debito_to_dict(item: DebitoFinanceiro) -> dict:
    return {
        "nome": item.nome,
        "valor": item.valor,
        "categoria": item.categoria or "",
    }


def _reservado_to_dict(item: ReservadoFinanceiro) -> dict:
    return {
        "nome": item.nome,
        "valor": item.valor,
        "categoria": item.categoria or "",
    }


def _compra_to_dict(item: CompraCartao) -> dict:
    data = {
        "nome": item.nome,
        "valor": item.valor,
        "parcelas": item.parcelas,
        "cartaoId": item.cartao_id,
        "categoria": item.categoria or "",
    }
    if item.recorrente:
        data["recorrente"] = True
    return data


def mes_to_dict(db: Session, record: MesFinanceiro) -> dict:
    migrate_legacy_json_if_needed(db, record)
    uid = record.user_id
    mid = record.id

    contas = [
        _conta_to_dict(c)
        for c in db.query(ContaFinanceira)
        .filter(ContaFinanceira.mes_id == mid, ContaFinanceira.user_id == uid)
        .order_by(ContaFinanceira.id)
        .all()
    ]
    adicionais = [
        _adicional_to_dict(a)
        for a in db.query(AdicionalFinanceiro)
        .filter(AdicionalFinanceiro.mes_id == mid, AdicionalFinanceiro.user_id == uid)
        .order_by(AdicionalFinanceiro.id)
        .all()
    ]
    debito = [
        _debito_to_dict(d)
        for d in db.query(DebitoFinanceiro)
        .filter(DebitoFinanceiro.mes_id == mid, DebitoFinanceiro.user_id == uid)
        .order_by(DebitoFinanceiro.id)
        .all()
    ]
    reservado = [
        _reservado_to_dict(r)
        for r in db.query(ReservadoFinanceiro)
        .filter(ReservadoFinanceiro.mes_id == mid, ReservadoFinanceiro.user_id == uid)
        .order_by(ReservadoFinanceiro.id)
        .all()
    ]
    cartao = [
        _compra_to_dict(c)
        for c in db.query(CompraCartao)
        .filter(CompraCartao.mes_id == mid, CompraCartao.user_id == uid)
        .order_by(CompraCartao.id)
        .all()
    ]
    vale_cargas = (
        db.query(ValeCarga)
        .filter(ValeCarga.mes_id == mid, ValeCarga.user_id == uid)
        .all()
    )
    vale_carga = {vc.cartao_id: vc.valor for vc in vale_cargas}

    return {
        "contas": contas,
        "adicionais": adicionais,
        "cartao": cartao,
        "reservado": reservado,
        "debito": debito,
        "cartaoStatus": record.cartao_status,
        "valeCarga": vale_carga,
    }


def _has_normalized_data(db: Session, mes_id: int, user_id: str) -> bool:
    return (
        _mes_has_contas(db, mes_id, user_id)
        or _mes_has_adicionais(db, mes_id, user_id)
        or _mes_has_debito(db, mes_id, user_id)
        or _mes_has_reservado(db, mes_id, user_id)
        or _mes_has_cartao(db, mes_id, user_id)
        or _mes_has_vale(db, mes_id, user_id)
    )


def migrate_legacy_json_if_needed(db: Session, record: MesFinanceiro) -> None:
    if _has_normalized_data(db, record.id, record.user_id):
        return

    contas = record.contas or []
    adicionais = record.adicionais or []
    cartao = record.cartao or []
    reservado = record.reservado or []
    debito = record.debito or []
    vale_carga = record.vale_carga or {}

    if not any([contas, adicionais, cartao, reservado, debito, vale_carga]):
        return

    uid = record.user_id
    mid = record.id

    for item in contas:
        db.add(
            ContaFinanceira(
                user_id=uid,
                mes_id=mid,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                status=item.get("status", "pendente"),
                categoria=item.get("categoria", ""),
            )
        )
    for item in adicionais:
        db.add(
            AdicionalFinanceiro(
                user_id=uid,
                mes_id=mid,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
            )
        )
    for item in debito:
        db.add(
            DebitoFinanceiro(
                user_id=uid,
                mes_id=mid,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                categoria=item.get("categoria", ""),
            )
        )
    for item in reservado:
        db.add(
            ReservadoFinanceiro(
                user_id=uid,
                mes_id=mid,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                categoria=item.get("categoria", ""),
            )
        )
    for item in cartao:
        db.add(
            CompraCartao(
                user_id=uid,
                mes_id=mid,
                cartao_id=item.get("cartaoId", ""),
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                parcelas=item.get("parcelas", "À vista"),
                recorrente=bool(item.get("recorrente", False)),
                categoria=item.get("categoria", ""),
            )
        )
    for cartao_id, valor in vale_carga.items():
        db.add(
            ValeCarga(
                user_id=uid,
                mes_id=mid,
                cartao_id=str(cartao_id),
                valor=float(valor or 0),
            )
        )

    record.contas = []
    record.adicionais = []
    record.cartao = []
    record.reservado = []
    record.debito = []
    record.vale_carga = {}
    db.commit()


def _replace_contas(db: Session, mes_id: int, user_id: str, items: list) -> None:
    db.query(ContaFinanceira).filter(
        ContaFinanceira.mes_id == mes_id, ContaFinanceira.user_id == user_id
    ).delete()
    for item in items:
        db.add(
            ContaFinanceira(
                user_id=user_id,
                mes_id=mes_id,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                status=item.get("status", "pendente"),
                categoria=item.get("categoria", ""),
            )
        )


def _replace_adicionais(db: Session, mes_id: int, user_id: str, items: list) -> None:
    db.query(AdicionalFinanceiro).filter(
        AdicionalFinanceiro.mes_id == mes_id, AdicionalFinanceiro.user_id == user_id
    ).delete()
    for item in items:
        db.add(
            AdicionalFinanceiro(
                user_id=user_id,
                mes_id=mes_id,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
            )
        )


def _replace_debito(db: Session, mes_id: int, user_id: str, items: list) -> None:
    db.query(DebitoFinanceiro).filter(
        DebitoFinanceiro.mes_id == mes_id, DebitoFinanceiro.user_id == user_id
    ).delete()
    for item in items:
        db.add(
            DebitoFinanceiro(
                user_id=user_id,
                mes_id=mes_id,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                categoria=item.get("categoria", ""),
            )
        )


def _replace_reservado(db: Session, mes_id: int, user_id: str, items: list) -> None:
    db.query(ReservadoFinanceiro).filter(
        ReservadoFinanceiro.mes_id == mes_id, ReservadoFinanceiro.user_id == user_id
    ).delete()
    for item in items:
        db.add(
            ReservadoFinanceiro(
                user_id=user_id,
                mes_id=mes_id,
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                categoria=item.get("categoria", ""),
            )
        )


def _replace_cartao(db: Session, mes_id: int, user_id: str, items: list) -> None:
    db.query(CompraCartao).filter(
        CompraCartao.mes_id == mes_id, CompraCartao.user_id == user_id
    ).delete()
    for item in items:
        db.add(
            CompraCartao(
                user_id=user_id,
                mes_id=mes_id,
                cartao_id=item.get("cartaoId", ""),
                nome=item.get("nome", ""),
                valor=float(item.get("valor", 0)),
                parcelas=item.get("parcelas", "À vista"),
                recorrente=bool(item.get("recorrente", False)),
                categoria=item.get("categoria", ""),
            )
        )


def _replace_vale_carga(db: Session, mes_id: int, user_id: str, data: dict) -> None:
    db.query(ValeCarga).filter(
        ValeCarga.mes_id == mes_id, ValeCarga.user_id == user_id
    ).delete()
    for cartao_id, valor in (data or {}).items():
        db.add(
            ValeCarga(
                user_id=user_id,
                mes_id=mes_id,
                cartao_id=str(cartao_id),
                valor=float(valor or 0),
            )
        )


def _union_contas(db: Session, mes_id: int, user_id: str, items: list) -> None:
    existing = [
        _conta_to_dict(c)
        for c in db.query(ContaFinanceira)
        .filter(ContaFinanceira.mes_id == mes_id, ContaFinanceira.user_id == user_id)
        .all()
    ]
    for item in items:
        if not any(_items_equal(item, e) for e in existing):
            db.add(
                ContaFinanceira(
                    user_id=user_id,
                    mes_id=mes_id,
                    nome=item.get("nome", ""),
                    valor=float(item.get("valor", 0)),
                    status=item.get("status", "pendente"),
                    categoria=item.get("categoria", ""),
                )
            )
            existing.append(item)


def _union_adicionais(db: Session, mes_id: int, user_id: str, items: list) -> None:
    existing = [
        _adicional_to_dict(a)
        for a in db.query(AdicionalFinanceiro)
        .filter(AdicionalFinanceiro.mes_id == mes_id, AdicionalFinanceiro.user_id == user_id)
        .all()
    ]
    for item in items:
        if not any(_items_equal(item, e) for e in existing):
            db.add(
                AdicionalFinanceiro(
                    user_id=user_id,
                    mes_id=mes_id,
                    nome=item.get("nome", ""),
                    valor=float(item.get("valor", 0)),
                )
            )


def _union_debito(db: Session, mes_id: int, user_id: str, items: list) -> None:
    existing = [
        _debito_to_dict(d)
        for d in db.query(DebitoFinanceiro)
        .filter(DebitoFinanceiro.mes_id == mes_id, DebitoFinanceiro.user_id == user_id)
        .all()
    ]
    for item in items:
        if not any(_items_equal(item, e) for e in existing):
            db.add(
                DebitoFinanceiro(
                    user_id=user_id,
                    mes_id=mes_id,
                    nome=item.get("nome", ""),
                    valor=float(item.get("valor", 0)),
                    categoria=item.get("categoria", ""),
                )
            )


def _union_reservado(db: Session, mes_id: int, user_id: str, items: list) -> None:
    existing = [
        _reservado_to_dict(r)
        for r in db.query(ReservadoFinanceiro)
        .filter(ReservadoFinanceiro.mes_id == mes_id, ReservadoFinanceiro.user_id == user_id)
        .all()
    ]
    for item in items:
        if not any(_items_equal(item, e) for e in existing):
            db.add(
                ReservadoFinanceiro(
                    user_id=user_id,
                    mes_id=mes_id,
                    nome=item.get("nome", ""),
                    valor=float(item.get("valor", 0)),
                    categoria=item.get("categoria", ""),
                )
            )


def _union_cartao(db: Session, mes_id: int, user_id: str, items: list) -> None:
    existing = [
        _compra_to_dict(c)
        for c in db.query(CompraCartao)
        .filter(CompraCartao.mes_id == mes_id, CompraCartao.user_id == user_id)
        .all()
    ]
    for item in items:
        if not any(_items_equal(item, e) for e in existing):
            db.add(
                CompraCartao(
                    user_id=user_id,
                    mes_id=mes_id,
                    cartao_id=item.get("cartaoId", ""),
                    nome=item.get("nome", ""),
                    valor=float(item.get("valor", 0)),
                    parcelas=item.get("parcelas", "À vista"),
                    recorrente=bool(item.get("recorrente", False)),
                    categoria=item.get("categoria", ""),
                )
            )


def _remove_contas(db: Session, mes_id: int, user_id: str, items: list) -> None:
    rows = (
        db.query(ContaFinanceira)
        .filter(ContaFinanceira.mes_id == mes_id, ContaFinanceira.user_id == user_id)
        .all()
    )
    for item in items:
        for row in rows:
            if _items_equal(item, _conta_to_dict(row)):
                db.delete(row)
                break


def _remove_cartao(db: Session, mes_id: int, user_id: str, items: list) -> None:
    rows = (
        db.query(CompraCartao)
        .filter(CompraCartao.mes_id == mes_id, CompraCartao.user_id == user_id)
        .all()
    )
    for item in items:
        for row in rows:
            if _items_equal(item, _compra_to_dict(row)):
                db.delete(row)
                break


def apply_mes_data(
    db: Session, record: MesFinanceiro, data: dict[str, Any], user_id: str
) -> None:
    """Grava dados do mês. user_id deve ser sempre users.id do usuário autenticado."""
    migrate_legacy_json_if_needed(db, record)
    mid, uid = record.id, user_id

    wipe = _is_init_wipe_payload(data)
    if wipe and (
        _mes_has_contas(db, mid, uid)
        or _mes_has_adicionais(db, mid, uid)
        or _mes_has_debito(db, mid, uid)
        or _mes_has_reservado(db, mid, uid)
        or _mes_has_cartao(db, mid, uid)
        or _mes_has_vale(db, mid, uid)
    ):
        return

    if "contas" in data:
        _replace_contas(db, mid, uid, data["contas"] or [])
    if "adicionais" in data:
        _replace_adicionais(db, mid, uid, data["adicionais"] or [])
    if "debito" in data:
        _replace_debito(db, mid, uid, data["debito"] or [])
    if "reservado" in data:
        _replace_reservado(db, mid, uid, data["reservado"] or [])
    if "cartao" in data:
        _replace_cartao(db, mid, uid, data["cartao"] or [])
    if "cartaoStatus" in data:
        record.cartao_status = data["cartaoStatus"]
    if "valeCarga" in data:
        _replace_vale_carga(db, mid, uid, data["valeCarga"] or {})


def apply_field_operations(
    db: Session, record: MesFinanceiro, updates: dict[str, Any], user_id: str
) -> None:
    """Atualiza campos do mês. user_id deve ser sempre users.id do usuário autenticado."""
    migrate_legacy_json_if_needed(db, record)
    mid, uid = record.id, user_id

    for field, value in updates.items():
        if isinstance(value, dict) and value.get("__finOp") == "arrayUnion":
            items = value.get("items", [])
            if field == "contas":
                _union_contas(db, mid, uid, items)
            elif field == "adicionais":
                _union_adicionais(db, mid, uid, items)
            elif field == "debito":
                _union_debito(db, mid, uid, items)
            elif field == "reservado":
                _union_reservado(db, mid, uid, items)
            elif field == "cartao":
                _union_cartao(db, mid, uid, items)
        elif isinstance(value, dict) and value.get("__finOp") == "arrayRemove":
            items = value.get("items", [])
            if field == "contas":
                _remove_contas(db, mid, uid, items)
            elif field == "cartao":
                _remove_cartao(db, mid, uid, items)
            elif field == "debito":
                rows = (
                    db.query(DebitoFinanceiro)
                    .filter(DebitoFinanceiro.mes_id == mid, DebitoFinanceiro.user_id == uid)
                    .all()
                )
                for item in items:
                    for row in rows:
                        if _items_equal(item, _debito_to_dict(row)):
                            db.delete(row)
            elif field == "reservado":
                rows = (
                    db.query(ReservadoFinanceiro)
                    .filter(ReservadoFinanceiro.mes_id == mid, ReservadoFinanceiro.user_id == uid)
                    .all()
                )
                for item in items:
                    for row in rows:
                        if _items_equal(item, _reservado_to_dict(row)):
                            db.delete(row)
            elif field == "adicionais":
                rows = (
                    db.query(AdicionalFinanceiro)
                    .filter(AdicionalFinanceiro.mes_id == mid, AdicionalFinanceiro.user_id == uid)
                    .all()
                )
                for item in items:
                    for row in rows:
                        if _items_equal(item, _adicional_to_dict(row)):
                            db.delete(row)
        elif field == "cartaoStatus":
            record.cartao_status = value
        elif field == "valeCarga":
            if isinstance(value, dict):
                _replace_vale_carga(db, mid, uid, value)
        elif field == "contas":
            _replace_contas(db, mid, uid, value or [])
        elif field == "adicionais":
            _replace_adicionais(db, mid, uid, value or [])
        elif field == "debito":
            _replace_debito(db, mid, uid, value or [])
        elif field == "reservado":
            _replace_reservado(db, mid, uid, value or [])
        elif field == "cartao":
            _replace_cartao(db, mid, uid, value or [])
