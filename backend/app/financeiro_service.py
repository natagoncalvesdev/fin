"""Serviço financeiro — dados por data, agrupados por mês na API."""

from __future__ import annotations

import json
import re
import unicodedata
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
    new_uuid,
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


def _normalizar_texto_busca(texto: str) -> str:
    texto = (texto or "").strip().casefold()
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(ch for ch in decomposto if unicodedata.category(ch) != "Mn")


def _textos_equivalentes(a: str, b: str) -> bool:
    norm_a = _normalizar_texto_busca(a)
    norm_b = _normalizar_texto_busca(b)
    if not norm_a or not norm_b:
        return False
    return norm_a == norm_b or norm_a in norm_b or norm_b in norm_a


def _filtrar_contas_por_descricao(
    contas: list[Conta],
    descricao: str,
    categoria: str = "",
) -> list[Conta]:
    matches: list[Conta] = []
    for conta in contas:
        if not _textos_equivalentes(conta.nome, descricao):
            continue
        if categoria.strip():
            cat_conta = _categoria_nome(conta.categoria)
            if not _textos_equivalentes(cat_conta, categoria):
                continue
        matches.append(conta)
    return matches


def _resolver_categoria(db: Session, id_usuario: int, nome: str) -> int | None:
    nome = (nome or "").strip()
    if not nome:
        return None
    categorias = (
        db.query(Categoria)
        .filter(Categoria.id_usuario == id_usuario)
        .all()
    )
    for cat in categorias:
        if _textos_equivalentes(cat.nome, nome):
            return cat.id
    nova = Categoria(id_usuario=id_usuario, nome=nome)
    db.add(nova)
    db.flush()
    return nova.id


def _referencia_cartao(cartao: Cartao | None) -> str:
    if not cartao:
        return ""
    return (cartao.final_cartao or "").strip() or cartao.uuid


def _resolver_cartao_id(db: Session, id_usuario: int, cartao_ref: str) -> int | None:
    if not cartao_ref:
        return None
    ref = cartao_ref.strip()
    cartao = (
        db.query(Cartao)
        .filter(Cartao.id_usuario == id_usuario, Cartao.final_cartao == ref)
        .first()
    )
    if cartao:
        return cartao.id
    cartao = (
        db.query(Cartao)
        .filter(Cartao.uuid == ref, Cartao.id_usuario == id_usuario)
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


def conta_to_dict(item: Conta) -> dict:
    return {
        "id": item.uuid,
        "nome": item.nome,
        "valor": item.valor,
        "status": item.situacao,
        "categoria": _categoria_nome(item.categoria),
    }


def entrada_to_dict(item: Entrada) -> dict:
    return {"id": item.uuid, "nome": item.nome, "valor": item.valor}


def debito_to_dict(item: Debito) -> dict:
    return {
        "id": item.uuid,
        "nome": item.compra,
        "valor": item.valor,
        "categoria": _categoria_nome(item.categoria),
    }


def reservado_to_dict(item: Reservado) -> dict:
    return {
        "id": item.uuid,
        "nome": item.compra,
        "valor": item.valor,
        "categoria": _categoria_nome(item.categoria),
    }


def compra_to_dict(item: CompraCartao) -> dict:
    data = {
        "id": item.uuid,
        "nome": item.compra,
        "valor": item.valor,
        "parcelas": _format_parcelas(item.parcela_atual, item.parcela_total, item.recorrente),
        "cartaoId": _referencia_cartao(item.cartao),
        "categoria": _categoria_nome(item.categoria),
        "serieUuid": item.serie_uuid,
    }
    if item.recorrente:
        data["recorrente"] = True
    return data


def mes_to_dict(db: Session, ref: MesRef) -> dict:
    uid = ref.id_usuario
    inicio, fim = periodo_mes(ref.ano, ref.mes)

    contas = [
        conta_to_dict(c)
        for c in (
            db.query(Conta)
            .options(joinedload(Conta.categoria))
            .filter(Conta.id_usuario == uid, Conta.data_conta >= inicio, Conta.data_conta < fim)
            .order_by(Conta.id)
            .all()
        )
    ]
    adicionais = [
        entrada_to_dict(e)
        for e in db.query(Entrada)
        .filter(Entrada.id_usuario == uid, Entrada.data_entrada >= inicio, Entrada.data_entrada < fim)
        .order_by(Entrada.id)
        .all()
    ]
    debito = [
        debito_to_dict(d)
        for d in (
            db.query(Debito)
            .options(joinedload(Debito.categoria))
            .filter(Debito.id_usuario == uid, Debito.data_debito >= inicio, Debito.data_debito < fim)
            .order_by(Debito.id.desc())
            .all()
        )
    ]
    reservado = [
        reservado_to_dict(r)
        for r in (
            db.query(Reservado)
            .options(joinedload(Reservado.categoria))
            .filter(Reservado.id_usuario == uid, Reservado.data_reservado >= inicio, Reservado.data_reservado < fim)
            .order_by(Reservado.id)
            .all()
        )
    ]
    cartao = [
        compra_to_dict(c)
        for c in (
            db.query(CompraCartao)
            .options(joinedload(CompraCartao.cartao), joinedload(CompraCartao.categoria))
            .filter(
                CompraCartao.id_usuario == uid,
                CompraCartao.data_competencia >= inicio,
                CompraCartao.data_competencia < fim,
            )
            .order_by(CompraCartao.id.desc())
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


def criar_conta(
    db: Session,
    usuario: Usuario,
    *,
    ano: int,
    mes: str,
    nome: str,
    valor: float,
    status: str = "pendente",
    categoria: str = "",
) -> Conta:
    get_or_create_mes(db, usuario, ano, mes)
    inicio, _ = periodo_mes(ano, mes)
    item = Conta(
        id_usuario=usuario.id,
        id_categoria=_resolver_categoria(db, usuario.id, categoria),
        data_conta=inicio,
        nome=nome,
        valor=valor,
        situacao=status or "pendente",
    )
    db.add(item)
    db.flush()
    return item


def _get_conta(db: Session, usuario: Usuario, item_uuid: str) -> Conta | None:
    return (
        db.query(Conta)
        .filter(Conta.uuid == item_uuid, Conta.id_usuario == usuario.id)
        .first()
    )


def atualizar_conta(
    db: Session,
    usuario: Usuario,
    item_uuid: str,
    *,
    nome: str | None = None,
    valor: float | None = None,
    status: str | None = None,
    categoria: str | None = None,
) -> Conta:
    item = _get_conta(db, usuario, item_uuid)
    if not item:
        raise ValueError("Conta não encontrada.")
    if nome is not None:
        item.nome = nome
    if valor is not None:
        item.valor = valor
    if status is not None:
        item.situacao = status
    if categoria is not None:
        item.id_categoria = _resolver_categoria(db, usuario.id, categoria)
    db.flush()
    return item


def remover_conta(db: Session, usuario: Usuario, item_uuid: str) -> None:
    item = _get_conta(db, usuario, item_uuid)
    if not item:
        raise ValueError("Conta não encontrada.")
    db.delete(item)
    db.flush()


def criar_entrada(
    db: Session, usuario: Usuario, *, ano: int, mes: str, nome: str, valor: float
) -> Entrada:
    get_or_create_mes(db, usuario, ano, mes)
    inicio, _ = periodo_mes(ano, mes)
    item = Entrada(id_usuario=usuario.id, data_entrada=inicio, nome=nome, valor=valor)
    db.add(item)
    db.flush()
    return item


def _get_entrada(db: Session, usuario: Usuario, item_uuid: str) -> Entrada | None:
    return (
        db.query(Entrada)
        .filter(Entrada.uuid == item_uuid, Entrada.id_usuario == usuario.id)
        .first()
    )


def atualizar_entrada(
    db: Session,
    usuario: Usuario,
    item_uuid: str,
    *,
    nome: str | None = None,
    valor: float | None = None,
) -> Entrada:
    item = _get_entrada(db, usuario, item_uuid)
    if not item:
        raise ValueError("Entrada não encontrada.")
    if nome is not None:
        item.nome = nome
    if valor is not None:
        item.valor = valor
    db.flush()
    return item


def remover_entrada(db: Session, usuario: Usuario, item_uuid: str) -> None:
    item = _get_entrada(db, usuario, item_uuid)
    if not item:
        raise ValueError("Entrada não encontrada.")
    db.delete(item)
    db.flush()


def criar_debito(
    db: Session,
    usuario: Usuario,
    *,
    ano: int,
    mes: str,
    nome: str,
    valor: float,
    categoria: str = "",
) -> Debito:
    get_or_create_mes(db, usuario, ano, mes)
    inicio, _ = periodo_mes(ano, mes)
    item = Debito(
        id_usuario=usuario.id,
        id_categoria=_resolver_categoria(db, usuario.id, categoria),
        data_debito=inicio,
        compra=nome,
        valor=valor,
    )
    db.add(item)
    db.flush()
    return item


def _get_debito(db: Session, usuario: Usuario, item_uuid: str) -> Debito | None:
    return (
        db.query(Debito)
        .filter(Debito.uuid == item_uuid, Debito.id_usuario == usuario.id)
        .first()
    )


def atualizar_debito(
    db: Session,
    usuario: Usuario,
    item_uuid: str,
    *,
    nome: str | None = None,
    valor: float | None = None,
    categoria: str | None = None,
) -> Debito:
    item = _get_debito(db, usuario, item_uuid)
    if not item:
        raise ValueError("Débito não encontrado.")
    if nome is not None:
        item.compra = nome
    if valor is not None:
        item.valor = valor
    if categoria is not None:
        item.id_categoria = _resolver_categoria(db, usuario.id, categoria)
    db.flush()
    return item


def remover_debito(db: Session, usuario: Usuario, item_uuid: str) -> None:
    item = _get_debito(db, usuario, item_uuid)
    if not item:
        raise ValueError("Débito não encontrado.")
    db.delete(item)
    db.flush()


def criar_reservado(
    db: Session,
    usuario: Usuario,
    *,
    ano: int,
    mes: str,
    nome: str,
    valor: float,
    categoria: str = "",
) -> Reservado:
    get_or_create_mes(db, usuario, ano, mes)
    inicio, _ = periodo_mes(ano, mes)
    item = Reservado(
        id_usuario=usuario.id,
        id_categoria=_resolver_categoria(db, usuario.id, categoria),
        data_reservado=inicio,
        compra=nome,
        valor=valor,
    )
    db.add(item)
    db.flush()
    return item


def _get_reservado(db: Session, usuario: Usuario, item_uuid: str) -> Reservado | None:
    return (
        db.query(Reservado)
        .filter(Reservado.uuid == item_uuid, Reservado.id_usuario == usuario.id)
        .first()
    )


def atualizar_reservado(
    db: Session,
    usuario: Usuario,
    item_uuid: str,
    *,
    nome: str | None = None,
    valor: float | None = None,
    categoria: str | None = None,
) -> Reservado:
    item = _get_reservado(db, usuario, item_uuid)
    if not item:
        raise ValueError("Reservado não encontrado.")
    if nome is not None:
        item.compra = nome
    if valor is not None:
        item.valor = valor
    if categoria is not None:
        item.id_categoria = _resolver_categoria(db, usuario.id, categoria)
    db.flush()
    return item


def remover_reservado(db: Session, usuario: Usuario, item_uuid: str) -> None:
    item = _get_reservado(db, usuario, item_uuid)
    if not item:
        raise ValueError("Reservado não encontrado.")
    db.delete(item)
    db.flush()


def _get_compra_cartao(db: Session, usuario: Usuario, item_uuid: str) -> CompraCartao | None:
    return (
        db.query(CompraCartao)
        .filter(CompraCartao.uuid == item_uuid, CompraCartao.id_usuario == usuario.id)
        .first()
    )


def atualizar_compra_cartao(
    db: Session,
    usuario: Usuario,
    item_uuid: str,
    *,
    nome: str | None = None,
    valor: float | None = None,
    categoria: str | None = None,
) -> CompraCartao:
    item = _get_compra_cartao(db, usuario, item_uuid)
    if not item:
        raise ValueError("Compra não encontrada.")
    if nome is not None:
        item.compra = nome
    if valor is not None:
        item.valor = valor
    if categoria is not None:
        item.id_categoria = _resolver_categoria(db, usuario.id, categoria)
    db.flush()
    return item


def remover_compra_cartao(
    db: Session, usuario: Usuario, item_uuid: str, *, futuras: bool = False
) -> int:
    """Remove uma compra do cartão. Com futuras=True e a compra fazendo parte de
    uma série (parcelada ou recorrente), remove também as ocorrências desta
    mesma série a partir deste mês (competência), usando serie_uuid — não mais
    por igualdade de conteúdo, que colide quando duas compras têm mesmo
    nome/valor."""
    item = _get_compra_cartao(db, usuario, item_uuid)
    if not item:
        raise ValueError("Compra não encontrada.")

    if futuras and item.serie_uuid:
        removidas = (
            db.query(CompraCartao)
            .filter(
                CompraCartao.id_usuario == usuario.id,
                CompraCartao.serie_uuid == item.serie_uuid,
                CompraCartao.data_competencia >= item.data_competencia,
            )
            .delete(synchronize_session=False)
        )
        db.flush()
        return removidas

    db.delete(item)
    db.flush()
    return 1


def mover_compra_cartao(
    db: Session, usuario: Usuario, item_uuid: str, *, ano: int, mes: str
) -> CompraCartao:
    """Move uma parcela para outro mês (usado para 'adiantar parcela')."""
    item = _get_compra_cartao(db, usuario, item_uuid)
    if not item:
        raise ValueError("Compra não encontrada.")
    get_or_create_mes(db, usuario, ano, mes)
    inicio, _ = periodo_mes(ano, mes)
    item.data_competencia = inicio
    db.flush()
    return item


def atualizar_status_fatura(db: Session, usuario: Usuario, ano: int, mes: str, status: str) -> None:
    ref = get_or_create_mes(db, usuario, ano, mes)
    _update_fatura_status(db, ref, status)
    db.flush()


def resolver_usuario_por_chat_id(db: Session, chat_id: str | int) -> Usuario | None:
    chat_str = str(chat_id).strip()
    if not chat_str:
        return None
    return db.query(Usuario).filter(Usuario.id_telegram == chat_str).first()


def _buscar_contas_mes(
    db: Session,
    usuario: Usuario,
    data_ref: date,
    descricao: str,
    categoria: str = "",
) -> list[Conta]:
    mes_nome = MESES[data_ref.month - 1]
    inicio, fim = periodo_mes(data_ref.year, mes_nome)
    contas = (
        db.query(Conta)
        .options(joinedload(Conta.categoria))
        .filter(
            Conta.id_usuario == usuario.id,
            Conta.data_conta >= inicio,
            Conta.data_conta < fim,
        )
        .all()
    )

    matches = _filtrar_contas_por_descricao(contas, descricao, categoria)
    if matches or not categoria.strip():
        return matches

    # Categoria informada pelo parser pode divergir; tenta só pelo nome.
    matches_nome = _filtrar_contas_por_descricao(contas, descricao)
    if len(matches_nome) == 1:
        return matches_nome
    return matches


def atualizar_status_conta_integracao(
    db: Session,
    usuario: Usuario,
    *,
    data_ref: date,
    descricao: str,
    categoria: str = "",
    pago: bool,
) -> dict[str, Any]:
    descricao = (descricao or "").strip()
    if not descricao:
        raise ValueError("Descrição é obrigatória.")

    contas = _buscar_contas_mes(db, usuario, data_ref, descricao, categoria)
    if not contas:
        mes_nome = MESES[data_ref.month - 1]
        raise ValueError(
            f"Conta '{descricao}' não encontrada em {mes_nome}/{data_ref.year}."
        )

    situacao = "pago" if pago else "pendente"
    for conta in contas:
        conta.situacao = situacao
    db.flush()

    conta = contas[0]
    return {
        "ok": True,
        "uuid": conta.uuid,
        "tipo": "conta",
        "acao": "status_atualizado",
        "data": data_ref.isoformat(),
        "descricao": conta.nome,
        "valor": conta.valor,
        "situacao": situacao,
        "atualizadas": len(contas),
    }


def _calcular_totais_mes(data: dict[str, Any]) -> dict[str, float]:
    total_contas_manuais = sum(float(i.get("valor", 0)) for i in data.get("contas", []))
    total_cartao = sum(float(i.get("valor", 0)) for i in data.get("cartao", []))
    total_debito = sum(float(i.get("valor", 0)) for i in data.get("debito", []))
    total_receita = sum(float(i.get("valor", 0)) for i in data.get("adicionais", []))
    total_reservado = sum(float(i.get("valor", 0)) for i in data.get("reservado", []))
    total_contas = total_contas_manuais + total_cartao + total_debito
    saldo = total_receita - total_contas - total_reservado
    return {
        "receita": total_receita,
        "contas": total_contas,
        "contas_fixas": total_contas_manuais,
        "cartao": total_cartao,
        "debito": total_debito,
        "saldo": saldo,
        "reservado": total_reservado,
    }


def _normalizar_tipo_consulta(tipo: str) -> str:
    tipo_norm = (tipo or "").strip().lower().replace("-", "_")
    if tipo_norm.startswith("extrato_"):
        tipo_norm = tipo_norm[len("extrato_") :]
    aliases = {
        "valores": "valores",
        "consulta_valores": "valores",
        "consulta": "valores",
        "resumo": "valores",
        "saldo": "valores",
        "debito": "debito",
        "debitos": "debito",
        "conta": "contas",
        "contas": "contas",
        "entrada": "entradas",
        "entradas": "entradas",
        "receita": "entradas",
        "receitas": "entradas",
        "adicional": "entradas",
        "adicionais": "entradas",
        "cartao": "cartao",
        "cartao_credito": "cartao",
        "credito": "cartao",
        "reservado": "reservado",
        "reservados": "reservado",
    }
    return aliases.get(tipo_norm, tipo_norm)


def is_tipo_consulta(tipo: str) -> bool:
    tipo_norm = (tipo or "").strip().lower().replace("-", "_")
    if tipo_norm.startswith("extrato_"):
        return True
    return tipo_norm in ("valores", "resumo", "saldo", "consulta_valores", "consulta")


def executar_consulta_integracao(
    db: Session,
    usuario: Usuario,
    *,
    data_ref: date,
    tipo: str,
    final_cartao: str = "",
) -> dict[str, Any]:
    from app.n8n_notifier import formatar_brl

    tipo_interno = _normalizar_tipo_consulta(tipo)
    mes_nome = MESES[data_ref.month - 1]
    ref = get_or_create_mes(db, usuario, data_ref.year, mes_nome)
    data = mes_to_dict(db, ref)
    periodo = f"{mes_nome}/{data_ref.year}"

    if tipo_interno == "valores":
        totais = _calcular_totais_mes(data)
        mensagem = (
            f"Resumo — {periodo}\n"
            f"🔵 Receita {formatar_brl(totais['receita'])}\n"
            f"🔴 Contas {formatar_brl(totais['contas'])}\n"
            f"   • Fixas {formatar_brl(totais['contas_fixas'])}\n"
            f"   • Cartão {formatar_brl(totais['cartao'])}\n"
            f"   • Débito {formatar_brl(totais['debito'])}\n"
            f"🟢 Saldo {formatar_brl(totais['saldo'])}\n"
            f"🟡 Reservado {formatar_brl(totais['reservado'])}"
        )
    elif tipo_interno == "debito":
        mensagem = _montar_extrato_debito(periodo, data.get("debito") or [], formatar_brl)
    elif tipo_interno == "contas":
        mensagem = _montar_extrato_contas(periodo, data.get("contas") or [], formatar_brl)
    elif tipo_interno == "entradas":
        mensagem = _montar_extrato_entradas(periodo, data.get("adicionais") or [], formatar_brl)
    elif tipo_interno == "cartao":
        compras = data.get("cartao") or []
        if final_cartao.strip():
            compras = [c for c in compras if c.get("cartaoId") == final_cartao.strip()]
        mensagem = _montar_extrato_cartao(periodo, compras, formatar_brl, final_cartao.strip())
    elif tipo_interno == "reservado":
        mensagem = _montar_extrato_reservado(periodo, data.get("reservado") or [], formatar_brl)
    else:
        raise ValueError(f"Tipo de consulta inválido: {tipo}")

    return {
        "ok": True,
        "acao": "consulta",
        "tipo": tipo_interno,
        "data": data_ref.isoformat(),
        "mensagem": mensagem,
    }


def _montar_extrato_debito(periodo: str, items: list, formatar_brl) -> str:
    if not items:
        return f"Extrato — Débito ({periodo})\nNenhum lançamento."
    linhas = [f"Extrato — Débito ({periodo})", ""]
    total = 0.0
    for item in items:
        nome = item.get("nome") or "—"
        valor = float(item.get("valor") or 0)
        cat = item.get("categoria") or ""
        sufixo = f" · {cat}" if cat else ""
        linhas.append(f"• {nome} — {formatar_brl(valor)}{sufixo}")
        total += valor
    linhas.extend(["", f"Total: {formatar_brl(total)}"])
    return "\n".join(linhas)


def _montar_extrato_contas(periodo: str, items: list, formatar_brl) -> str:
    if not items:
        return f"Extrato — Contas ({periodo})\nNenhuma conta."
    linhas = [f"Extrato — Contas ({periodo})", ""]
    total = 0.0
    for item in items:
        nome = item.get("nome") or "—"
        valor = float(item.get("valor") or 0)
        status = item.get("status") or "pendente"
        status_label = "pago" if status == "pago" else "pendente"
        cat = item.get("categoria") or ""
        sufixo = f" · {cat}" if cat else ""
        linhas.append(f"• {nome} — {formatar_brl(valor)} ({status_label}){sufixo}")
        total += valor
    linhas.extend(["", f"Total: {formatar_brl(total)}"])
    return "\n".join(linhas)


def _montar_extrato_entradas(periodo: str, items: list, formatar_brl) -> str:
    if not items:
        return f"Extrato — Entradas ({periodo})\nNenhuma entrada."
    linhas = [f"Extrato — Entradas ({periodo})", ""]
    total = 0.0
    for item in items:
        nome = item.get("nome") or "—"
        valor = float(item.get("valor") or 0)
        linhas.append(f"• {nome} — {formatar_brl(valor)}")
        total += valor
    linhas.extend(["", f"Total: {formatar_brl(total)}"])
    return "\n".join(linhas)


def _montar_extrato_cartao(
    periodo: str,
    items: list,
    formatar_brl,
    final_cartao: str = "",
) -> str:
    titulo = f"Extrato — Cartão ({periodo})"
    if final_cartao:
        titulo = f"Extrato — Cartão final {final_cartao} ({periodo})"
    if not items:
        return f"{titulo}\nNenhuma compra."
    linhas = [titulo, ""]
    total = 0.0
    for item in items:
        nome = item.get("nome") or "—"
        valor = float(item.get("valor") or 0)
        parcelas = item.get("parcelas") or "À vista"
        final = item.get("cartaoId") or ""
        extras = [parcelas]
        if final and not final_cartao:
            extras.append(f"final {final}")
        cat = item.get("categoria") or ""
        if cat:
            extras.append(cat)
        linhas.append(f"• {nome} — {formatar_brl(valor)} ({', '.join(extras)})")
        total += valor
    linhas.extend(["", f"Total: {formatar_brl(total)}"])
    return "\n".join(linhas)


def _montar_extrato_reservado(periodo: str, items: list, formatar_brl) -> str:
    if not items:
        return f"Extrato — Reservado ({periodo})\nNenhum valor reservado."
    linhas = [f"Extrato — Reservado ({periodo})", ""]
    total = 0.0
    for item in items:
        nome = item.get("nome") or "—"
        valor = float(item.get("valor") or 0)
        cat = item.get("categoria") or ""
        sufixo = f" · {cat}" if cat else ""
        linhas.append(f"• {nome} — {formatar_brl(valor)}{sufixo}")
        total += valor
    linhas.extend(["", f"Total: {formatar_brl(total)}"])
    return "\n".join(linhas)


def _normalizar_tipo_lancamento(tipo: str) -> str:
    tipo_norm = (tipo or "").strip().lower()
    aliases = {
        "despesa": "debito",
        "debito": "debito",
        "receita": "entrada",
        "entrada": "entrada",
        "adicional": "entrada",
        "adicionais": "entrada",
        "conta": "conta",
        "contas": "conta",
        "reservado": "reservado",
        "cartao": "cartao",
    }
    return aliases.get(tipo_norm, tipo_norm)


MESES_RECORRENTE_MAX = 12
ANO_LIMITE_OFFSET = 10


def _destino_mes_offset(ano: int, mes_index: int, offset: int) -> tuple[int, str]:
    target_mes_index = (mes_index + offset) % 12
    target_ano = ano + (mes_index + offset) // 12
    return target_ano, MESES[target_mes_index]


def inserir_compra_cartao(
    db: Session,
    usuario: Usuario,
    *,
    data_lanc: date,
    descricao: str,
    valor: float,
    categoria: str,
    cartao_id: str,
    total_parcelas: int = 1,
    recorrente: bool = False,
) -> dict[str, Any]:
    """Cria a(s) linha(s) de uma compra no cartão (parcelada ou recorrente).

    Todas as parcelas/ocorrências de uma mesma compra compartilham `serie_uuid`,
    o que permite depois localizar "esta e as próximas" de forma confiável
    (ex.: adiantar parcela, excluir recorrência) sem depender de comparar
    nome/valor por igualdade de conteúdo.
    """
    cartao_db_id = _resolver_cartao_id(db, usuario.id, cartao_id)
    if not cartao_db_id:
        raise ValueError("Informe final_cartao com os 4 últimos dígitos do cartão.")

    id_categoria = _resolver_categoria(db, usuario.id, categoria)
    mes_index = data_lanc.month - 1
    ano_base = data_lanc.year
    ano_limite = ano_base + ANO_LIMITE_OFFSET
    serie = new_uuid()
    registros: list[CompraCartao] = []

    if recorrente:
        for i in range(MESES_RECORRENTE_MAX):
            target_ano, target_mes = _destino_mes_offset(ano_base, mes_index, i)
            if target_ano > ano_limite:
                break
            get_or_create_mes(db, usuario, target_ano, target_mes)
            target_inicio, _ = periodo_mes(target_ano, target_mes)
            registros.append(
                CompraCartao(
                    id_usuario=usuario.id,
                    id_cartao=cartao_db_id,
                    data_compra_cartao=data_lanc,
                    data_competencia=target_inicio,
                    id_categoria=id_categoria,
                    compra=descricao,
                    valor=valor,
                    parcela_atual=1,
                    parcela_total=1,
                    recorrente=True,
                    serie_uuid=serie,
                )
            )
    else:
        if total_parcelas < 1:
            raise ValueError("totalParcelas deve ser 1 ou maior.")
        for i in range(total_parcelas):
            target_ano, target_mes = _destino_mes_offset(ano_base, mes_index, i)
            if target_ano > ano_limite:
                continue
            get_or_create_mes(db, usuario, target_ano, target_mes)
            target_inicio, _ = periodo_mes(target_ano, target_mes)
            registros.append(
                CompraCartao(
                    id_usuario=usuario.id,
                    id_cartao=cartao_db_id,
                    data_compra_cartao=data_lanc,
                    data_competencia=target_inicio,
                    id_categoria=id_categoria,
                    compra=descricao,
                    valor=valor,
                    parcela_atual=i + 1,
                    parcela_total=total_parcelas,
                    recorrente=False,
                    serie_uuid=serie,
                )
            )

    if not registros:
        raise ValueError("Não foi possível registrar a compra no cartão.")

    for registro in registros:
        db.add(registro)
    db.flush()

    primeira = registros[0]
    return {
        "ok": True,
        "uuid": primeira.uuid,
        "tipo": "cartao",
        "data": data_lanc.isoformat(),
        "descricao": descricao,
        "valor": valor,
        "parcelasRegistradas": len(registros),
        "totalParcelas": total_parcelas if not recorrente else "Recorrente",
        "registros": registros,
    }


def inserir_lancamento_integracao(
    db: Session,
    usuario: Usuario,
    *,
    tipo: str,
    data_lanc: date,
    descricao: str,
    valor: float,
    categoria: str = "",
    cartao_id: str = "",
    total_parcelas: int = 1,
    recorrente: bool = False,
) -> dict[str, Any]:
    tipo_interno = _normalizar_tipo_lancamento(tipo)
    descricao = (descricao or "").strip()
    if not descricao:
        raise ValueError("Descrição é obrigatória.")
    if valor <= 0:
        raise ValueError("Valor deve ser maior que zero.")

    mes_nome = MESES[data_lanc.month - 1]
    get_or_create_mes(db, usuario, data_lanc.year, mes_nome)

    id_categoria = _resolver_categoria(db, usuario.id, categoria)

    if tipo_interno == "debito":
        registro = Debito(
            id_usuario=usuario.id,
            data_debito=data_lanc,
            id_categoria=id_categoria,
            compra=descricao,
            valor=valor,
        )
    elif tipo_interno == "entrada":
        registro = Entrada(
            id_usuario=usuario.id,
            data_entrada=data_lanc,
            nome=descricao,
            valor=valor,
        )
    elif tipo_interno == "reservado":
        registro = Reservado(
            id_usuario=usuario.id,
            data_reservado=data_lanc,
            id_categoria=id_categoria,
            compra=descricao,
            valor=valor,
        )
    elif tipo_interno == "conta":
        registro = Conta(
            id_usuario=usuario.id,
            data_conta=data_lanc,
            id_categoria=id_categoria,
            nome=descricao,
            valor=valor,
            situacao="pendente",
        )
    elif tipo_interno == "cartao":
        return inserir_compra_cartao(
            db,
            usuario,
            data_lanc=data_lanc,
            descricao=descricao,
            valor=valor,
            categoria=categoria,
            cartao_id=cartao_id,
            total_parcelas=total_parcelas,
            recorrente=recorrente,
        )
    else:
        raise ValueError(f"Tipo de lançamento inválido: {tipo}")

    db.add(registro)
    db.flush()
    return {
        "ok": True,
        "uuid": registro.uuid,
        "tipo": tipo_interno,
        "data": data_lanc.isoformat(),
        "descricao": descricao,
        "valor": valor,
    }


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
