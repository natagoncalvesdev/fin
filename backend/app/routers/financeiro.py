from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.financeiro_service import (
    ano_tem_meses,
    apply_mes_data,
    get_or_create_mes,
    init_ano_meses,
    list_meses_ano,
    mes_to_dict,
)
from app.models import Usuario

router = APIRouter(prefix="/api/financeiro", tags=["financeiro"])


class MesUpdateRequest(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("/anos/{ano}/exists")
def ano_exists(
    ano: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return {"exists": ano_tem_meses(db, current_user, ano), "ano": ano}


@router.post("/anos/{ano}/init")
def init_ano(
    ano: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    init_ano_meses(db, current_user, ano)
    return {"ok": True, "ano": ano}


@router.get("/anos/{ano}/meses/{mes}")
def get_mes(
    ano: int,
    mes: str,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    ref = get_or_create_mes(db, current_user, ano, mes)
    return {"id": f"{ano}_{mes}", "data": mes_to_dict(db, ref), "exists": True}


@router.put("/anos/{ano}/meses/{mes}")
def update_mes(
    ano: int,
    mes: str,
    body: MesUpdateRequest,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    ref = get_or_create_mes(db, current_user, ano, mes)
    apply_mes_data(db, ref, body.data)
    db.commit()
    ref = get_or_create_mes(db, current_user, ano, mes)
    return {"id": f"{ano}_{mes}", "data": mes_to_dict(db, ref), "exists": True}


@router.get("/anos/{ano}/meses")
def list_meses_ano_endpoint(
    ano: int,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    refs = list_meses_ano(db, current_user, ano)
    return [{"mes": r.mes, "data": mes_to_dict(db, r)} for r in refs]
