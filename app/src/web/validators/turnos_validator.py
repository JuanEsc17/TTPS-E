"""Funciones de validacion y serializacion para solicitudes y respuestas de turnos."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.core.models.turnos import CentroExtraccion


def serializar_centro(centro: CentroExtraccion) -> dict[str, Any]:
    """Serializa un CentroExtraccion a diccionario plano."""
    return {
        "id": centro.id,
        "nombre": centro.nombre,
        "direccion": centro.direccion,
        "provincia": centro.provincia,
        "latitud": centro.latitud,
        "longitud": centro.longitud,
    }


def serializar_centros(centros: list[CentroExtraccion]) -> list[dict[str, Any]]:
    """Serializa una lista de CentroExtraccion."""
    return [serializar_centro(c) for c in centros]


def validar_consulta_disponibilidad(
    args: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Valida el parametro query 'fecha' para consulta de turnos libres.

    Retorna:
        (datos, None) en caso de exito.
        (None, mensaje_error) si es invalido.
    """
    fecha_str = args.get("fecha") if hasattr(args, "get") else None
    if not fecha_str:
        return None, "El parametro de consulta 'fecha' es obligatorio."

    try:
        fecha = date.fromisoformat(fecha_str)
    except (ValueError, TypeError):
        return None, "El formato de fecha debe ser YYYY-MM-DD."

    return {"fecha": fecha}, None


def validar_solicitar_turno(
    payload: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Valida el payload JSON para la reserva de un turno de extraccion.

    Retorna:
        (datos, None) en caso de exito.
        (None, mensaje_error) si es invalido.
    """
    if not isinstance(payload, dict) or not payload:
        return None, "El cuerpo de la solicitud debe ser un JSON valido con centro_id e inicio."

    centro_id = payload.get("centro_id")
    if centro_id is None:
        return None, "El campo 'centro_id' es obligatorio."
    # isinstance(True, int) es True en Python, se descarta bool explicitamente
    if isinstance(centro_id, bool) or not isinstance(centro_id, int) or centro_id <= 0:
        return None, "El centro_id debe ser un entero positivo."

    inicio_str = payload.get("inicio")
    if not inicio_str:
        return None, "El campo 'inicio' es obligatorio."
    if not isinstance(inicio_str, str):
        return None, "El campo 'inicio' debe ser una cadena con formato ISO-8601."

    try:
        inicio = datetime.fromisoformat(inicio_str)
    except (ValueError, TypeError):
        return None, "El campo 'inicio' debe tener formato ISO-8601 valido (ej: 2026-11-02T09:15:00)."

    if inicio.tzinfo is not None:
        inicio = inicio.replace(tzinfo=None)

    usuario_id: int | None = None
    if "usuario_id" in payload:
        uid = payload.get("usuario_id")
        if isinstance(uid, bool) or not isinstance(uid, int) or uid <= 0:
            return None, "El campo 'usuario_id' debe ser un entero positivo."
        usuario_id = uid

    return {"centro_id": centro_id, "inicio": inicio, "usuario_id": usuario_id}, None
