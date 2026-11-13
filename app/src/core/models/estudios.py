"""Estudio de exoma y los genes a analizar."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import EstadoEstudio, OrigenGen

if TYPE_CHECKING:
    from .analisis import Analisis, DatosCrudos
    from .clinica import Gen, Patologia
    from .economia import Autorizacion, Demanda, ObraSocial, Presupuesto
    from .logistica import Muestra
    from .perfiles import Medico, Paciente
    from .turnos import Turno


class Estudio(TimestampMixin, Base):
    __tablename__ = "estudios"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"), index=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("medicos.id"), index=True)
    patologia_sospechada_id: Mapped[int] = mapped_column(ForeignKey("patologias.id"))
    estado: Mapped[EstadoEstudio] = mapped_column(Enum(EstadoEstudio), default=EstadoEstudio.CREADO, index=True)
    quiere_hallazgos_secundarios: Mapped[bool] = mapped_column(Boolean, default=False)
    obra_social_id: Mapped[int | None] = mapped_column(ForeignKey("obras_sociales.id"))
    es_pompe_urgente: Mapped[bool] = mapped_column(Boolean, default=False)   # Pompe y menor de 4 meses
    ausencias: Mapped[int] = mapped_column(Integer, default=0)               # llega a 5 -> vuelve a Creado

    paciente: Mapped[Paciente] = relationship(back_populates="estudios")
    medico: Mapped[Medico] = relationship(back_populates="estudios")
    patologia_sospechada: Mapped[Patologia] = relationship()
    obra_social: Mapped[ObraSocial | None] = relationship()
    genes: Mapped[list[EstudioGen]] = relationship(back_populates="estudio", cascade="all, delete-orphan")
    presupuesto: Mapped[Presupuesto | None] = relationship(back_populates="estudio", uselist=False)
    autorizaciones: Mapped[list[Autorizacion]] = relationship(back_populates="estudio", order_by="Autorizacion.id")
    demandas: Mapped[list[Demanda]] = relationship(back_populates="estudio")
    turnos: Mapped[list[Turno]] = relationship(back_populates="estudio")
    muestras: Mapped[list[Muestra]] = relationship(back_populates="estudio", order_by="Muestra.id")
    datos_crudos: Mapped[DatosCrudos | None] = relationship(back_populates="estudio", uselist=False)
    analisis: Mapped[list[Analisis]] = relationship(back_populates="estudio", order_by="Analisis.id")

    __table_args__ = (CheckConstraint("ausencias BETWEEN 0 AND 5"),)

    @property
    def muestra_vigente(self) -> Muestra | None:
        validas = [m for m in self.muestras if m.motivo_descarte is None]
        return validas[-1] if validas else None


class EstudioGen(Base):
    __tablename__ = "estudios_genes"

    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudios.id", ondelete="CASCADE"), primary_key=True)
    gen_id: Mapped[int] = mapped_column(ForeignKey("genes.id"), primary_key=True)
    origen: Mapped[OrigenGen] = mapped_column(Enum(OrigenGen))

    estudio: Mapped[Estudio] = relationship(back_populates="genes")
    gen: Mapped[Gen] = relationship()
