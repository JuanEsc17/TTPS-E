"""Datos crudos, analisis bioinformatico y resultado."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import ClasificacionVariante, TipoAnalisis

if TYPE_CHECKING:
    from .clinica import Gen, Variante
    from .estudios import Estudio


class DatosCrudos(Base):
    """Archivo con letras A, C, T y G recibido de Corea (simulado)."""
    __tablename__ = "datos_crudos"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudios.id"), unique=True)
    cargado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))   # administrativo
    archivo_path: Mapped[str] = mapped_column(String(500))
    cargado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    estudio: Mapped[Estudio] = relationship(back_populates="datos_crudos")


class Analisis(Base):
    """Un analisis del exoma. El reanalisis agrega una fila nueva sobre el mismo estudio (historial)."""
    __tablename__ = "analisis"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudios.id"), index=True)
    tipo: Mapped[TipoAnalisis] = mapped_column(Enum(TipoAnalisis), default=TipoAnalisis.INICIAL)
    bioinformatico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"))
    solicitado_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("medicos.id"))   # en reanalisis
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    estudio: Mapped[Estudio] = relationship(back_populates="analisis")
    genes: Mapped[list["AnalisisGen"]] = relationship(back_populates="analisis", cascade="all, delete-orphan")
    variantes: Mapped[list["AnalisisVariante"]] = relationship(back_populates="analisis", cascade="all, delete-orphan")
    resultado: Mapped[Optional["Resultado"]] = relationship(back_populates="analisis", uselist=False)


class AnalisisGen(Base):
    __tablename__ = "analisis_genes"

    analisis_id: Mapped[int] = mapped_column(ForeignKey("analisis.id", ondelete="CASCADE"), primary_key=True)
    gen_id: Mapped[int] = mapped_column(ForeignKey("genes.id"), primary_key=True)

    analisis: Mapped[Analisis] = relationship(back_populates="genes")
    gen: Mapped[Gen] = relationship()


class AnalisisVariante(Base):
    __tablename__ = "analisis_variantes"

    analisis_id: Mapped[int] = mapped_column(ForeignKey("analisis.id", ondelete="CASCADE"), primary_key=True)
    variante_id: Mapped[int] = mapped_column(ForeignKey("variantes.id"), primary_key=True)

    analisis: Mapped[Analisis] = relationship(back_populates="variantes")
    variante: Mapped[Variante] = relationship()


class Resultado(Base):
    """PDF con positividad/negatividad y variantes. Positivo si hay alguna variante patogenica."""
    __tablename__ = "resultados"

    id: Mapped[int] = mapped_column(primary_key=True)
    analisis_id: Mapped[int] = mapped_column(ForeignKey("analisis.id"), unique=True)
    positivo: Mapped[bool] = mapped_column(Boolean)
    pdf_path: Mapped[str] = mapped_column(String(500))
    generado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    analisis: Mapped[Analisis] = relationship(back_populates="resultado")


def calcular_positivo(variantes: list[Variante]) -> bool:
    return any(v.clasificacion == ClasificacionVariante.PATOGENICA for v in variantes)
