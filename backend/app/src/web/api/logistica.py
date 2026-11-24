"""Blueprint de endpoints para Logistica Terrestre (Escenario 11)."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services.logistica_service import LogisticaService
from src.web.decorators.auth import requiere_sesion

logistica_bp = Blueprint("logistica", __name__, url_prefix="/api/logistica")


@logistica_bp.get("/ordenes-del-dia/hoy")
@requiere_sesion(roles=[Rol.TRANSPORTISTA])
def obtener_orden_del_dia_hoy() -> tuple[Any, int]:
    lat_raw = request.args.get("lat")
    lon_raw = request.args.get("lon")
    origen_lat: float | None = None
    origen_lon: float | None = None
    if lat_raw is not None and lon_raw is not None:
        try:
            origen_lat = float(lat_raw)
            origen_lon = float(lon_raw)
        except ValueError:
            return jsonify({"ok": False, "error": "Coordenadas de origen invalidas."}), 422

    recalcular_raw = request.args.get("recalcular", "").strip().lower()
    recalcular = recalcular_raw in ("1", "true", "si", "yes")

    resultado, error, status = LogisticaService.obtener_o_generar_orden_del_dia(
        usuario_actual_id=g.usuario_actual.id,
        origen_lat=origen_lat,
        origen_lon=origen_lon,
        recalcular=recalcular,
    )
    if error:
        return jsonify({"ok": False, "error": error}), status
    return jsonify({"ok": True, "data": resultado}), status


@logistica_bp.post("/ordenes-del-dia/<int:orden_id>/paradas/<int:parada_id>/recoger")
@requiere_sesion(roles=[Rol.TRANSPORTISTA])
def marcar_recogida(orden_id: int, parada_id: int) -> tuple[Any, int]:
    resultado, error, status = LogisticaService.marcar_recogida_centro(
        orden_id=orden_id,
        parada_id=parada_id,
        usuario_actual_id=g.usuario_actual.id,
    )
    if error:
        return jsonify({"ok": False, "error": error}), status
    return jsonify({"ok": True, "data": resultado}), status


@logistica_bp.post("/ordenes-del-dia/<int:orden_id>/llegada-laboratorio-central")
@requiere_sesion(roles=[Rol.TRANSPORTISTA])
def marcar_llegada_lab_central(orden_id: int) -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    resultado, error, status = LogisticaService.marcar_llegada_lab_central(
        orden_id=orden_id,
        usuario_actual_id=g.usuario_actual.id,
        mililitros_por_muestra=payload.get("mililitros_por_muestra"),
    )
    if error:
        return jsonify({"ok": False, "error": error}), status
    return jsonify({"ok": True, "data": resultado}), status