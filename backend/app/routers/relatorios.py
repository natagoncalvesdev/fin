from typing import Annotated

import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.financeiro_service import get_or_create_mes, mes_to_dict
from app.models import MESES, Usuario

router = APIRouter(prefix="/api/relatorios", tags=["relatorios"])
logger = logging.getLogger(__name__)


class GerarRelatorioRequest(BaseModel):
    ano: int = Field(ge=2000, le=2100)
    mes: str = Field(min_length=1, max_length=20)


class GerarRelatorioResponse(BaseModel):
    ok: bool
    message: str


def _formatar_brl(valor: float) -> str:
    negativo = valor < 0
    s = f"{abs(valor):,.2f}"
    inteiro, dec = s.rsplit(".", 1)
    inteiro = inteiro.replace(",", ".")
    prefixo = "R$ -" if negativo else "R$ "
    return f"{prefixo}{inteiro},{dec}"


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

    payload = {
        "chat_id": current_user.id_telegram,
        "mensagem": mensagem,
    }

    webhook_url = settings.n8n_webhook_relatorio_url
    if "seu-n8n.com" in webhook_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook do n8n não configurado. Defina N8N_WEBHOOK_RELATORIO_URL no servidor.",
        )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        logger.warning(
            "Webhook n8n retornou erro HTTP %s para %s: %s",
            status_code,
            webhook_url,
            exc.response.text[:500],
        )
        if status_code == 404:
            detail = (
                "Workflow do n8n não encontrado ou inativo. "
                "Ative o workflow com o webhook 'relatorio-fin' no n8n."
            )
        else:
            detail = f"O n8n retornou erro {status_code}. Verifique o workflow e tente novamente."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
    except httpx.RequestError as exc:
        logger.warning("Falha ao conectar ao webhook n8n %s: %s", webhook_url, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível conectar ao n8n. Verifique a URL do webhook no servidor.",
        ) from exc

    return GerarRelatorioResponse(ok=True, message="Relatório enviado com sucesso.")
