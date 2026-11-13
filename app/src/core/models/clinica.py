"""Clinica: patologias, sintomas, familiares, genes y variantes."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import ClasificacionVariante

if TYPE_CHECKING:
    from .perfiles import Paciente


class Patologia(TimestampMixin, Base):
    __tablename__ = "patologias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)   # Fabry, Pompe, MPS1, Gaucher, ASMD
    descripcion: Mapped[str | None] = mapped_column(Text)

    sintomas: Mapped[list[PatologiaSintoma]] = relationship(back_populates="patologia", cascade="all, delete-orphan")
    genes: Mapped[list[Gen]] = relationship(secondary="patologias_genes", back_populates="patologias")


class Sintoma(Base):
    """Sintoma codificado en SNOMED."""
    __tablename__ = "sintomas"

    id: Mapped[int] = mapped_column(primary_key=True)
    snomed_id: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    descripcion: Mapped[str] = mapped_column(String(255), index=True)


class PatologiaSintoma(Base):
    """Sintoma de una patologia: cardinal (uno) o secundario."""
    __tablename__ = "patologias_sintomas"

    patologia_id: Mapped[int] = mapped_column(ForeignKey("patologias.id", ondelete="CASCADE"), primary_key=True)
    sintoma_id: Mapped[int] = mapped_column(ForeignKey("sintomas.id"), primary_key=True)
    es_cardinal: Mapped[bool] = mapped_column(Boolean, default=False)

    patologia: Mapped[Patologia] = relationship(back_populates="sintomas")
    sintoma: Mapped[Sintoma] = relationship()

    __table_args__ = (
        # Un solo sintoma cardinal por patologia
        Index("uq_un_cardinal_por_patologia", "patologia_id", unique=True,
              sqlite_where=text("es_cardinal"), postgresql_where=text("es_cardinal")),
    )


class PacienteSintoma(Base):
    __tablename__ = "pacientes_sintomas"

    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), primary_key=True)
    sintoma_id: Mapped[int] = mapped_column(ForeignKey("sintomas.id"), primary_key=True)


class Familiar(Base):
    __tablename__ = "familiares"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    parentesco: Mapped[str] = mapped_column(String(60))
    nombre: Mapped[str] = mapped_column(String(150))
    diagnostico_previo: Mapped[str | None] = mapped_column(String(255))

    paciente: Mapped[Paciente] = relationship(back_populates="familiares")
    sintomas: Mapped[list[Sintoma]] = relationship(secondary="familiares_sintomas")


class FamiliarSintoma(Base):
    __tablename__ = "familiares_sintomas"

    familiar_id: Mapped[int] = mapped_column(ForeignKey("familiares.id", ondelete="CASCADE"), primary_key=True)
    sintoma_id: Mapped[int] = mapped_column(ForeignKey("sintomas.id"), primary_key=True)


class Gen(Base):
    __tablename__ = "genes"

    id: Mapped[int] = mapped_column(primary_key=True)
    simbolo: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    nombre: Mapped[str | None] = mapped_column(String(255))
    es_hallazgo_secundario: Mapped[bool] = mapped_column(Boolean, default=False)

    patologias: Mapped[list[Patologia]] = relationship(secondary="patologias_genes", back_populates="genes")
    variantes: Mapped[list[Variante]] = relationship(back_populates="gen", cascade="all, delete-orphan")


class PatologiaGen(Base):
    __tablename__ = "patologias_genes"

    patologia_id: Mapped[int] = mapped_column(ForeignKey("patologias.id", ondelete="CASCADE"), primary_key=True)
    gen_id: Mapped[int] = mapped_column(ForeignKey("genes.id", ondelete="CASCADE"), primary_key=True)


class Variante(Base):
    __tablename__ = "variantes"
    __table_args__ = (UniqueConstraint("gen_id", "notacion"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    gen_id: Mapped[int] = mapped_column(ForeignKey("genes.id", ondelete="CASCADE"), index=True)
    notacion: Mapped[str] = mapped_column(String(120))     # ej. c.1935C>A
    clinvar_id: Mapped[str | None] = mapped_column(String(30), index=True)   # origen: ClinVar via Apigen
    clasificacion: Mapped[ClasificacionVariante] = mapped_column(Enum(ClasificacionVariante))

    gen: Mapped[Gen] = relationship(back_populates="variantes")
