"""Centros de extraccion y turnos."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .estudios import Estudio
    from .perfiles import Paciente


class CentroExtraccion(Base):
    __tablename__ = "centros_extraccion"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    direccion: Mapped[str] = mapped_column(String(255))
    provincia: Mapped[str] = mapped_column(String(80), index=True)
    latitud: Mapped[float] = mapped_column()
    longitud: Mapped[float] = mapped_column()

    turnos: Mapped[list[Turno]] = relationship(back_populates="centro")


class Turno(Base):
    """Slot de 15 minutos para una persona. Se crea al reservarlo (lunes a viernes, 9 a 18)."""
    __tablename__ = "turnos"

    id: Mapped[int] = mapped_column(primary_key=True)
    centro_id: Mapped[int] = mapped_column(ForeignKey("centros_extraccion.id"), index=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"), index=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudios.id"), index=True)
    inicio: Mapped[datetime] = mapped_column(DateTime)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)     # False si se cancelo
    asistio: Mapped[bool | None] = mapped_column(Boolean)         # None hasta que pasa el turno; False = ausente

    centro: Mapped[CentroExtraccion] = relationship(back_populates="turnos")
    paciente: Mapped[Paciente] = relationship(back_populates="turnos")
    estudio: Mapped[Estudio] = relationship(back_populates="turnos")

    __table_args__ = (
        # No puede haber dos turnos activos en el mismo centro y horario
        Index("uq_turno_activo", "centro_id", "inicio", unique=True,
              sqlite_where=text("activo"), postgresql_where=text("activo")),
    )
