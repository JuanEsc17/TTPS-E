"""Blueprint de endpoints para la toma de muestras y remuestreo (Escenarios 9 y 10)."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services.muestra_service import MuestraService
from src.web.decorators.auth import requiere_sesion
from src.web.validators.muestras_validator import (
    validar_filtros_pendientes_toma,
    validar_filtros_remuestreables,
    validar_registrar_toma_muestra,
    validar_remuestreo_estudio,
)

muestras_bp = Blueprint("muestras", __name__, url_prefix="/api/v1")


@muestras_bp.get("/muestras/pendientes")
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


@muestras_bp.post("/muestras/turnos/<int:turno_id>/toma")
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


@muestras_bp.get("/muestras/remuestreables")
@requiere_sesion(roles=[Rol.ADMINISTRATIVO])
def listar_estudios_remuestreables() -> tuple[Any, int]:
    """Lista los estudios con muestra vigente elegibles para declarar remuestreo (Escenario 10)."""
    filtros = validar_filtros_remuestreables(request.args)
    resultado = MuestraService.listar_estudios_remuestreables(
        dni=filtros["dni"],
        estudio_id=filtros["estudio_id"],
    )
    return jsonify({"ok": True, "data": resultado}), 200


@muestras_bp.post("/estudios/<int:estudio_id>/remuestreo")
@requiere_sesion(roles=[Rol.ADMINISTRATIVO])
def solicitar_remuestreo_estudio(estudio_id: int) -> tuple[Any, int]:
    """Descarta una muestra por falla de calidad y retrocede el estudio a Remuestreo requerido."""
    payload = request.get_json(silent=True)
    datos = validar_remuestreo_estudio(payload)
    resultado = MuestraService.solicitar_remuestreo(
        estudio_id=estudio_id,
        usuario_actual_id=g.usuario_actual.id,
        motivo_descarte=datos["motivo_descarte"],
        observaciones_calidad=datos["observaciones_calidad"],
        motivo=datos["motivo"],
        ip_origen=request.remote_addr,
    )
    return jsonify({"ok": True, "data": resultado}), 200