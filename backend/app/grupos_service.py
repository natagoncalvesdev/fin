"""Regras dos grupos. Hoje só grupos de saúde: dois rankings (kg perdidos e cm
perdidos) + um cartão por membro. A base de cada pessoa é o primeiro registro na
data em que ela entrou no grupo (`GrupoMembro.entrou_em`)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import Grupo, GrupoMembro, RegistroMedidas, RegistroPeso, Usuario

_CAMPOS_MEDIDA = [
    "pescoco", "peito", "cintura", "abdomen", "quadril",
    "braco_dir", "braco_esq", "coxa_dir", "coxa_esq",
    "panturrilha_dir", "panturrilha_esq",
]


def membros_ativos(db: Session, grupo: Grupo) -> list[GrupoMembro]:
    return (
        db.query(GrupoMembro)
        .filter(GrupoMembro.id_grupo == grupo.id, GrupoMembro.situacao == "ativo")
        .order_by(GrupoMembro.id.asc())
        .all()
    )


def _peso_atual(db: Session, id_usuario: int) -> float | None:
    ultimo = (
        db.query(RegistroPeso)
        .filter(RegistroPeso.id_usuario == id_usuario)
        .order_by(RegistroPeso.data_registro.desc(), RegistroPeso.id.desc())
        .first()
    )
    return ultimo.peso if ultimo else None


def _peso_base(db: Session, id_usuario: int, desde: date) -> RegistroPeso | None:
    return (
        db.query(RegistroPeso)
        .filter(RegistroPeso.id_usuario == id_usuario, RegistroPeso.data_registro >= desde)
        .order_by(RegistroPeso.data_registro.asc(), RegistroPeso.id.asc())
        .first()
    )


def _medida_base(db: Session, id_usuario: int, desde: date) -> RegistroMedidas | None:
    return (
        db.query(RegistroMedidas)
        .filter(RegistroMedidas.id_usuario == id_usuario, RegistroMedidas.data_registro >= desde)
        .order_by(RegistroMedidas.data_registro.asc(), RegistroMedidas.id.asc())
        .first()
    )


def _medida_recente(db: Session, id_usuario: int) -> RegistroMedidas | None:
    return (
        db.query(RegistroMedidas)
        .filter(RegistroMedidas.id_usuario == id_usuario)
        .order_by(RegistroMedidas.data_registro.desc(), RegistroMedidas.id.desc())
        .first()
    )


def _cm_perdidos(base: RegistroMedidas, recente: RegistroMedidas) -> float | None:
    total = 0.0
    houve = False
    for campo in _CAMPOS_MEDIDA:
        a, b = getattr(base, campo), getattr(recente, campo)
        if a is not None and b is not None:
            total += a - b
            houve = True
    return round(total, 1) if houve else None


def resumo_saude(db: Session, grupo: Grupo) -> dict:
    membros = membros_ativos(db, grupo)
    usuarios = {
        u.id: u
        for u in db.query(Usuario).filter(
            Usuario.id.in_([m.id_usuario for m in membros] or [0])
        ).all()
    }

    cartoes = []
    for membro in membros:
        usuario = usuarios.get(membro.id_usuario)
        if not usuario:
            continue
        desde = membro.entrou_em or membro.created_at.date()

        atual = _peso_atual(db, usuario.id)
        base_peso = _peso_base(db, usuario.id, desde)
        peso_perdido = (
            round(base_peso.peso - atual, 1)
            if base_peso is not None and atual is not None
            else None
        )

        base_med = _medida_base(db, usuario.id, desde)
        recente_med = _medida_recente(db, usuario.id)
        cm_perdidos = (
            _cm_perdidos(base_med, recente_med)
            if base_med is not None and recente_med is not None and base_med.id != recente_med.id
            else None
        )

        cartoes.append(
            {
                "nome": usuario.nome,
                "souDono": usuario.id == grupo.id_dono,
                "entrouEm": desde.isoformat(),
                "pesoAtual": atual,
                "pesoPerdido": peso_perdido,
                "cmPerdidos": cm_perdidos,
                "medidasRecentes": recente_med.to_dict() if recente_med else None,
            }
        )

    def ranking(chave: str) -> list[dict]:
        com = sorted(
            (c for c in cartoes if c[chave] is not None),
            key=lambda c: c[chave],
            reverse=True,
        )
        sem = [c for c in cartoes if c[chave] is None]
        linhas = [
            {"posicao": i + 1, "nome": c["nome"], "valor": c[chave]}
            for i, c in enumerate(com)
        ]
        linhas += [{"posicao": None, "nome": c["nome"], "valor": None} for c in sem]
        return linhas

    return {
        "rankingPeso": ranking("pesoPerdido"),
        "rankingMedidas": ranking("cmPerdidos"),
        "membros": cartoes,
    }
