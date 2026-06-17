import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def new_uuid() -> str:
    return str(uuid.uuid4())


def mes_numero(mes: str) -> int:
    try:
        return MESES.index(mes) + 1
    except ValueError:
        return 1


def periodo_mes(ano: int, mes: str) -> tuple[date, date]:
    """Retorna [início, fim) do mês."""
    m = mes_numero(mes)
    inicio = date(ano, m, 1)
    if m == 12:
        fim = date(ano + 1, 1, 1)
    else:
        fim = date(ano, m + 1, 1)
    return inicio, fim


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    cpf: Mapped[str | None] = mapped_column(String(14), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    senha: Mapped[str] = mapped_column(String(255), nullable=False)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    id_telegram: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adm: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    categorias: Mapped[list["Categoria"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")
    cartoes: Mapped[list["Cartao"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")
    veiculos: Mapped[list["Veiculo"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")

    @property
    def id_externo(self) -> str:
        return self.uuid



class Categoria(Base):
    __tablename__ = "categoria"
    __table_args__ = (UniqueConstraint("id_usuario", "nome", name="uq_categoria_usuario_nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="categorias")


class Conta(Base):
    __tablename__ = "conta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    id_categoria: Mapped[int | None] = mapped_column(Integer, ForeignKey("categoria.id", ondelete="SET NULL"), nullable=True)
    data_conta: Mapped[date] = mapped_column(Date, nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    situacao: Mapped[str] = mapped_column(String(20), default="pendente")

    categoria: Mapped["Categoria | None"] = relationship()


class Entrada(Base):
    __tablename__ = "entrada"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    data_entrada: Mapped[date] = mapped_column(Date, nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)


class Cartao(Base):
    __tablename__ = "cartao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    final_cartao: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bandeira: Mapped[str | None] = mapped_column(String(50), nullable=True)
    nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vencimento: Mapped[int | None] = mapped_column(Integer, nullable=True)
    situacao: Mapped[str] = mapped_column(String(20), default="ativo")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    usuario: Mapped["Usuario"] = relationship(back_populates="cartoes")

    def to_dict(self) -> dict:
        data = {
            "dataCriacao": self.created_at.isoformat() + "Z",
            "situacao": self.situacao,
        }
        if self.bandeira:
            data["bandeira"] = self.bandeira
        if self.final_cartao:
            data["numero"] = self.final_cartao
        if self.nome:
            data["nome"] = self.nome
        if self.vencimento is not None:
            data["vencimento"] = self.vencimento
        return data


class CompraCartao(Base):
    __tablename__ = "compra_cartao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_cartao: Mapped[int] = mapped_column(Integer, ForeignKey("cartao.id", ondelete="CASCADE"), nullable=False, index=True)
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    data_compra_cartao: Mapped[date] = mapped_column(Date, nullable=False)
    data_competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    id_categoria: Mapped[int | None] = mapped_column(Integer, ForeignKey("categoria.id", ondelete="SET NULL"), nullable=True)
    compra: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    parcela_atual: Mapped[int] = mapped_column(Integer, default=1)
    parcela_total: Mapped[int] = mapped_column(Integer, default=1)
    recorrente: Mapped[bool] = mapped_column(Boolean, default=False)

    cartao: Mapped["Cartao"] = relationship()
    categoria: Mapped["Categoria | None"] = relationship()


class Debito(Base):
    __tablename__ = "debito"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    data_debito: Mapped[date] = mapped_column(Date, nullable=False)
    id_categoria: Mapped[int | None] = mapped_column(Integer, ForeignKey("categoria.id", ondelete="SET NULL"), nullable=True)
    compra: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)

    categoria: Mapped["Categoria | None"] = relationship()


class Reservado(Base):
    __tablename__ = "reservado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    data_reservado: Mapped[date] = mapped_column(Date, nullable=False)
    id_categoria: Mapped[int | None] = mapped_column(Integer, ForeignKey("categoria.id", ondelete="SET NULL"), nullable=True)
    compra: Mapped[str] = mapped_column(String(255), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)

    categoria: Mapped["Categoria | None"] = relationship()


class FaturaCartao(Base):
    """Status mensal da fatura de cartão (cartaoStatus no frontend)."""

    __tablename__ = "fatura_cartao"
    __table_args__ = (UniqueConstraint("id_usuario", "ano", "mes", name="uq_fatura_usuario_ano_mes"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid)
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    ano: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[str] = mapped_column(String(20), nullable=False)
    situacao: Mapped[str] = mapped_column(String(20), default="pendente")


class Veiculo(Base):
    __tablename__ = "veiculo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    placa: Mapped[str | None] = mapped_column(String(10), nullable=True)
    km_inicial: Mapped[float] = mapped_column(Float, nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="veiculos")
    abastecimentos: Mapped[list["VeiculoAbastecimento"]] = relationship(
        back_populates="veiculo", cascade="all, delete-orphan"
    )
    manutencoes: Mapped[list["ManutencaoVeiculo"]] = relationship(
        back_populates="veiculo", cascade="all, delete-orphan"
    )
    historicos: Mapped[list["VeiculoHistorico"]] = relationship(
        back_populates="veiculo", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {"nome": self.nome, "kmInicial": self.km_inicial, "placa": self.placa or ""}


class VeiculoHistorico(Base):
    __tablename__ = "veiculo_historico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid)
    id_veiculo: Mapped[int] = mapped_column(Integer, ForeignKey("veiculo.id", ondelete="CASCADE"), nullable=False)
    ultima_quilometragem: Mapped[float] = mapped_column(Float, nullable=False)
    data_registro: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    veiculo: Mapped["Veiculo"] = relationship(back_populates="historicos")


class VeiculoAbastecimento(Base):
    __tablename__ = "veiculo_abastecimento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_veiculo: Mapped[int] = mapped_column(Integer, ForeignKey("veiculo.id", ondelete="CASCADE"), nullable=False, index=True)
    data_abastecimento: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    quilometragem_atual: Mapped[float] = mapped_column(Float, nullable=False)
    litros_abastecido: Mapped[float] = mapped_column(Float, nullable=False)
    valor_abastecido: Mapped[float] = mapped_column(Float, nullable=False)
    tipo_combustivel: Mapped[str | None] = mapped_column(String(50), nullable=True)

    veiculo: Mapped["Veiculo"] = relationship(back_populates="abastecimentos")

    def to_dict(self) -> dict:
        dt = self.data_abastecimento
        return {
            "kmAtual": self.quilometragem_atual,
            "litros": self.litros_abastecido,
            "valor": self.valor_abastecido,
            "kmRodado": 0,
            "kmPorLitro": 0,
            "data": dt.isoformat() + "Z",
            "mes": MESES[dt.month - 1],
            "ano": str(dt.year),
            "tipoCombustivel": self.tipo_combustivel or "",
        }


class ManutencaoVeiculo(Base):
    __tablename__ = "manutencao_veiculo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=new_uuid, index=True)
    id_veiculo: Mapped[int] = mapped_column(Integer, ForeignKey("veiculo.id", ondelete="CASCADE"), nullable=False, index=True)
    data_manutencao: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    descricao: Mapped[str] = mapped_column(String(500), nullable=False)
    valor_manutencao: Mapped[float] = mapped_column(Float, nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), default="Preventiva")

    veiculo: Mapped["Veiculo"] = relationship(back_populates="manutencoes")

    def to_dict(self) -> dict:
        dt = self.data_manutencao
        return {
            "descricao": self.descricao,
            "valor": self.valor_manutencao,
            "tipo": self.tipo,
            "data": dt.isoformat() + "Z",
            "mes": MESES[dt.month - 1],
            "ano": str(dt.year),
        }
