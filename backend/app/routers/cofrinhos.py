from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import cofrinhos_service, usuarios_service
from app.auth import get_current_user
from app.database import get_db
from app.models import MESES, Cofrinho, CofrinhoParticipante, Conta, Usuario

router = APIRouter(prefix="/api/cofrinhos", tags=["cofrinhos"])


class CofrinhoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    valorAlvo: float | None = Field(default=None, gt=0, le=1_000_000_000)
    aporteMensal: float | None = Field(default=None, gt=0, le=1_000_000_000)
    mesAlvo: str
    anoAlvo: int = Field(ge=2000, le=2100)


class CofrinhoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    valorAlvo: float | None = Field(default=None, gt=0, le=1_000_000_000)
    aporteMensal: float | None = Field(default=None, gt=0, le=1_000_000_000)
    mesAlvo: str | None = None
    anoAlvo: int | None = Field(default=None, ge=2000, le=2100)
    situacao: str | None = None


class ParticipanteInvite(BaseModel):
    email: str | None = None
    usuarioId: str | None = None


class AporteBody(BaseModel):
    aporteMensal: float = Field(gt=0, le=1_000_000_000)


def _checar_mes(mes: str) -> None:
    if mes not in MESES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mês inválido.")


def _checar_modo(valor_alvo: float | None, aporte_mensal: float | None) -> None:
    if (valor_alvo is None) == (aporte_mensal is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe um valor alvo OU um aporte mensal (apenas um dos dois).",
        )


def _get_dono_or_404(db: Session, cofrinho_uuid: str, usuario: Usuario) -> Cofrinho:
    item = (
        db.query(Cofrinho)
        .filter(Cofrinho.uuid == cofrinho_uuid, Cofrinho.id_usuario == usuario.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cofrinho não encontrado.")
    return item


def _participacao(db: Session, cofrinho: Cofrinho, usuario: Usuario) -> CofrinhoParticipante | None:
    return (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.id_cofrinho == cofrinho.id,
            CofrinhoParticipante.id_usuario == usuario.id,
        )
        .first()
    )


def _get_visivel_or_404(db: Session, cofrinho_uuid: str, usuario: Usuario) -> Cofrinho:
    """Dono ou participante ativo."""
    item = db.query(Cofrinho).filter(Cofrinho.uuid == cofrinho_uuid).first()
    if item and item.id_usuario == usuario.id:
        return item
    if item:
        p = _participacao(db, item, usuario)
        if p and p.situacao == "ativo":
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cofrinho não encontrado.")


def _meus_cofrinhos(db: Session, usuario: Usuario) -> list[Cofrinho]:
    """Cofrinhos que o usuário criou + aqueles em que é participante ativo."""
    itens: dict[int, Cofrinho] = {
        c.id: c for c in db.query(Cofrinho).filter(Cofrinho.id_usuario == usuario.id).all()
    }
    participacoes = (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.id_usuario == usuario.id,
            CofrinhoParticipante.situacao == "ativo",
        )
        .all()
    )
    for p in participacoes:
        if p.id_cofrinho in itens:
            continue
        cofrinho = db.query(Cofrinho).filter(Cofrinho.id == p.id_cofrinho).first()
        if cofrinho:
            itens[cofrinho.id] = cofrinho
    return sorted(itens.values(), key=lambda c: (c.created_at, c.id), reverse=True)


@router.get("")
def list_cofrinhos(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinhos_service.sincronizar_todos(db, current_user)
    itens = [cofrinhos_service.payload(db, c, current_user) for c in _meus_cofrinhos(db, current_user)]
    # sincronizar_todos + payload podem ter criado linhas de participante-dono
    # (backfill) e concluído cofrinhos — persiste tudo.
    db.commit()
    return itens


@router.get("/convites")
def list_convites(
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    pendentes = (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.id_usuario == current_user.id,
            CofrinhoParticipante.situacao == "pendente",
        )
        .all()
    )
    out = []
    for p in pendentes:
        cofrinho = db.query(Cofrinho).filter(Cofrinho.id == p.id_cofrinho).first()
        if not cofrinho:
            continue
        dono = db.query(Usuario).filter(Usuario.id == cofrinho.id_usuario).first()
        out.append(
            {
                "id": p.uuid,
                "cofrinhoNome": cofrinho.nome,
                "donoNome": dono.nome if dono else "—",
                "valorAlvo": cofrinho.valor_alvo,
                "mesAlvo": cofrinho.mes_alvo,
                "anoAlvo": cofrinho.ano_alvo,
            }
        )
    return out


@router.post("/convites/{convite_id}/aceitar")
def aceitar_convite(
    convite_id: str,
    body: AporteBody,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    p = (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.uuid == convite_id,
            CofrinhoParticipante.id_usuario == current_user.id,
            CofrinhoParticipante.situacao == "pendente",
        )
        .first()
    )
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite não encontrado.")
    cofrinho = db.query(Cofrinho).filter(Cofrinho.id == p.id_cofrinho).first()
    if not cofrinho:
        db.delete(p)
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cofrinho não encontrado.")
    p.situacao = "ativo"
    p.aporte_mensal = body.aporteMensal
    p.entrou_em = date.today()
    db.flush()
    cofrinhos_service.gerar_parcelas_participante(db, cofrinho, p)
    cofrinhos_service.sincronizar(db, cofrinho)
    db.commit()
    return {"ok": True}


@router.post("/convites/{convite_id}/recusar")
def recusar_convite(
    convite_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    p = (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.uuid == convite_id,
            CofrinhoParticipante.id_usuario == current_user.id,
            CofrinhoParticipante.situacao == "pendente",
        )
        .first()
    )
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite não encontrado.")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_cofrinho(
    body: CofrinhoCreate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _checar_mes(body.mesAlvo)
    _checar_modo(body.valorAlvo, body.aporteMensal)
    cofrinho = Cofrinho(
        id_usuario=current_user.id,
        nome=body.nome.strip(),
        valor_alvo=body.valorAlvo,
        aporte_mensal=body.aporteMensal,
        mes_alvo=body.mesAlvo,
        ano_alvo=body.anoAlvo,
        data_inicio=date.today(),
        situacao="ativo",
    )
    db.add(cofrinho)
    db.flush()
    cofrinhos_service.garantir_dono(db, cofrinho)
    cofrinhos_service.gerar_parcelas(db, cofrinho)
    db.commit()
    db.refresh(cofrinho)
    return cofrinhos_service.payload(db, cofrinho, current_user)


@router.put("/{cofrinho_id}")
def update_cofrinho(
    cofrinho_id: str,
    body: CofrinhoUpdate,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_dono_or_404(db, cofrinho_id, current_user)
    cofrinhos_service.garantir_dono(db, cofrinho)
    enviados = body.model_fields_set
    cronograma_mudou = False

    if body.nome is not None and body.nome.strip() != cofrinho.nome:
        cofrinho.nome = body.nome.strip()
        for conta in db.query(Conta).filter(Conta.id_cofrinho == cofrinho.id):
            conta.nome = f"Cofrinho: {cofrinho.nome}"
    if body.mesAlvo is not None:
        _checar_mes(body.mesAlvo)
        cofrinho.mes_alvo = body.mesAlvo
        cronograma_mudou = True
    if body.anoAlvo is not None:
        cofrinho.ano_alvo = body.anoAlvo
        cronograma_mudou = True

    compartilhado = cofrinhos_service.is_compartilhado(db, cofrinho)
    if "valorAlvo" in enviados:
        cofrinho.valor_alvo = body.valorAlvo
        cronograma_mudou = True
    if "aporteMensal" in enviados:
        if compartilhado:
            # o dono edita o próprio aporte pela linha de participante
            dono = cofrinhos_service.garantir_dono(db, cofrinho)
            dono.aporte_mensal = body.aporteMensal
        else:
            cofrinho.aporte_mensal = body.aporteMensal
            dono = cofrinhos_service.garantir_dono(db, cofrinho)
            dono.aporte_mensal = body.aporteMensal
        cronograma_mudou = True
    if ("valorAlvo" in enviados or "aporteMensal" in enviados) and not compartilhado:
        _checar_modo(cofrinho.valor_alvo, cofrinho.aporte_mensal)
    if compartilhado and cofrinho.valor_alvo is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uma caixinha compartilhada precisa de um valor alvo.",
        )
    if body.situacao is not None:
        if body.situacao not in ("ativo", "arquivado"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Situação deve ser 'ativo' ou 'arquivado'.",
            )
        cofrinho.situacao = body.situacao
        if body.situacao == "arquivado":
            cofrinho.data_concluido = None

    db.flush()
    if cronograma_mudou:
        cofrinhos_service.apagar_parcelas_pendentes(db, cofrinho)
        cofrinhos_service.gerar_parcelas(db, cofrinho)
        cofrinhos_service.recalcular_pendentes(db, cofrinho)
    cofrinhos_service.sincronizar(db, cofrinho)
    db.commit()
    db.refresh(cofrinho)
    return cofrinhos_service.payload(db, cofrinho, current_user)


@router.delete("/{cofrinho_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cofrinho(
    cofrinho_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_dono_or_404(db, cofrinho_id, current_user)
    # Parcelas pendentes (de todos os participantes) somem; as já pagas ficam no
    # financeiro sem vínculo — é dinheiro que de fato saiu da conta.
    for conta in db.query(Conta).filter(Conta.id_cofrinho == cofrinho.id).all():
        if conta.situacao == "pago":
            conta.id_cofrinho = None
        else:
            db.delete(conta)
    db.flush()
    db.delete(cofrinho)  # cascade remove as linhas de cofrinho_participante
    db.commit()


@router.post("/{cofrinho_id}/participantes", status_code=status.HTTP_201_CREATED)
def add_participante(
    cofrinho_id: str,
    body: ParticipanteInvite,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_dono_or_404(db, cofrinho_id, current_user)
    alvo = usuarios_service.resolver(db, email=body.email, usuario_id=body.usuarioId)
    if alvo.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Você já participa.")
    if _participacao(db, cofrinho, alvo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Essa pessoa já foi convidada."
        )
    cofrinhos_service.converter_para_compartilhado(db, cofrinho)
    db.add(
        CofrinhoParticipante(
            id_cofrinho=cofrinho.id,
            id_usuario=alvo.id,
            papel="membro",
            situacao="pendente",
            convidado_por=current_user.id,
        )
    )
    db.commit()
    return {"ok": True}


@router.put("/{cofrinho_id}/participantes/me")
def editar_meu_aporte(
    cofrinho_id: str,
    body: AporteBody,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = _get_visivel_or_404(db, cofrinho_id, current_user)
    p = _participacao(db, cofrinho, current_user)
    if not p or p.situacao != "ativo":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Você não participa.")
    p.aporte_mensal = body.aporteMensal
    db.flush()
    cofrinhos_service.apagar_parcelas_pendentes(db, cofrinho, p)
    cofrinhos_service.gerar_parcelas_participante(db, cofrinho, p)
    cofrinhos_service.sincronizar(db, cofrinho)
    db.commit()
    db.refresh(cofrinho)
    return cofrinhos_service.payload(db, cofrinho, current_user)


@router.delete("/{cofrinho_id}/participantes/{participante_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_participante(
    cofrinho_id: str,
    participante_id: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    cofrinho = db.query(Cofrinho).filter(Cofrinho.uuid == cofrinho_id).first()
    if not cofrinho:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cofrinho não encontrado.")
    p = (
        db.query(CofrinhoParticipante)
        .filter(
            CofrinhoParticipante.uuid == participante_id,
            CofrinhoParticipante.id_cofrinho == cofrinho.id,
        )
        .first()
    )
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participante não encontrado.")
    # O dono remove qualquer membro; um membro só remove a si mesmo.
    if cofrinho.id_usuario != current_user.id and p.id_usuario != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão.")
    if p.papel == "dono":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O dono não pode sair da própria caixinha.",
        )
    for conta in (
        db.query(Conta)
        .filter(Conta.id_cofrinho == cofrinho.id, Conta.id_usuario == p.id_usuario)
        .all()
    ):
        if conta.situacao == "pago":
            conta.id_cofrinho = None
        else:
            db.delete(conta)
    db.delete(p)
    db.flush()
    cofrinhos_service.sincronizar(db, cofrinho)
    db.commit()
