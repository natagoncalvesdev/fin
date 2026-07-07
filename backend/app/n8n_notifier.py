"""Envio de mensagens ao Telegram via webhook n8n."""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.models import MESES

logger = logging.getLogger(__name__)


def formatar_brl(valor: float) -> str:
    negativo = valor < 0
    s = f"{abs(valor):,.2f}"
    inteiro, dec = s.rsplit(".", 1)
    inteiro = inteiro.replace(",", ".")
    prefixo = "R$ -" if negativo else "R$ "
    return f"{prefixo}{inteiro},{dec}"


def _mes_ano_label(data_iso: str | None) -> str:
    if not data_iso:
        return ""
    try:
        partes = data_iso.split("-")
        ano = int(partes[0])
        mes = int(partes[1])
        return f"{MESES[mes - 1]}/{ano}"
    except (IndexError, ValueError):
        return data_iso


def montar_mensagem_integracao(resultados: list[dict]) -> str:
    linhas: list[str] = []

    for resultado in resultados:
        if not resultado.get("ok"):
            linhas.append(f"❌ {resultado.get('erro') or 'Não foi possível processar a operação.'}")
            continue

        if resultado.get("acao") == "consulta":
            linhas.append(resultado.get("mensagem") or "Consulta sem resultados.")
            continue

        if resultado.get("acao") == "status_atualizado":
            status_label = "paga" if resultado.get("situacao") == "pago" else "pendente"
            periodo = _mes_ano_label(resultado.get("data"))
            sufixo = f" em {periodo}" if periodo else ""
            linhas.append(f"✅ Conta {resultado.get('descricao')} marcada como {status_label}{sufixo}")
            continue

        tipo = resultado.get("tipo") or ""
        rotulos = {
            "debito": "Despesa",
            "entrada": "Receita",
            "cartao": "Compra no cartão",
            "conta": "Conta",
            "reservado": "Reservado",
        }
        rotulo = rotulos.get(tipo, "Lançamento")
        descricao = resultado.get("descricao") or ""
        valor = resultado.get("valor")
        partes = [f"✅ {rotulo} registrada", f"📝 {descricao}"]
        if valor is not None and valor > 0:
            partes.append(f"💰 {formatar_brl(float(valor))}")
        parcelas = resultado.get("totalParcelas")
        if tipo == "cartao" and parcelas and parcelas != 1 and parcelas != "Recorrente":
            partes.append(f"📆 {parcelas}x")
        elif tipo == "cartao" and parcelas == "Recorrente":
            partes.append("🔁 Recorrente")
        linhas.append("\n".join(partes))

    if len(linhas) == 1:
        return linhas[0]
    return "Fin — atualizações\n\n" + "\n\n".join(linhas)


async def enviar_mensagem_telegram(chat_id: str, mensagem: str) -> tuple[bool, str | None]:
    chat = str(chat_id or "").strip()
    if not chat:
        return False, "chat_id ausente"

    webhook_url = settings.n8n_webhook_url
    if not webhook_url or "seu-n8n.com" in webhook_url:
        return False, "Webhook do n8n não configurado"

    payload = {"chat_id": chat, "mensagem": mensagem}
    headers: dict[str, str] = {}
    host_header = settings.n8n_webhook_host_header.strip()
    if host_header:
        headers["Host"] = host_header

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(webhook_url, json=payload, headers=headers or None)
            response.raise_for_status()
        logger.info("Mensagem enviada ao n8n via %s", webhook_url)
        return True, None
    except httpx.HTTPStatusError as exc:
        erro = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        logger.warning("Webhook n8n (%s) retornou erro: %s", webhook_url, erro)
        return False, erro
    except httpx.RequestError as exc:
        erro = str(exc)
        logger.warning("Falha ao conectar ao webhook n8n (%s): %s", webhook_url, erro)
        return False, erro
