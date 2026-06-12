import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    adm: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meses: Mapped[list["MesFinanceiro"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    categorias: Mapped[list["Categoria"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    cartoes: Mapped[list["Cartao"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    veiculos: Mapped[list["Veiculo"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class MesFinanceiro(Base):
    """Cabeçalho do período (usuário + ano + mês). Itens ficam nas tabelas filhas."""

    __tablename__ = "meses_financeiros"
    __table_args__ = (UniqueConstraint("user_id", "ano", "mes", name="uq_user_ano_mes"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ano: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[str] = mapped_column(String(20), nullable=False)
    cartao_status: Mapped[str] = mapped_column(String(20), default="pendente")
    # Colunas legadas — usadas só para migração automática para tabelas normalizadas
    contas: Mapped[list] = mapped_column(JSON, default=list)
    adicionais: Mapped[list] = mapped_column(JSON, default=list)
    cartao: Mapped[list] = mapped_column(JSON, default=list)
    reservado: Mapped[list] = mapped_column(JSON, default=list)
    debito: Mapped[list] = mapped_column(JSON, default=list)
    vale_carga: Mapped[dict] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship(back_populates="meses")
    contas_items: Mapped[list["ContaFinanceira"]] = relationship(
        back_populates="mes", cascade="all, delete-orphan"
    )
    adicionais_items: Mapped[list["AdicionalFinanceiro"]] = relationship(
        back_populates="mes", cascade="all, delete-orphan"
    )
    debitos_items: Mapped[list["DebitoFinanceiro"]] = relationship(
        back_populates="mes", cascade="all, delete-orphan"
    )
    reservados_items: Mapped[list["ReservadoFinanceiro"]] = relationship(
        back_populates="mes", cascade="all, delete-orphan"
    )
    compras_cartao: Mapped[list["CompraCartao"]] = relationship(
        back_populates="mes", cascade="all, delete-orphan"
    )
    vale_cargas: Mapped[list["ValeCarga"]] = relationship(
        back_populates="mes", cascade="all, delete-orphan"
    )


class ContaFinanceira(Base):
    __tablename__ = "contas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mes_id: Mapped[int] = mapped_column(Integer, ForeignKey("meses_financeiros.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    categoria: Mapped[str] = mapped_column(String(255), default="")

    mes: Mapped["MesFinanceiro"] = relationship(back_populates="contas_items")


class AdicionalFinanceiro(Base):
    __tablename__ = "adicionais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mes_id: Mapped[int] = mapped_column(Integer, ForeignKey("meses_financeiros.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)

    mes: Mapped["MesFinanceiro"] = relationship(back_populates="adicionais_items")


class DebitoFinanceiro(Base):
    __tablename__ = "debitos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mes_id: Mapped[int] = mapped_column(Integer, ForeignKey("meses_financeiros.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    categoria: Mapped[str] = mapped_column(String(255), default="")

    mes: Mapped["MesFinanceiro"] = relationship(back_populates="debitos_items")


class ReservadoFinanceiro(Base):
    __tablename__ = "reservados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mes_id: Mapped[int] = mapped_column(Integer, ForeignKey("meses_financeiros.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    categoria: Mapped[str] = mapped_column(String(255), default="")

    mes: Mapped["MesFinanceiro"] = relationship(back_populates="reservados_items")


class CompraCartao(Base):
    __tablename__ = "compras_cartao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mes_id: Mapped[int] = mapped_column(Integer, ForeignKey("meses_financeiros.id", ondelete="CASCADE"), nullable=False)
    cartao_id: Mapped[str] = mapped_column(String(36), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    parcelas: Mapped[str] = mapped_column(String(50), default="À vista")
    recorrente: Mapped[bool] = mapped_column(Boolean, default=False)
    categoria: Mapped[str] = mapped_column(String(255), default="")

    mes: Mapped["MesFinanceiro"] = relationship(back_populates="compras_cartao")


class ValeCarga(Base):
    __tablename__ = "vale_cargas"
    __table_args__ = (UniqueConstraint("mes_id", "cartao_id", name="uq_vale_mes_cartao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mes_id: Mapped[int] = mapped_column(Integer, ForeignKey("meses_financeiros.id", ondelete="CASCADE"), nullable=False)
    cartao_id: Mapped[str] = mapped_column(String(36), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    mes: Mapped["MesFinanceiro"] = relationship(back_populates="vale_cargas")


class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped["User"] = relationship(back_populates="categorias")


class Cartao(Base):
    __tablename__ = "cartoes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), default="credito")
    bandeira: Mapped[str | None] = mapped_column(String(50), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_criacao: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="cartoes")

    def to_dict(self) -> dict:
        data = {
            "tipo": self.tipo,
            "dataCriacao": self.data_criacao.isoformat() + "Z",
        }
        if self.bandeira:
            data["bandeira"] = self.bandeira
        if self.numero:
            data["numero"] = self.numero
        if self.nome:
            data["nome"] = self.nome
        return data


class Veiculo(Base):
    __tablename__ = "veiculos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    km_inicial: Mapped[float] = mapped_column(Float, nullable=False)

    user: Mapped["User"] = relationship(back_populates="veiculos")
    abastecimentos: Mapped[list["Abastecimento"]] = relationship(
        back_populates="veiculo", cascade="all, delete-orphan"
    )
    manutencoes: Mapped[list["Manutencao"]] = relationship(
        back_populates="veiculo", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {"nome": self.nome, "kmInicial": self.km_inicial}


class Abastecimento(Base):
    __tablename__ = "abastecimentos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    veiculo_id: Mapped[str] = mapped_column(String(36), ForeignKey("veiculos.id", ondelete="CASCADE"), nullable=False)
    km_atual: Mapped[float] = mapped_column(Float, nullable=False)
    litros: Mapped[float] = mapped_column(Float, nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    km_rodado: Mapped[float] = mapped_column(Float, default=0)
    km_por_litro: Mapped[float] = mapped_column(Float, default=0)
    data: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    mes: Mapped[str] = mapped_column(String(20), nullable=False)
    ano: Mapped[str] = mapped_column(String(4), nullable=False)

    veiculo: Mapped["Veiculo"] = relationship(back_populates="abastecimentos")

    def to_dict(self) -> dict:
        return {
            "kmAtual": self.km_atual,
            "litros": self.litros,
            "valor": self.valor,
            "kmRodado": self.km_rodado,
            "kmPorLitro": self.km_por_litro,
            "data": self.data.isoformat() + "Z",
            "mes": self.mes,
            "ano": self.ano,
        }


class Manutencao(Base):
    __tablename__ = "manutencoes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    veiculo_id: Mapped[str] = mapped_column(String(36), ForeignKey("veiculos.id", ondelete="CASCADE"), nullable=False)
    descricao: Mapped[str] = mapped_column(String(500), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), default="Preventiva")
    data: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    mes: Mapped[str] = mapped_column(String(20), nullable=False)
    ano: Mapped[str] = mapped_column(String(4), nullable=False)

    veiculo: Mapped["Veiculo"] = relationship(back_populates="manutencoes")

    def to_dict(self) -> dict:
        return {
            "descricao": self.descricao,
            "valor": self.valor,
            "tipo": self.tipo,
            "data": self.data.isoformat() + "Z",
            "mes": self.mes,
            "ano": self.ano,
        }
