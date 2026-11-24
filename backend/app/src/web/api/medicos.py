"""Blueprint de medicos y especialidades (/api/v1)."""
from flask import Blueprint, jsonify, request
from src.core.services import medico_service
from src.web.validators.medicos_validator import RegistroMedicoSchema

medicos_bp = Blueprint("medicos", __name__, url_prefix="/api/v1")


@medicos_bp.get("/especialidades")
def listar_especialidades():
    especialidades = medico_service.listar_especialidades()
    return jsonify({"ok": True, "data": especialidades}), 200


@medicos_bp.post("/medicos/registro")
def registrar_medico():
    # silent=True devuelve None si no hay JSON valido en vez de lanzar error 400 crudo
    payload = request.get_json(silent=True) or {}
    # load() valida tipos con Marshmallow; si falla, errors.py devuelve 400 automatico
    datos = RegistroMedicoSchema().load(payload)
    resultado = medico_service.registrar_medico(**datos)
    return jsonify({"ok": True, "data": resultado}), 201