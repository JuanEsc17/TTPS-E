"""Blueprint de endpoints de presupuestos (Escenario 3)."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services.economia_service import EconomiaService
from src.web.decorators.auth import requiere_sesion
from src.web.validators.presupuestos_validator import (
    validar_emitir_presupuesto,
    validar_filtros_pendientes_presupuesto,
)

presupuestos_bp = Blueprint("presupuestos", __name__, url_prefix="/api/v1")


@presupuestos_bp.get("/presupuestos/pendientes")
@requiere_sesion(roles=[Rol.ADMINISTRATIVO], codigo_rol_denegado="FORBIDDEN_ROLE")
def listar_pendientes_presupuesto() -> tuple[Any, int]:
    """Bandeja del Administrativo: estudios en Creado sin presupuesto (STEP 0)."""
    filtros = validar_filtros_pendientes_presupuesto(request.args)
    resultado = EconomiaService.listar_pendientes_presupuesto(dni=filtros["dni"])
    return jsonify({"ok": True, "data": resultado}), 200

@presupuestos_bp.post("/estudios/<int:estudio_id>/presupuesto")
@requiere_sesion(roles=[Rol.ADMINISTRATIVO], codigo_rol_denegado="FORBIDDEN_ROLE")
def emitir_presupuesto(estudio_id: int) -> tuple[Any, int]:
    """El Administrativo emite el presupuesto de un estudio en estado Creado."""
    datos = validar_emitir_presupuesto(request.get_json(silent=True))
    resultado = EconomiaService.emitir_presupuesto(
        estudio_id=estudio_id,
        usuario_actual_id=g.usuario_actual.id,
        obra_social_id=datos["obra_social_id"],
    )
    return jsonify({"ok": True, "data": resultado}), 201