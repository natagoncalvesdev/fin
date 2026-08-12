import re
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.financeiro_service import (
    atualizar_status_conta_integracao,
    executar_consulta_integracao,
    inserir_lancamento_integracao,
    is_tipo_consulta,
    resolver_usuario_por_chat_id,
)
from app.models import Cartao
from app.n8n_notifier import enviar_mensagem_telegram, montar_mensagem_integracao

router = APIRouter(prefix="/api/integracoes", tags=["integracoes"])


class LancamentoIntegracao(BaseModel):
    tipo: str = Field(min_length=1, max_length=50)
    valor: float = Field(ge=0)
    categoria: str = ""
    descricao: str = ""
    data: date
    chatId: str | int = Field(alias="chatId")
    final_cartao: str = ""
    cartaoId: str = ""
    totalParcelas: int = Field(default=1, ge=1, le=48)
    recorrente: bool = False
    situacao: bool | None = None

    model_config = {"populate_by_name": True}

    @field_validator("data", mode="before")
    @classmethod
    def parse_data(cls, value: Any) -> date:
        if isinstance(value, date):
            return value
        texto = str(value).strip()
        match = re.match(r"^(\d{4})-(\d{2})$", texto)
        if match:
            return date(int(match.group(1)), int(match.group(2)), 1)
        return date.fromisoformat(texto)

    @field_validator("descricao", mode="before")
    @classmethod
    def normalizar_descricao(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("chatId", mode="before")
    @classmethod
    def normalizar_chat_id(cls, value: Any) -> str | int:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("chatId é obrigatório.")
        return value

    @field_validator("situacao", mode="before")
    @classmethod
    def parse_situacao(cls, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalizado = value.strip().lower()
            if normalizado in ("true", "1", "pago", "paga", "sim"):
                return True
            if normalizado in ("false", "0", "pendente", "nao", "não"):
                return False
        raise ValueError("situacao inválida. Use true/false ou pago/pendente.")

    @property
    def referencia_cartao(self) -> str:
        return (self.final_cartao or self.cartaoId or "").strip()

    @property
    def is_atualizacao_status_conta(self) -> bool:
        tipo = self.tipo.strip().lower()
        return tipo in ("conta", "contas") and self.valor == 0 and self.situacao is not None

    @property
    def is_consulta(self) -> bool:
        return is_tipo_consulta(self.tipo)


class LancamentoResultado(BaseModel):
    ok: bool
    uuid: str | None = None
    tipo: str | None = None
    acao: str | None = None
    data: str | None = None
    descricao: str | None = None
    valor: float | None = None
    situacao: str | None = None
    mensagem: str | None = None
    erro: str | None = None


class InserirLancamentosResponse(BaseModel):
    ok: bool
    inseridos: int
    notificacao_enviada: bool = False
    notificacao_erro: str | None = None
    resultados: list[LancamentoResultado]


class CartaoIntegracaoResponse(BaseModel):
    final_cartao: str
    nome: str | None = None
    bandeira: str | None = None


def verificar_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> None:
    expected = settings.integration_api_key.strip()
    if not expected:
        return
    if not x_api_key or x_api_key.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida ou ausente. Envie o header X-API-Key.",
        )


@router.get("/cartoes", response_model=list[CartaoIntegracaoResponse])
def listar_cartoes_integracao(
    chatId: str,
    _: Annotated[None, Depends(verificar_api_key)],
    db: Annotated[Session, Depends(get_db)],
):
    usuario = resolver_usuario_por_chat_id(db, chatId)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário não encontrado para chatId {chatId}.",
        )

    cartoes = (
        db.query(Cartao)
        .filter(Cartao.id_usuario == usuario.id, Cartao.situacao == "ativo")
        .order_by(Cartao.created_at.desc())
        .all()
    )
    return [
        CartaoIntegracaoResponse(
            final_cartao=c.final_cartao or "",
            nome=c.nome,
            bandeira=c.bandeira,
        )
        for c in cartoes
    ]


@router.post("/lancamentos", response_model=InserirLancamentosResponse)
async def inserir_lancamentos(
    body: list[LancamentoIntegracao],
    _: Annotated[None, Depends(verificar_api_key)],
    db: Annotated[Session, Depends(get_db)],
):
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie ao menos um lançamento.",
        )

    resultados: list[LancamentoResultado] = []
    resultados_por_chat: dict[str, list[dict]] = {}
    inseridos = 0

    for item in body:
        chat_id = str(item.chatId).strip()
        descricao = item.descricao.strip()

        if not item.is_consulta and not descricao:
            resultado = LancamentoResultado(ok=False, erro="Descrição é obrigatória.")
            resultados.append(resultado)
            resultados_por_chat.setdefault(chat_id, []).append(resultado.model_dump())
            continue

        usuario = resolver_usuario_por_chat_id(db, item.chatId)
        if not usuario:
            resultado = LancamentoResultado(
                ok=False,
                erro=f"Usuário não encontrado para chatId {item.chatId}. Configure o ID Telegram no perfil.",
            )
            resultados.append(resultado)
            resultados_por_chat.setdefault(chat_id, []).append(resultado.model_dump())
            continue

        try:
            if item.is_consulta:
                payload = executar_consulta_integracao(
                    db,
                    usuario,
                    data_ref=item.data,
                    tipo=item.tipo,
                    final_cartao=item.referencia_cartao,
                )
            elif item.is_atualizacao_status_conta:
                payload = atualizar_status_conta_integracao(
                    db,
                    usuario,
                    data_ref=item.data,
                    descricao=descricao,
                    categoria=item.categoria,
                    pago=item.situacao,
                )
            else:
                payload = inserir_lancamento_integracao(
                    db,
                    usuario,
                    tipo=item.tipo,
                    data_lanc=item.data,
                    descricao=descricao,
                    valor=item.valor,
                    categoria=item.categoria,
                    cartao_id=item.referencia_cartao,
                    total_parcelas=item.totalParcelas,
                    recorrente=item.recorrente,
                )
            inseridos += 1
            resultado = LancamentoResultado(**payload)
            resultados.append(resultado)
            resultados_por_chat.setdefault(chat_id, []).append(payload)
        except ValueError as exc:
            resultado = LancamentoResultado(ok=False, erro=str(exc))
            resultados.append(resultado)
            resultados_por_chat.setdefault(chat_id, []).append(resultado.model_dump())

    if inseridos:
        db.commit()
    else:
        db.rollback()

    notificacao_enviada = False
    notificacao_erro: str | None = None
    for chat_id, payloads in resultados_por_chat.items():
        mensagem = montar_mensagem_integracao(payloads)
        enviado, erro = await enviar_mensagem_telegram(chat_id, mensagem)
        if enviado:
            notificacao_enviada = True
        elif erro:
            notificacao_erro = erro

    return InserirLancamentosResponse(
        ok=inseridos > 0,
        inseridos=inseridos,
        notificacao_enviada=notificacao_enviada,
        notificacao_erro=notificacao_erro,
        resultados=resultados,
    )
