"""Repositorio append-only para registro_modificaciones (ADR-003)."""
from __future__ import annotations

from typing import Any

from src.core.database import db
from src.core.models import EntidadAuditable, RegistroModificacion, TipoAccionAuditoria


def registrar_modificacion(
    *,
    entidad_tipo: EntidadAuditable,
    entidad_id: int,
    accion: TipoAccionAuditoria,
    cambios: dict[str, Any],
    usuario_id: int | None = None,
    origen: str = "usuario",
    motivo: str | None = None,
    ip_origen: str | None = None,
) -> RegistroModificacion:
    """Inserta un asiento inmutable en registro_modificaciones dentro de la sesion actual."""
    registro = RegistroModificacion(
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        accion=accion,
        usuario_id=usuario_id,
        origen=origen,
        cambios=cambios,
        motivo=motivo,
        ip_origen=ip_origen,
    )
    db.session.add(registro)
    db.session.flush()
    return registro
