"""Blueprint de endpoints para la gestion de turnos y centros de extraccion."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request
from src.core.services.turno_service import TurnoService
from src.web.validators.turnos_validator import (
    serializar_centro,
    serializar_centros,
    validar_consulta_disponibilidad,
    validar_solicitar_turno,
)

turnos_bp = Blueprint("turnos", __name__, url_prefix="/api/v1")


@turnos_bp.get("/centros-extraccion")
def listar_centros() -> tuple[Any, int]:
    """Retorna el listado de centros de extraccion para visualizar en el mapa interactivo."""
    centros = TurnoService.listar_centros()
    return jsonify({"ok": True, "data": serializar_centros(centros)}), 200


@turnos_bp.get("/centros-extraccion/<int:centro_id>/turnos-disponibles")
def obtener_turnos_disponibles(centro_id: int) -> tuple[Any, int]:
    """Consulta los slots de 15 minutos libres en un centro para una fecha dada."""
    parametros, error = validar_consulta_disponibilidad(request.args)
    if error:
        return jsonify({"ok": False, "error": error}), 422

    resultado, error, status = TurnoService.obtener_disponibilidad(
        centro_id=centro_id,
        fecha=parametros["fecha"],
    )

    if error:
        return jsonify({"ok": False, "error": error}), status

    data = {
        "centro": serializar_centro(resultado["centro"]),
        "fecha": resultado["fecha"],
        "slots_libres": resultado["slots_libres"],
    }
    return jsonify({"ok": True, "data": data}), status


@turnos_bp.post("/estudios/<int:estudio_id>/turnos")
def reservar_turno(estudio_id: int) -> tuple[Any, int]:
    """Reserva un turno de extraccion de 15 minutos para el paciente titular del estudio.

    NOTA: El modulo de login y auth esta siendo desarrollado por otro compañero.
    Por ahora se extrae usuario_actual_id desde cabecera 'X-User-Id', body 'usuario_id'
    o por defecto se asume el titular del estudio para facilitar el testing e integracion.
    """
    payload = request.get_json(silent=True)
    datos, error = validar_solicitar_turno(payload)
    if error:
        return jsonify({"ok": False, "error": error}), 422

    usuario_actual_id: int | None = datos.get("usuario_id")
    usuario_id_header = request.headers.get("X-User-Id")
    if usuario_id_header:
        if not usuario_id_header.isdigit() or int(usuario_id_header) <= 0:
            return jsonify({"ok": False, "error": "La cabecera 'X-User-Id' debe ser un entero positivo."}), 422
        usuario_actual_id = int(usuario_id_header)

    resultado, error, status = TurnoService.solicitar_turno(
        estudio_id=estudio_id,
        centro_id=datos["centro_id"],
        inicio=datos["inicio"],
        usuario_actual_id=usuario_actual_id,
    )

    if error:
        return jsonify({"ok": False, "error": error}), status

    return jsonify({"ok": True, "data": resultado}), status
