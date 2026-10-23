"""Parametros editables del sistema."""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Configuracion(Base):
    """Parametros editables del sistema (clave/valor).
    Ej.: clave 'cdss_estrategia' con valor = nombre de un EstrategiaCDSS."""
    __tablename__ = "configuracion"

    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(String(255))
