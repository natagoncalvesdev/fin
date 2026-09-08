"""Concessão de medalhas (Conquista).

Regras:
  - "peso_inicio": ao registrar o primeiro peso.
  - "peso_perda:N": a cada N kg perdidos desde o primeiro peso registrado
    (N em MARCOS_PESO_KG).
  - "meta_peso:<uuid>": ao atingir uma meta de peso.
  - "meta_guardar:<uuid>": ao concluir um cofrinho.

Toda medalha é permanente: uma vez concedida, não some se a meta/cofrinho
depois for revertido ou apagado. `chave` garante que não há duplicata.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import Conquista, MetaPeso, RegistroPeso, Usuario

MARCOS_PESO_KG = [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]


def _fmt_kg(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",")


def _fmt_brl(valor: float) -> str:
    inteiro = f"{valor:,.2f}"
    return "R$ " + inteiro.replace(",", "@").replace(".", ",").replace("@", ".")


def conceder(
    db: Session,
    usuario: Usuario,
    *,
    tipo: str,
    chave: str,
    titulo: str,
    descricao: str,
    icone: str,
    valor: float | None = None,
    quando: date | None = None,
) -> bool:
    """Cria a medalha se ainda não existir (dedup por `chave`). Retorna True se criou."""
    ja_tem = (
        db.query(Conquista)
        .filter(Conquista.id_usuario == usuario.id, Conquista.chave == chave)
        .first()
    )
    if ja_tem:
        return False
    db.add(
        Conquista(
            id_usuario=usuario.id,
            tipo=tipo,
            chave=chave,
            titulo=titulo,
            descricao=descricao,
            icone=icone,
            valor=valor,
            data_conquista=quando or date.today(),
        )
    )
    return True


def conceder_meta_peso(db: Session, usuario: Usuario, meta: MetaPeso) -> bool:
    if meta.situacao != "atingida":
        return False
    alvo = _fmt_kg(meta.peso_alvo)
    quando = meta.data_atingida or date.today()
    return conceder(
        db,
        usuario,
        tipo="meta_peso",
        chave=f"meta_peso:{meta.uuid}",
        titulo=f"Meta de {alvo} kg",
        descricao=f"Você atingiu {alvo} kg em {quando.strftime('%d/%m/%Y')}.",
        icone="alvo",
        valor=meta.peso_alvo,
        quando=quando,
    )


def conceder_cofrinho(
    db: Session, usuario: Usuario, cofrinho, *, alvo: float, quando: date
) -> bool:
    return conceder(
        db,
        usuario,
        tipo="meta_guardar",
        chave=f"meta_guardar:{cofrinho.uuid}",
        titulo=cofrinho.nome,
        descricao=(
            f'Você guardou {_fmt_brl(alvo)} no cofrinho "{cofrinho.nome}" '
            f"em {quando.strftime('%d/%m/%Y')}."
        ),
        icone="cofre",
        valor=alvo,
        quando=quando,
    )


def sincronizar_peso(db: Session, usuario: Usuario) -> bool:
    """Concede as medalhas automáticas de peso (início da jornada + marcos de
    perda). Idempotente. Retorna True se criou alguma."""
    pesos = (
        db.query(RegistroPeso)
        .filter(RegistroPeso.id_usuario == usuario.id)
        .order_by(RegistroPeso.data_registro.asc(), RegistroPeso.id.asc())
        .all()
    )
    if not pesos:
        return False

    mudou = False
    primeiro = pesos[0]
    if conceder(
        db,
        usuario,
        tipo="peso_inicio",
        chave="peso_inicio",
        titulo="Início da jornada",
        descricao=(
            f"Primeiro peso registrado: {_fmt_kg(primeiro.peso)} kg em "
            f"{primeiro.data_registro.strftime('%d/%m/%Y')}."
        ),
        icone="bandeira",
        valor=primeiro.peso,
        quando=primeiro.data_registro,
    ):
        mudou = True

    base = primeiro.peso
    for marco in MARCOS_PESO_KG:
        alvo = base - marco
        atingido = next((p for p in pesos if p.peso <= alvo + 1e-9), None)
        if not atingido:
            continue
        if conceder(
            db,
            usuario,
            tipo="peso_perda",
            chave=f"peso_perda:{marco}",
            titulo=f"-{marco} kg",
            descricao=(
                f"Você perdeu {marco} kg desde o início "
                f"({atingido.data_registro.strftime('%d/%m/%Y')})."
            ),
            icone="balanca",
            valor=float(marco),
            quando=atingido.data_registro,
        ):
            mudou = True

    return mudou


def listar(db: Session, usuario: Usuario) -> list[dict]:
    itens = (
        db.query(Conquista)
        .filter(Conquista.id_usuario == usuario.id)
        .order_by(Conquista.data_conquista.desc(), Conquista.id.desc())
        .all()
    )
    return [{"id": c.uuid, "data": c.to_dict()} for c in itens]
