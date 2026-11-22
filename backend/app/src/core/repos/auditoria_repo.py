"""Repositorio append-only para registro_modificaciones (ADR-003)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
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


def listar_cambios_estado_estudios(
    estudio_ids: list[int],
) -> dict[int, list[RegistroModificacion]]:
    """Devuelve las transiciones de estado registradas agrupadas por estudio_id."""
    if not estudio_ids:
        return {}
    stmt = (
        select(RegistroModificacion)
        .where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
            RegistroModificacion.entidad_id.in_(estudio_ids),
            RegistroModificacion.accion == TipoAccionAuditoria.CAMBIO_ESTADO,
        )
        .order_by(RegistroModificacion.fecha.asc(), RegistroModificacion.id.asc())
    )
    por_estudio: dict[int, list[RegistroModificacion]] = {}
    for reg in db.session.scalars(stmt).all():
        por_estudio.setdefault(reg.entidad_id, []).append(reg)
    return por_estudio
