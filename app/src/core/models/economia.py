"""Obras sociales, cupones, presupuestos, pagos y autorizaciones."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import ResultadoAutorizacion, TipoPago

if TYPE_CHECKING:
    from .estudios import Estudio


class ObraSocial(Base):
    """Copia local de la API de obras sociales."""
    __tablename__ = "obras_sociales"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), unique=True)
    rnos: Mapped[str | None] = mapped_column(String(20), unique=True)   # codigo RNOS (SSSalud)
    porcentaje_cobertura: Mapped[Decimal] = mapped_column(Numeric(5, 2))   # 0-100

    __table_args__ = (CheckConstraint("porcentaje_cobertura BETWEEN 0 AND 100"),)


class Cupon(TimestampMixin, Base):
    __tablename__ = "cupones"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(80), unique=True)      # codigo numerico o contenido del QR
    qr_url: Mapped[str | None] = mapped_column(String(500))
    descuento_porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    gerente_id: Mapped[int] = mapped_column(ForeignKey("medicos.id"))       # gerente que lo creo
    medico_id: Mapped[int | None] = mapped_column(ForeignKey("medicos.id"))      # medico asignado
    paciente_id: Mapped[int | None] = mapped_column(ForeignKey("pacientes.id"))  # paciente asignado
    usado: Mapped[bool] = mapped_column(Boolean, default=False)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime)
    vigente_hasta: Mapped[datetime | None] = mapped_column(DateTime)   # la vigencia la valida el sistema de vouchers

    __table_args__ = (CheckConstraint("descuento_porcentaje BETWEEN 0 AND 100"),)


class Presupuesto(TimestampMixin, Base):
    __tablename__ = "presupuestos"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudios.id"), unique=True)
    emitido_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))   # administrativo
    cantidad_genes: Mapped[int] = mapped_column(Integer)
    monto_total_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))         # ver calcular_precio()

    estudio: Mapped[Estudio] = relationship(back_populates="presupuesto")
    pagos: Mapped[list[Pago]] = relationship(back_populates="presupuesto")


class Pago(Base):
    """Registro financiero. Si el paciente pierde el pago por 5 ausencias, se marca anulado."""
    __tablename__ = "pagos"

    id: Mapped[int] = mapped_column(primary_key=True)
    presupuesto_id: Mapped[int] = mapped_column(ForeignKey("presupuestos.id"), index=True)
    tipo: Mapped[TipoPago] = mapped_column(Enum(TipoPago))
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    cupon_id: Mapped[int | None] = mapped_column(ForeignKey("cupones.id"))
    descuento_cupon_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    cobertura_obra_social_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    anulado: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    presupuesto: Mapped[Presupuesto] = relationship(back_populates="pagos")
    cupon: Mapped[Cupon | None] = relationship()


class Autorizacion(Base):
    """Decision de la obra social. Una reautorizacion es una nueva fila para el mismo estudio."""
    __tablename__ = "autorizaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudios.id"), index=True)
    resultado: Mapped[ResultadoAutorizacion] = mapped_column(
        Enum(ResultadoAutorizacion), default=ResultadoAutorizacion.PENDIENTE)
    registrada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    demanda_id: Mapped[int | None] = mapped_column(ForeignKey("demandas.id"))   # si es reautorizacion
    # Id que devuelve la API de obras sociales al dar de alta el estudio (nombre del paciente + fecha);
    # la obra social autoriza o rechaza desde su propia web
    solicitud_externa_id: Mapped[str | None] = mapped_column(String(100), index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    estudio: Mapped[Estudio] = relationship(back_populates="autorizaciones")


class Demanda(Base):
    __tablename__ = "demandas"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudios.id"), index=True)
    pdf_path: Mapped[str] = mapped_column(String(500))     # decision judicial favorable
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    estudio: Mapped[Estudio] = relationship(back_populates="demandas")
