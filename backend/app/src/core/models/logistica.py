"""Muestras, sample sets y transporte."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import EstadoSampleSet, MotivoDescarte

if TYPE_CHECKING:
    from .estudios import Estudio
    from .perfiles import Transportista
    from .turnos import CentroExtraccion


class SampleSet(TimestampMixin, Base):
    """Lote de 10 muestras; incompleto solo ante un Pompe urgente."""
    __tablename__ = "sample_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    estado: Mapped[EstadoSampleSet] = mapped_column(Enum(EstadoSampleSet), default=EstadoSampleSet.ABIERTO)
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime)
    es_pompe_urgente: Mapped[bool] = mapped_column(Boolean, default=False)
    csv_path: Mapped[str | None] = mapped_column(String(500))
    autorizacion_ministerio_pdf_path: Mapped[str | None] = mapped_column(String(500))
    # Retiro FedEx
    retiro_fedex_fecha: Mapped[datetime | None] = mapped_column(DateTime)
    retiro_fedex_lugar: Mapped[str | None] = mapped_column(String(255))
    retiro_fedex_url: Mapped[str | None] = mapped_column(String(500))      # URL de estado que devuelve FedEx
    retiro_fedex_pedido_id: Mapped[str | None] = mapped_column(String(100))

    muestras: Mapped[list[Muestra]] = relationship(back_populates="sample_set")


class Muestra(TimestampMixin, Base):
    __tablename__ = "muestras"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudios.id"), index=True)
    turno_id: Mapped[int | None] = mapped_column(ForeignKey("turnos.id"))
    sample_set_id: Mapped[int | None] = mapped_column(ForeignKey("sample_sets.id"), index=True)
    mililitros: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    tomada_en: Mapped[datetime | None] = mapped_column(DateTime)       # aviso por bot de Telegram
    llegada_lab_central: Mapped[datetime | None] = mapped_column(DateTime)
    # Si no sirve se descarta y se pide una nueva (remuestreo sin costo)
    motivo_descarte: Mapped[MotivoDescarte | None] = mapped_column(Enum(MotivoDescarte))

    estudio: Mapped[Estudio] = relationship(back_populates="muestras")
    sample_set: Mapped[SampleSet | None] = relationship(back_populates="muestras")


class OrdenDelDia(Base):
    """Recorrido diario fijo y ordenado del transportista (no se genera en feriados ni fines de semana)."""
    __tablename__ = "ordenes_del_dia"
    __table_args__ = (UniqueConstraint("transportista_id", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    transportista_id: Mapped[int] = mapped_column(ForeignKey("transportistas.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)

    transportista: Mapped[Transportista] = relationship(back_populates="ordenes_del_dia")
    paradas: Mapped[list[OrdenDelDiaParada]] = relationship(
        back_populates="orden", cascade="all, delete-orphan", order_by="OrdenDelDiaParada.posicion")
    posiciones: Mapped[list[PosicionTransporte]] = relationship(back_populates="orden")


class OrdenDelDiaParada(Base):
    __tablename__ = "ordenes_del_dia_paradas"
    __table_args__ = (UniqueConstraint("orden_id", "posicion"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes_del_dia.id", ondelete="CASCADE"))
    centro_id: Mapped[int] = mapped_column(ForeignKey("centros_extraccion.id"))
    posicion: Mapped[int] = mapped_column(Integer)
    retirada_en: Mapped[datetime | None] = mapped_column(DateTime)
    llegada_lab_central: Mapped[datetime | None] = mapped_column(DateTime)

    orden: Mapped[OrdenDelDia] = relationship(back_populates="paradas")
    centro: Mapped[CentroExtraccion] = relationship()


class PosicionTransporte(Base):
    """Posiciones registradas para el mapa de seguimiento (escenario 32)."""
    __tablename__ = "posiciones_transporte"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes_del_dia.id", ondelete="CASCADE"), index=True)
    latitud: Mapped[float] = mapped_column()
    longitud: Mapped[float] = mapped_column()
    registrada_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    orden: Mapped[OrdenDelDia] = relationship(back_populates="posiciones")
