"""Regras de negócio de saúde: peso atual, avaliação de metas e sincronização
das medalhas automáticas de peso."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import conquistas_service
from app.models import MetaPeso, RegistroPeso, Usuario


def peso_atual(db: Session, usuario: Usuario) -> float | None:
    ultimo = (
        db.query(RegistroPeso)
        .filter(RegistroPeso.id_usuario == usuario.id)
        .order_by(RegistroPeso.data_registro.desc(), RegistroPeso.id.desc())
        .first()
    )
    return ultimo.peso if ultimo else None


def peso_atinge_meta(peso: float, meta: MetaPeso) -> bool:
    base = meta.peso_inicial
    if base is None:
        return abs(peso - meta.peso_alvo) <= 0.05
    if meta.peso_alvo <= base:
        return peso <= meta.peso_alvo
    return peso >= meta.peso_alvo


def sincronizar(db: Session, usuario: Usuario) -> bool:
    """Recalcula a situação das metas de peso a partir de todo o histórico e
    concede as medalhas automáticas (metas atingidas + marcos de peso).
    Idempotente. Retorna True se algo mudou."""
    mudou = conquistas_service.sincronizar_peso(db, usuario)

    metas = (
        db.query(MetaPeso)
        .filter(MetaPeso.id_usuario == usuario.id, MetaPeso.situacao != "arquivada")
        .all()
    )
    if not metas:
        return mudou

    pesos = (
        db.query(RegistroPeso)
        .filter(RegistroPeso.id_usuario == usuario.id)
        .order_by(RegistroPeso.data_registro.asc(), RegistroPeso.id.asc())
        .all()
    )

    for meta in metas:
        atingida_em = next(
            (
                p.data_registro
                for p in pesos
                if p.data_registro >= meta.data_criacao and peso_atinge_meta(p.peso, meta)
            ),
            None,
        )
        nova = "atingida" if atingida_em else "ativa"
        if meta.situacao != nova or meta.data_atingida != atingida_em:
            meta.situacao = nova
            meta.data_atingida = atingida_em
            mudou = True
        if nova == "atingida" and conquistas_service.conceder_meta_peso(db, usuario, meta):
            mudou = True
    return mudou
