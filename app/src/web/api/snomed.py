"""Blueprint para busqueda SNOMED y validacion clinica contra patologias (/api/v1)."""
from flask import Blueprint, jsonify, request
from src.core.models import Rol
from src.core.services import clinica_service
from src.web.decorators.auth import requiere_sesion

snomed_bp = Blueprint("snomed", __name__, url_prefix="/api/v1")


@snomed_bp.get("/snomed/sintomas")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def buscar_sintomas():
    q = request.args.get("q", "")
    limite = request.args.get("limite", default=20, type=int)
    resultado = clinica_service.buscar_sintomas_snomed(q, limite=limite)
    return jsonify({"ok": True, "data": resultado}), 200


@snomed_bp.get("/patologias")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def listar_patologias():
    patologias = clinica_service.listar_patologias()
    return jsonify({"ok": True, "data": patologias}), 200


@snomed_bp.post("/patologias/<int:patologia_id>/validar-sintomas")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def validar_sintomas_patologia(patologia_id: int):
    payload = request.get_json(silent=True) or {}
    sintomas_ids = payload.get("sintomas_snomed_ids") or []
    sintomas_detalle = payload.get("sintomas_seleccionados")
    patologia, sintomas = clinica_service.validar_sintomas_contra_patologia(
        patologia_id=patologia_id,
        sintomas_snomed_ids=sintomas_ids,
        sintomas_detalle=sintomas_detalle,
    )
    return (
        jsonify(
            {
                "ok": True,
                "data": {
                    "valido": True,
                    "patologia_id": patologia.id,
                    "cantidad_sintomas": len(sintomas),
                },
            }
        ),
        200,
    )