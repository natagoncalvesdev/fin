from typing import Annotated

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.financeiro_service import get_or_create_mes, mes_to_dict
from app.models import MESES, Usuario
from app.n8n_notifier import enviar_mensagem_telegram, formatar_brl

router = APIRouter(prefix="/api/relatorios", tags=["relatorios"])
logger = logging.getLogger(__name__)


class GerarRelatorioRequest(BaseModel):
    ano: int = Field(ge=2000, le=2100)
    mes: str = Field(min_length=1, max_length=20)


class GerarRelatorioResponse(BaseModel):
    ok: bool
    message: str


def _calcular_totais(data: dict) -> dict[str, float]:
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
        "saldo": saldo,
        "reservado": total_reservado,
    }


def _montar_mensagem(mes: str, totais: dict[str, float]) -> str:
    return (
        f"Relatório de {mes}\n"
        f"🔵Receita {_formatar_brl(totais['receita'])}\n"
        f"🔴Contas {_formatar_brl(totais['contas'])}\n"
        f"🟢Saldo {_formatar_brl(totais['saldo'])}\n"
        f"🟡Reservado {_formatar_brl(totais['reservado'])}"
    )


@router.post("/gerar", response_model=GerarRelatorioResponse)
async def gerar_relatorio(
    body: GerarRelatorioRequest,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if body.mes not in MESES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mês inválido.",
        )

    if not current_user.id_telegram:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID Telegram não configurado.",
        )

    ref = get_or_create_mes(db, current_user, body.ano, body.mes)
    data = mes_to_dict(db, ref)
    totais = _calcular_totais(data)
    mensagem = _montar_mensagem(body.mes, totais)

    enviado, erro_notificacao = await enviar_mensagem_telegram(current_user.id_telegram, mensagem)
    if not enviado:
        detail = erro_notificacao or "Não foi possível enviar a mensagem pelo n8n."
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{detail} Verifique o webhook no servidor.",
        )

    return GerarRelatorioResponse(ok=True, message="Relatório enviado com sucesso.")