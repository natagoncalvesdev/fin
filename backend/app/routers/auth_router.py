from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import Usuario

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    adm: bool
    phone: str | None = None
    cpf: str | None = None


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    cpf: str | None = Field(None, max_length=14)
    current_password: str | None = Field(None, min_length=6, max_length=128)
    new_password: str | None = Field(None, min_length=6, max_length=128)


def user_to_response(user: Usuario) -> UserResponse:
    return UserResponse(
        id=user.uuid,
        name=user.nome,
        email=user.email,
        adm=user.adm,
        phone=user.telefone,
        cpf=user.cpf,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Annotated[Session, Depends(get_db)]):
    existing = db.query(Usuario).filter(Usuario.email == body.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Este email já está em uso.")

    user = Usuario(
        nome=body.name.strip(),
        email=body.email.lower(),
        senha=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.uuid)
    return AuthResponse(token=token, user=user_to_response(user))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    user = db.query(Usuario).filter(Usuario.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.senha):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos.")

    token = create_access_token(user.uuid)
    return AuthResponse(token=token, user=user_to_response(user))


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[Usuario, Depends(get_current_user)]):
    return user_to_response(current_user)


@router.patch("/me", response_model=AuthResponse)
def update_me(
    body: UpdateProfileRequest,
    current_user: Annotated[Usuario, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    alterando_credencial = body.email is not None or body.new_password is not None
    if alterando_credencial:
        if not body.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe a senha atual para alterar email ou senha.",
            )
        if not verify_password(body.current_password, current_user.senha):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Senha atual incorreta.",
            )

    if body.name is not None:
        current_user.nome = body.name.strip()

    if body.email is not None:
        novo_email = body.email.lower()
        if novo_email != current_user.email:
            em_uso = (
                db.query(Usuario)
                .filter(Usuario.email == novo_email, Usuario.id != current_user.id)
                .first()
            )
            if em_uso:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Este email já está em uso.",
                )
            current_user.email = novo_email

    if body.new_password is not None:
        current_user.senha = hash_password(body.new_password)

    if body.phone is not None:
        current_user.telefone = body.phone.strip() or None

    if body.cpf is not None:
        current_user.cpf = body.cpf.strip() or None

    if (
        body.name is None
        and body.email is None
        and body.new_password is None
        and body.phone is None
        and body.cpf is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhuma alteração informada.",
        )

    db.commit()
    db.refresh(current_user)

    token = create_access_token(current_user.uuid)
    return AuthResponse(token=token, user=user_to_response(current_user))
