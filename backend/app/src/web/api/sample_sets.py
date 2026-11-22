"""Blueprint de endpoints para consulta de SampleSets (Escenario 12)."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request
from src.core.models import Rol
from src.core.services.sample_set_service import SampleSetService
from src.web.decorators.auth import requiere_sesion
from src.web.validators.sample_sets_validator import validar_filtro_estado_sample_set

sample_sets_bp = Blueprint("sample_sets", __name__, url_prefix="/api/sample-sets")


@sample_sets_bp.get("")
@requiere_sesion(roles=[Rol.ADMINISTRATIVO])
def listar_sample_sets() -> tuple[Any, int]:
    """Lista los SampleSets del laboratorio central filtrables por estado."""
    estado = validar_filtro_estado_sample_set(request.args)
    lotes = SampleSetService.listar_sample_sets(estado=estado)
    return jsonify({"ok": True, "sample_sets": lotes}), 200


@sample_sets_bp.get("/<int:sample_set_id>")
@requiere_sesion(roles=[Rol.ADMINISTRATIVO])
def obtener_sample_set(sample_set_id: int) -> tuple[Any, int]:
    """Devuelve el detalle de un SampleSet con sus muestras y estudios."""
    lote = SampleSetService.obtener_sample_set(sample_set_id)
    return jsonify({"ok": True, "sample_set": lote}), 200

