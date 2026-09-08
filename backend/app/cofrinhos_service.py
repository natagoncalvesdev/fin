"""Cofrinhos (metas de economia), individuais ou compartilhados.

Ao criar um cofrinho, geramos uma **parcela por mês** como uma linha em `conta`
("Cofrinho: <nome>") para cada participante. O usuário paga essas contas
normalmente na tela de Contas (ou pelo próprio cofrinho); marcar como paga =
guardar aquele valor. O montante do cofrinho é a soma das parcelas pagas de
**todos** os participantes.

Cofrinho **solo** (só o dono ativo): comportamento clássico — modo "valor alvo"
redistribui as parcelas pendentes para fechar no alvo; modo "aporte mensal" tem
parcela fixa e mostra projeção.

Cofrinho **compartilhado** (o dono convidou alguém): `valor_alvo` é a meta única;
cada participante tem o próprio `aporte_mensal` fixo (sem redistribuição) e as
parcelas dele entram nas contas dele. Conclui quando a soma paga alcança o alvo —
medalha para cada participante ativo.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app import conquistas_service
from app.models import MESES, Cofrinho, CofrinhoParticipante, Conta, Usuario

CATEGORIA_COFRINHO = "Cofrinho"


def _mes_idx(nome: str | None) -> int | None:
    return MESES.index(nome) if nome in MESES else None


def _tem_prazo(cofrinho: Cofrinho) -> bool:
    return _mes_idx(cofrinho.mes_alvo) is not None and bool(cofrinho.ano_alvo)


def _modo(cofrinho: Cofrinho) -> str:
    return "valor_prazo" if cofrinho.valor_alvo is not None else "aporte_prazo"


def _meses_plano(cofrinho: Cofrinho, desde: date | None = None) -> list[tuple[int, str]]:
    """(ano, nome do mês) de cada parcela — do mês inicial ao mês-alvo. `desde`
    (data de entrada de um participante) nunca recua antes de `data_inicio`."""
    if not _tem_prazo(cofrinho):
        return []
    ini = desde or cofrinho.data_inicio
    if ini < cofrinho.data_inicio:
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


# ---------------------------------------------------------------------------
# Participantes
# ---------------------------------------------------------------------------


def garantir_dono(db: Session, cofrinho: Cofrinho) -> CofrinhoParticipante:
    """Cria a linha do participante-dono se não existir (backfill dos cofrinhos
    criados antes do compartilhamento). O aporte do dono nasce de
    `cofrinho.aporte_mensal`."""
    dono = (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.id_cofrinho == cofrinho.id,
            CofrinhoParticipante.id_usuario == cofrinho.id_usuario,
        )
        .first()
    )
    if dono:
        return dono
    dono = CofrinhoParticipante(
        id_cofrinho=cofrinho.id,
        id_usuario=cofrinho.id_usuario,
        papel="dono",
        situacao="ativo",
        aporte_mensal=cofrinho.aporte_mensal,
        entrou_em=cofrinho.data_inicio,
    )
    db.add(dono)
    db.flush()
    return dono


def participantes_ativos(db: Session, cofrinho: Cofrinho) -> list[CofrinhoParticipante]:
    return (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.id_cofrinho == cofrinho.id,
            CofrinhoParticipante.situacao == "ativo",
        )
        .order_by(CofrinhoParticipante.id.asc())
        .all()
    )


def _tem_membros(db: Session, cofrinho: Cofrinho) -> bool:
    """True se o dono já convidou alguém (pendente ou ativo) — a partir daí o
    cofrinho é tratado como compartilhado (aportes fixos, sem redistribuição)."""
    return (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.id_cofrinho == cofrinho.id,
            CofrinhoParticipante.papel == "membro",
        )
        .count()
        > 0
    )


def is_compartilhado(db: Session, cofrinho: Cofrinho) -> bool:
    return _tem_membros(db, cofrinho)


def _usuario(db: Session, id_usuario: int) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.id == id_usuario).first()


# ---------------------------------------------------------------------------
# Parcelas (contas)
# ---------------------------------------------------------------------------


def _contas(
    db: Session, cofrinho: Cofrinho, participante: CofrinhoParticipante | None = None
) -> list[Conta]:
    query = db.query(Conta).filter(Conta.id_cofrinho == cofrinho.id)
    if participante is not None:
        query = query.filter(Conta.id_usuario == participante.id_usuario)
    return query.order_by(Conta.data_conta.asc(), Conta.id.asc()).all()


def _alvo(db: Session, cofrinho: Cofrinho) -> float:
    """Meta efetiva. Compartilhado / modo valor: `valor_alvo`. Solo modo aporte:
    aporte do dono × nº de meses do plano."""
    if cofrinho.valor_alvo is not None:
        return float(cofrinho.valor_alvo)
    dono = garantir_dono(db, cofrinho)
    return float(dono.aporte_mensal or 0) * max(1, len(_meses_plano(cofrinho)))


def gerar_parcelas_participante(
    db: Session, cofrinho: Cofrinho, participante: CofrinhoParticipante
) -> None:
    """Cria as contas mensais que ainda faltam para um participante."""
    from app.financeiro_service import criar_conta

    usuario = _usuario(db, participante.id_usuario)
    if usuario is None:
        return
    desde = participante.entrou_em or cofrinho.data_inicio
    meses = _meses_plano(cofrinho, desde=desde)
    if not meses:
        return
    existentes = {
        (c.data_conta.year, MESES[c.data_conta.month - 1])
        for c in _contas(db, cofrinho, participante)
    }
    if is_compartilhado(db, cofrinho) or participante.aporte_mensal is not None:
        valor = float(participante.aporte_mensal or 0)
    else:
        valor = float(cofrinho.valor_alvo or 0) / len(meses)
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


def gerar_parcelas(db: Session, cofrinho: Cofrinho) -> None:
    garantir_dono(db, cofrinho)
    for participante in participantes_ativos(db, cofrinho):
        gerar_parcelas_participante(db, cofrinho, participante)


def apagar_parcelas_pendentes(
    db: Session, cofrinho: Cofrinho, participante: CofrinhoParticipante | None = None
) -> None:
    for conta in _contas(db, cofrinho, participante):
        if conta.situacao != "pago":
            db.delete(conta)
    db.flush()


def recalcular_pendentes(db: Session, cofrinho: Cofrinho) -> bool:
    """Redistribui o que falta entre as parcelas pendentes. Só no modo valor e
    só enquanto o cofrinho é solo."""
    if cofrinho.valor_alvo is None or is_compartilhado(db, cofrinho):
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


def converter_para_compartilhado(db: Session, cofrinho: Cofrinho) -> None:
    """Chamado na 1ª vez que o dono convida alguém. Congela o aporte do dono (se
    ele estava no modo valor) e garante uma meta única (`valor_alvo`)."""
    dono = garantir_dono(db, cofrinho)
    if dono.aporte_mensal is None:
        pendentes = [c for c in _contas(db, cofrinho, dono) if c.situacao != "pago"]
        meses = _meses_plano(cofrinho)
        if pendentes:
            dono.aporte_mensal = round(pendentes[0].valor, 2)
        elif cofrinho.valor_alvo and meses:
            dono.aporte_mensal = round(float(cofrinho.valor_alvo) / len(meses), 2)
        else:
            dono.aporte_mensal = 0.0
    if cofrinho.valor_alvo is None:
        meses = max(1, len(_meses_plano(cofrinho)))
        cofrinho.valor_alvo = round(float(dono.aporte_mensal or 0) * meses, 2)
    db.flush()


# ---------------------------------------------------------------------------
# Sincronização (conclusão + medalhas)
# ---------------------------------------------------------------------------


def sincronizar(db: Session, cofrinho: Cofrinho) -> bool:
    """Conclui o cofrinho quando o total pago (de todos) alcança o alvo — medalha
    permanente para cada participante ativo — e reverte para ativo se cair
    abaixo. `arquivado` não muda sozinho."""
    garantir_dono(db, cofrinho)
    if cofrinho.situacao == "arquivado":
        return False
    contas = _contas(db, cofrinho)
    pago = sum(c.valor for c in contas if c.situacao == "pago")
    alvo = _alvo(db, cofrinho)
    mudou = False
    if alvo > 0 and pago >= alvo - 0.005:
        quando = max(
            (c.data_conta for c in contas if c.situacao == "pago"), default=date.today()
        )
        if cofrinho.situacao != "concluido":
            cofrinho.situacao = "concluido"
            cofrinho.data_concluido = quando
            mudou = True
        for participante in participantes_ativos(db, cofrinho):
            usuario = _usuario(db, participante.id_usuario)
            if usuario and conquistas_service.conceder_cofrinho(
                db, usuario, cofrinho, alvo=round(alvo, 2), quando=quando
            ):
                mudou = True
    elif cofrinho.situacao == "concluido":
        cofrinho.situacao = "ativo"
        cofrinho.data_concluido = None
        mudou = True
    return mudou


def apos_mudanca_conta(db: Session, cofrinho: Cofrinho) -> bool:
    """Chamado quando uma conta ligada a um cofrinho é paga/editada/removida."""
    mudou = recalcular_pendentes(db, cofrinho)
    return sincronizar(db, cofrinho) or mudou


def sincronizar_todos(db: Session, usuario: Usuario) -> bool:
    """Sincroniza os cofrinhos do usuário (como dono) e aqueles em que ele é
    participante ativo."""
    mudou = False
    vistos: set[int] = set()

    for cofrinho in db.query(Cofrinho).filter(Cofrinho.id_usuario == usuario.id).all():
        garantir_dono(db, cofrinho)
        vistos.add(cofrinho.id)
        if sincronizar(db, cofrinho):
            mudou = True

    participacoes = (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.id_usuario == usuario.id,
            CofrinhoParticipante.situacao == "ativo",
        )
        .all()
    )
    for participante in participacoes:
        if participante.id_cofrinho in vistos:
            continue
        cofrinho = db.query(Cofrinho).filter(Cofrinho.id == participante.id_cofrinho).first()
        if cofrinho and sincronizar(db, cofrinho):
            mudou = True
    return mudou


# ---------------------------------------------------------------------------
# Payload para o frontend
# ---------------------------------------------------------------------------


def payload(db: Session, cofrinho: Cofrinho, eu: Usuario) -> dict:
    dono = garantir_dono(db, cofrinho)
    todos = (
        db.query(CofrinhoParticipante)
        .filter(CofrinhoParticipante.id_cofrinho == cofrinho.id)
        .order_by(CofrinhoParticipante.id.asc())
        .all()
    )
    contas_all = _contas(db, cofrinho)
    hoje = date.today()
    pago_total = round(sum(c.valor for c in contas_all if c.situacao == "pago"), 2)
    alvo = round(_alvo(db, cofrinho), 2)
    compartilhado = is_compartilhado(db, cofrinho)
    modo = "compartilhado" if compartilhado else _modo(cofrinho)

    minhas = [c for c in contas_all if c.id_usuario == eu.id]
    pendentes_minhas = [c for c in minhas if c.situacao != "pago"]

    projecao_final = None
    if not compartilhado and modo == "aporte_prazo":
        pendentes = [c for c in contas_all if c.situacao != "pago"]
        projecao_final = round(pago_total + sum(c.valor for c in pendentes), 2)

    nomes = {
        u.id: u.nome
        for u in db.query(Usuario)
        .filter(Usuario.id.in_([p.id_usuario for p in todos] or [0]))
        .all()
    }

    def guardado(participante: CofrinhoParticipante) -> float:
        return round(
            sum(
                c.valor
                for c in contas_all
                if c.id_usuario == participante.id_usuario and c.situacao == "pago"
            ),
            2,
        )

    participantes = [
        {
            "id": p.uuid,
            "nome": nomes.get(p.id_usuario, "—"),
            "papel": p.papel,
            "situacao": p.situacao,
            "aporteMensal": p.aporte_mensal,
            "guardado": guardado(p),
            "souEu": p.id_usuario == eu.id,
        }
        for p in todos
    ]
    meu = next((p for p in todos if p.id_usuario == eu.id), None)

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
        for c in minhas
    ]

    return {
        "id": cofrinho.uuid,
        "nome": cofrinho.nome,
        "modo": modo,
        "compartilhado": compartilhado,
        "souDono": cofrinho.id_usuario == eu.id,
        "meuAporte": meu.aporte_mensal if meu else None,
        "valorAlvo": cofrinho.valor_alvo,
        "aporteMensal": dono.aporte_mensal,
        "mesAlvo": cofrinho.mes_alvo,
        "anoAlvo": cofrinho.ano_alvo,
        "situacao": cofrinho.situacao,
        "dataConcluido": cofrinho.data_concluido.isoformat() if cofrinho.data_concluido else None,
        "saldo": pago_total,
        "alvo": alvo,
        "restante": round(max(0.0, alvo - pago_total), 2),
        "progresso": min(1.0, pago_total / alvo) if alvo > 0 else None,
        "parcelas": parcelas,
        "parcelasPagas": sum(1 for c in minhas if c.situacao == "pago"),
        "parcelasTotais": len(minhas),
        "aporteSugerido": round(pendentes_minhas[0].valor, 2) if pendentes_minhas else None,
        "projecaoFinal": projecao_final,
        "participantes": participantes,
    }
