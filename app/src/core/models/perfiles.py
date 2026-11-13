"""Perfiles por rol: medicos, transportistas y pacientes."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .clinica import Familiar, Patologia, Sintoma
    from .estudios import Estudio
    from .logistica import OrdenDelDia
    from .turnos import Turno
    from .usuarios import Usuario


class Especialidad(Base):
    __tablename__ = "especialidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)


class MedicoEspecialidad(Base):
    __tablename__ = "medicos_especialidades"

    medico_id: Mapped[int] = mapped_column(ForeignKey("medicos.id", ondelete="CASCADE"), primary_key=True)
    especialidad_id: Mapped[int] = mapped_column(ForeignKey("especialidades.id"), primary_key=True)


class Medico(Base):
    """Medico tratante/derivante. El gerente medico es un Medico con rol GERENTE_MEDICO."""
    __tablename__ = "medicos"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), unique=True)
    matricula: Mapped[str] = mapped_column(String(50), unique=True)

    usuario: Mapped[Usuario] = relationship(back_populates="medico")
    especialidades: Mapped[list[Especialidad]] = relationship(secondary="medicos_especialidades")
    pacientes: Mapped[list[Paciente]] = relationship(back_populates="medico")
    estudios: Mapped[list[Estudio]] = relationship(back_populates="medico")


class Transportista(Base):
    __tablename__ = "transportistas"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), unique=True)
    provincia: Mapped[str] = mapped_column(String(80), unique=True)   # uno por provincia

    usuario: Mapped[Usuario] = relationship(back_populates="transportista")
    ordenes_del_dia: Mapped[list[OrdenDelDia]] = relationship(back_populates="transportista")


class Paciente(Base):
    __tablename__ = "pacientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), unique=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("medicos.id"), index=True)   # medico que lo dio de alta
    dni: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    fecha_nacimiento: Mapped[date] = mapped_column(Date)
    diagnostico_presuntivo_id: Mapped[int] = mapped_column(ForeignKey("patologias.id"))
    historia_clinica: Mapped[str] = mapped_column(Text)
    tipo_sospecha: Mapped[str] = mapped_column(String(80))
    # PDF devuelto por la API de familiograma (puede no existir, escenario 19)
    familiograma_pdf_path: Mapped[str | None] = mapped_column(String(500))
    # Si es menor de edad, el padre realiza el proceso
    responsable_nombre: Mapped[str | None] = mapped_column(String(200))
    responsable_dni: Mapped[str | None] = mapped_column(String(20))

    usuario: Mapped[Usuario] = relationship(back_populates="paciente")
    medico: Mapped[Medico] = relationship(back_populates="pacientes")
    diagnostico_presuntivo: Mapped[Patologia] = relationship()
    sintomas: Mapped[list[Sintoma]] = relationship(secondary="pacientes_sintomas")
    familiares: Mapped[list[Familiar]] = relationship(back_populates="paciente", cascade="all, delete-orphan")
    estudios: Mapped[list[Estudio]] = relationship(back_populates="paciente")
    turnos: Mapped[list[Turno]] = relationship(back_populates="paciente")
