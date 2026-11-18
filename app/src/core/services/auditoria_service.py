"""Servicio transversal de auditoria inmutable (ADR-003 / Escenario 42)."""
from __future__ import annotations

import logging
from typing import Any

from flask import has_request_context, request
from src.core.models import EntidadAuditable, TipoAccionAuditoria
from src.core.repos import auditoria_repo

logger = logging.getLogger(__name__)


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
):
    """Registra de forma atomica una modificacion dentro de la transaccion activa."""
    if not cambios and accion != TipoAccionAuditoria.CREACION:
        return None

    ip_resuelta = ip_origen
    if ip_resuelta is None and has_request_context():
        ip_resuelta = request.remote_addr

    registro = auditoria_repo.registrar_modificacion(
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        accion=accion,
        cambios=cambios,
        usuario_id=usuario_id,
        origen=origen,
        motivo=motivo,
        ip_origen=ip_resuelta,
    )
    logger.info(
        "[auditoria_service] modificacion_registrada tipo=%s id=%s accion=%s",
        entidad_tipo.value,
        entidad_id,
        accion.value,
    )
    return registro
