"""Cofrinhos (metas de economia).

Ao criar um cofrinho, geramos uma **parcela por mês** como uma linha em `conta`
("Cofrinho: <nome>"). O usuário paga essas contas normalmente na tela de Contas
(ou pelo próprio cofrinho); marcar como paga = guardar aquele valor. O montante
do cofrinho é a soma das parcelas pagas.

No modo "valor alvo", quando uma parcela é paga/editada as parcelas pendentes são
redistribuídas para o valor voltar a fechar no alvo. No modo "aporte mensal" a
parcela é fixa.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app import conquistas_service
from app.models import MESES, Cofrinho, Conta, Usuario

CATEGORIA_COFRINHO = "Cofrinho"


def _mes_idx(nome: str | None) -> int | None:
    return MESES.index(nome) if nome in MESES else None


def _tem_prazo(cofrinho: Cofrinho) -> bool:
    return _mes_idx(cofrinho.mes_alvo) is not None and bool(cofrinho.ano_alvo)


def _modo(cofrinho: Cofrinho) -> str:
    return "valor_prazo" if cofrinho.valor_alvo is not None else "aporte_prazo"


def _meses_plano(cofrinho: Cofrinho) -> list[tuple[int, str]]:
    """(ano, nome do mês) de cada parcela — do mês de data_inicio ao mês-alvo."""
    if not _tem_prazo(cofrinho):
        return []
    ini = cofrinho.data_inicio
    alvo_idx = _mes_idx(cofrinho.mes_alvo)
    total = (cofrinho.ano_alvo - ini.year) * 12 + (alvo_idx - (ini.month - 1)) + 1
    total = max(1, total)
    out: list[tuple[int, str]] = []
    ano, mes = ini.year, ini.month - 1
    for _ in range(total):
        out.append((ano, MESES[mes]))
        mes += 1
        if mes == 12:
            mes, ano = 0, ano + 1
    return out


def _alvo_efetivo(cofrinho: Cofrinho) -> float:
    if _modo(cofrinho) == "valor_prazo":
        return float(cofrinho.valor_alvo or 0)
    return float(cofrinho.aporte_mensal or 0) * max(1, len(_meses_plano(cofrinho)))


def _contas(db: Session, cofrinho: Cofrinho) -> list[Conta]:
    return (
        db.query(Conta)
        .filter(Conta.id_cofrinho == cofrinho.id)
        .order_by(Conta.data_conta.asc(), Conta.id.asc())
        .all()
    )


def gerar_parcelas(db: Session, usuario: Usuario, cofrinho: Cofrinho) -> None:
    """Cria as contas mensais que ainda não existem para o plano atual."""
    from app.financeiro_service import criar_conta

    meses = _meses_plano(cofrinho)
    if not meses:
        return
    existentes = {(c.data_conta.year, MESES[c.data_conta.month - 1]) for c in _contas(db, cofrinho)}
    if _modo(cofrinho) == "valor_prazo":
        valor = float(cofrinho.valor_alvo or 0) / len(meses)
    else:
        valor = float(cofrinho.aporte_mensal or 0)
    for ano, mes in meses:
        if (ano, mes) in existentes:
            continue
        criar_conta(
            db,
            usuario,
            ano=ano,
            mes=mes,
            nome=f"Cofrinho: {cofrinho.nome}",
            valor=round(valor, 2),
            status="pendente",
            categoria=CATEGORIA_COFRINHO,
            id_cofrinho=cofrinho.id,
        )


def apagar_parcelas_pendentes(db: Session, cofrinho: Cofrinho) -> None:
    for conta in _contas(db, cofrinho):
        if conta.situacao != "pago":
            db.delete(conta)
    db.flush()


def recalcular_pendentes(db: Session, cofrinho: Cofrinho) -> bool:
    """Redistribui o que falta entre as parcelas pendentes (só no modo valor)."""
    if cofrinho.valor_alvo is None:
        return False
    contas = _contas(db, cofrinho)
    pago = sum(c.valor for c in contas if c.situacao == "pago")
    pendentes = [c for c in contas if c.situacao != "pago"]
    if not pendentes:
        return False
    novo = round(max(0.0, float(cofrinho.valor_alvo) - pago) / len(pendentes), 2)
    mudou = False
    for c in pendentes:
        if abs(c.valor - novo) > 0.005:
            c.valor = novo
            mudou = True
    return mudou


def sincronizar(db: Session, usuario: Usuario, cofrinho: Cofrinho) -> bool:
    """Conclui o cofrinho quando o total pago alcança o alvo (medalha, permanente)
    e reverte para ativo se cair abaixo. `arquivado` não muda sozinho."""
    if cofrinho.situacao == "arquivado":
        return False
    contas = _contas(db, cofrinho)
    pago = sum(c.valor for c in contas if c.situacao == "pago")
    alvo = _alvo_efetivo(cofrinho)
    mudou = False
    if alvo > 0 and pago >= alvo - 0.005:
        quando = max((c.data_conta for c in contas if c.situacao == "pago"), default=date.today())
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


def apos_mudanca_conta(db: Session, usuario: Usuario, cofrinho: Cofrinho) -> bool:
    """Chamado quando uma conta ligada a um cofrinho é paga/editada/removida."""
    mudou = recalcular_pendentes(db, cofrinho)
    return sincronizar(db, usuario, cofrinho) or mudou


def payload(db: Session, cofrinho: Cofrinho) -> dict:
    contas = _contas(db, cofrinho)
    hoje = date.today()
    pago = round(sum(c.valor for c in contas if c.situacao == "pago"), 2)
    modo = _modo(cofrinho)
    alvo = round(_alvo_efetivo(cofrinho), 2)
    pendentes = [c for c in contas if c.situacao != "pago"]

    projecao_final = None
    if modo == "aporte_prazo":
        projecao_final = round(pago + sum(c.valor for c in pendentes), 2)

    parcelas = [
        {
            "id": c.uuid,
            "mes": MESES[c.data_conta.month - 1],
            "ano": c.data_conta.year,
            "valor": round(c.valor, 2),
            "status": c.situacao,
            "vencida": c.situacao != "pago"
            and (c.data_conta.year, c.data_conta.month) < (hoje.year, hoje.month),
        }
        for c in contas
    ]

    return {
        "id": cofrinho.uuid,
        "nome": cofrinho.nome,
        "modo": modo,
        "valorAlvo": cofrinho.valor_alvo,
        "aporteMensal": cofrinho.aporte_mensal,
        "mesAlvo": cofrinho.mes_alvo,
        "anoAlvo": cofrinho.ano_alvo,
        "situacao": cofrinho.situacao,
        "dataConcluido": cofrinho.data_concluido.isoformat() if cofrinho.data_concluido else None,
        "saldo": pago,
        "alvo": alvo,
        "restante": round(max(0.0, alvo - pago), 2),
        "progresso": min(1.0, pago / alvo) if alvo > 0 else None,
        "parcelas": parcelas,
        "parcelasPagas": sum(1 for c in contas if c.situacao == "pago"),
        "parcelasTotais": len(contas),
        "aporteSugerido": round(pendentes[0].valor, 2) if pendentes else None,
        "projecaoFinal": projecao_final,
    }


def sincronizar_todos(db: Session, usuario: Usuario) -> bool:
    mudou = False
    for cofrinho in db.query(Cofrinho).filter(Cofrinho.id_usuario == usuario.id).all():
        if sincronizar(db, usuario, cofrinho):
            mudou = True
    return mudou
