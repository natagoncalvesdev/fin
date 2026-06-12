from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.financeiro_service import (
    ano_tem_meses,
    apply_mes_data,
    get_or_create_mes,
    init_ano_meses,
    mes_to_dict,
)
from app.models import MesFinanceiro, User

router = APIRouter(prefix="/api/financeiro", tags=["financeiro"])


def _garantir_mes_do_usuario(record: MesFinanceiro, user_id: str) -> None:
    if record.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")


class MesUpdateRequest(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("/anos/{ano}/exists")
def ano_exists(
    ano: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return {"exists": ano_tem_meses(db, current_user.id, ano), "ano": ano}


@router.post("/anos/{ano}/init")
def init_ano(
    ano: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    init_ano_meses(db, current_user.id, ano)
    return {"ok": True, "ano": ano}


@router.get("/anos/{ano}/meses/{mes}")
def get_mes(
    ano: int,
    mes: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    record = get_or_create_mes(db, current_user.id, ano, mes)
    _garantir_mes_do_usuario(record, current_user.id)
    return {"id": f"{ano}_{mes}", "data": mes_to_dict(db, record), "exists": True}


@router.put("/anos/{ano}/meses/{mes}")
def update_mes(
    ano: int,
    mes: str,
    body: MesUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    record = get_or_create_mes(db, current_user.id, ano, mes)
    _garantir_mes_do_usuario(record, current_user.id)
    apply_mes_data(db, record, body.data, current_user.id)
    db.commit()
    db.refresh(record)
    return {"id": f"{ano}_{mes}", "data": mes_to_dict(db, record), "exists": True}


@router.get("/anos/{ano}/meses")
def list_meses_ano(
    ano: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    records = (
        db.query(MesFinanceiro)
        .filter(MesFinanceiro.user_id == current_user.id, MesFinanceiro.ano == ano)
        .all()
    )
    return [{"mes": r.mes, "data": mes_to_dict(db, r)} for r in records]
