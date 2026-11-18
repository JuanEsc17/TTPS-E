"""Modelo de auditoria inmutable para entidades criticas (ADR-003)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .enums import EntidadAuditable, TipoAccionAuditoria


class RegistroModificacion(Base):
    """Registro append-only de altas, ediciones y transiciones de estado."""
    __tablename__ = "registro_modificaciones"
    __table_args__ = (
        Index("idx_auditoria_entidad_fecha", "entidad_tipo", "entidad_id", "fecha"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entidad_tipo: Mapped[EntidadAuditable] = mapped_column(Enum(EntidadAuditable), index=True)
    entidad_id: Mapped[int] = mapped_column(index=True)
    accion: Mapped[TipoAccionAuditoria] = mapped_column(Enum(TipoAccionAuditoria))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    origen: Mapped[str] = mapped_column(String(60), default="usuario")
    cambios: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    motivo: Mapped[str | None] = mapped_column(String(500))
    ip_origen: Mapped[str | None] = mapped_column(String(64))
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
