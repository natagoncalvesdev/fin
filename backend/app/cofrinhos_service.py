"""Cálculo e sincronização dos cofrinhos (metas de economia)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app import conquistas_service
from app.models import MESES, Cofrinho, Usuario


def _mes_idx(nome: str | None) -> int | None:
    return MESES.index(nome) if nome in MESES else None


def _tem_prazo(cofrinho: Cofrinho) -> bool:
    return _mes_idx(cofrinho.mes_alvo) is not None and bool(cofrinho.ano_alvo)


def _meses_ate(de: date, ano_alvo: int, mes_alvo_idx: int) -> int:
    """Nº de meses do mês de `de` até o mês-alvo, inclusivo. Passado -> <= 0."""
    return (ano_alvo - de.year) * 12 + (mes_alvo_idx - (de.month - 1)) + 1


def _modo(cofrinho: Cofrinho) -> str:
    return "valor_prazo" if cofrinho.valor_alvo is not None else "aporte_prazo"


def _alvo_efetivo(cofrinho: Cofrinho) -> float:
    """Valor que, ao ser atingido pelo saldo, conclui o cofrinho.

    - modo valor: o próprio valor_alvo.
    - modo aporte: aporte_mensal × (meses do plano, de data_inicio até o alvo).
    """
    if _modo(cofrinho) == "valor_prazo":
        return float(cofrinho.valor_alvo or 0)
    if not _tem_prazo(cofrinho):
        return 0.0
    meses = max(1, _meses_ate(cofrinho.data_inicio, cofrinho.ano_alvo, _mes_idx(cofrinho.mes_alvo)))
    return float(cofrinho.aporte_mensal or 0) * meses


def payload(cofrinho: Cofrinho) -> dict:
    aportes = sorted(cofrinho.aportes, key=lambda a: (a.data_aporte, a.id))
    saldo = round(sum(a.valor for a in aportes), 2)
    hoje = date.today()
    modo = _modo(cofrinho)
    tem_prazo = _tem_prazo(cofrinho)
    mes_idx = _mes_idx(cofrinho.mes_alvo)

    meses_rest = max(0, _meses_ate(hoje, cofrinho.ano_alvo, mes_idx)) if tem_prazo else None
    alvo = round(_alvo_efetivo(cofrinho), 2)
    restante = round(max(0.0, alvo - saldo), 2)
    progresso = min(1.0, saldo / alvo) if alvo > 0 else None

    aporte_sugerido = None
    projecao_final = None
    if modo == "valor_prazo":
        if meses_rest:
            aporte_sugerido = round(restante / meses_rest, 2)
        elif restante > 0:
            aporte_sugerido = restante
    else:
        aporte_sugerido = cofrinho.aporte_mensal
        projecao_final = round(saldo + float(cofrinho.aporte_mensal or 0) * (meses_rest or 0), 2)

    plano: list[dict] = []
    if tem_prazo and meses_rest and restante > 0.005:
        por_mes = (restante / meses_rest) if modo == "valor_prazo" else float(cofrinho.aporte_mensal or 0)
        acum = saldo
        ano, mes = hoje.year, hoje.month - 1
        for _ in range(meses_rest):
            acum += por_mes
            plano.append(
                {"mes": MESES[mes], "ano": ano, "valor": round(por_mes, 2), "acumulado": round(acum, 2)}
            )
            mes += 1
            if mes == 12:
                mes, ano = 0, ano + 1

    return {
        "id": cofrinho.uuid,
        "nome": cofrinho.nome,
        "modo": modo,
        "valorAlvo": cofrinho.valor_alvo,
        "aporteMensal": cofrinho.aporte_mensal,
        "mesAlvo": cofrinho.mes_alvo,
        "anoAlvo": cofrinho.ano_alvo,
        "dataInicio": cofrinho.data_inicio.isoformat(),
        "situacao": cofrinho.situacao,
        "dataConcluido": cofrinho.data_concluido.isoformat() if cofrinho.data_concluido else None,
        "saldo": saldo,
        "alvo": alvo,
        "restante": restante,
        "progresso": progresso,
        "mesesRestantes": meses_rest,
        "aporteSugerido": aporte_sugerido,
        "projecaoFinal": projecao_final,
        "plano": plano,
        "aportes": [{"id": a.uuid, "data": a.to_dict()} for a in aportes],
    }


def sincronizar(db: Session, usuario: Usuario, cofrinho: Cofrinho) -> bool:
    """Marca o cofrinho como concluído quando o saldo alcança o alvo (e concede a
    medalha, permanente). Reverte para ativo se o saldo cair abaixo. `arquivado`
    nunca muda sozinho. Retorna True se algo mudou."""
    if cofrinho.situacao == "arquivado":
        return False

    aportes = list(cofrinho.aportes)
    saldo = sum(a.valor for a in aportes)
    alvo = _alvo_efetivo(cofrinho)
    mudou = False

    if alvo > 0 and saldo >= alvo - 0.005:
        quando = max((a.data_aporte for a in aportes), default=date.today())
        if cofrinho.situacao != "concluido":
            cofrinho.situacao = "concluido"
            cofrinho.data_concluido = quando
            mudou = True
        if conquistas_service.conceder_cofrinho(db, usuario, cofrinho, alvo=round(alvo, 2), quando=quando):
            mudou = True
    elif cofrinho.situacao == "concluido":
        cofrinho.situacao = "ativo"
        cofrinho.data_concluido = None
        mudou = True

    return mudou


def sincronizar_todos(db: Session, usuario: Usuario) -> bool:
    mudou = False
    for cofrinho in db.query(Cofrinho).filter(Cofrinho.id_usuario == usuario.id).all():
        if sincronizar(db, usuario, cofrinho):
            mudou = True
    return mudou
