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
        "cartaoId": _referencia_cartao(item.cartao),
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


def _inserir_compra_cartao_integracao(
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
    cartao_db_id = _resolver_cartao_id(db, usuario.id, cartao_id)
    if not cartao_db_id:
        raise ValueError("Informe final_cartao com os 4 últimos dígitos do cartão.")

    id_categoria = _resolver_categoria(db, usuario.id, categoria)
    mes_index = data_lanc.month - 1
    ano_base = data_lanc.year
    ano_limite = ano_base + ANO_LIMITE_OFFSET
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
        return _inserir_compra_cartao_integracao(
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
