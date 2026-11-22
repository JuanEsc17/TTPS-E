"""Blueprint de endpoints para la toma de muestras (Escenario 9)."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services.muestra_service import MuestraService
from src.web.decorators.auth import requiere_sesion
from src.web.validators.muestras_validator import (
    validar_filtros_pendientes_toma,
    validar_registrar_toma_muestra,
)

muestras_bp = Blueprint("muestras", __name__, url_prefix="/api/v1/muestras")


@muestras_bp.get("/pendientes")
@requiere_sesion(roles=[Rol.ADMINISTRATIVO])
def listar_pendientes_toma() -> tuple[Any, int]:
    """Lista los turnos activos pendientes de registro de toma de muestra."""
    filtros, error = validar_filtros_pendientes_toma(request.args)
    if error or filtros is None:
        return jsonify({"ok": False, "error": error}), 422

    resultado, error_srv, status = MuestraService.listar_turnos_pendientes_toma(
        dni=filtros["dni"],
        estudio_id=filtros["estudio_id"],
        centro_id=filtros["centro_id"],
        fecha=filtros["fecha"],
    )
    if error_srv:
        return jsonify({"ok": False, "error": error_srv}), status
    return jsonify({"ok": True, "data": resultado}), status


@muestras_bp.post("/turnos/<int:turno_id>/toma")
@requiere_sesion(roles=[Rol.ADMINISTRATIVO])
def registrar_toma_muestra(turno_id: int) -> tuple[Any, int]:
    """Registra la toma de muestra de un turno tras el llamado del centro de extraccion."""
    payload = request.get_json(silent=True)
    datos, error = validar_registrar_toma_muestra(payload)
    if error or datos is None:
        return jsonify({"ok": False, "error": error}), 422

    resultado, error_srv, status = MuestraService.registrar_toma_muestra(
        turno_id=turno_id,
        usuario_actual_id=g.usuario_actual.id,
        tomada_en=datos["tomada_en"],
    )
    if error_srv:
        return jsonify({"ok": False, "error": error_srv}), status
    return jsonify({"ok": True, "data": resultado}), status