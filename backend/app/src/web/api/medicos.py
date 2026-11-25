"""Blueprint de medicos y especialidades (/api/v1)."""
from flask import Blueprint, g, jsonify, make_response, request
from src.core.models import Rol
from src.core.services import medico_service
from src.core.services.excepciones import ErrorDominio
from src.web.decorators.auth import requiere_sesion
from src.web.validators.medicos_validator import RegistroMedicoSchema

medicos_bp = Blueprint("medicos", __name__, url_prefix="/api/v1")


def _parsear_especialidad_id_opcional() -> int | None:
    raw = request.args.get("especialidad_id")
    if raw is None or raw.strip() == "":
        return None
    try:
        valor = int(raw)
    except ValueError as exc:
        raise ErrorDominio(
            "El parametro especialidad_id debe ser un entero positivo.",
            codigo="DATOS_INVALIDOS",
            http_status=400,
        ) from exc
    if valor <= 0:
        raise ErrorDominio(
            "El parametro especialidad_id debe ser un entero positivo.",
            codigo="DATOS_INVALIDOS",
            http_status=400,
        )
    return valor


@medicos_bp.get("/especialidades")
def listar_especialidades():
    especialidades = medico_service.listar_especialidades()
    return jsonify({"ok": True, "data": especialidades}), 200


@medicos_bp.get("/medicos")
@requiere_sesion(roles=Rol.PACIENTE)
def listar_directorio_medicos():
    especialidad_id = _parsear_especialidad_id_opcional()
    resultado = medico_service.listar_directorio_medicos_paciente(
        usuario_actual_id=g.usuario_actual.id,
        q=request.args.get("q"),
        especialidad_id=especialidad_id,
    )
    resp = make_response(jsonify({"ok": True, "data": resultado}), 200)
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@medicos_bp.post("/medicos/registro")
def registrar_medico():
    # silent=True devuelve None si no hay JSON valido en vez de lanzar error 400 crudo
    payload = request.get_json(silent=True) or {}
    # load() valida tipos con Marshmallow; si falla, errors.py devuelve 400 automatico
    datos = RegistroMedicoSchema().load(payload)
    resultado = medico_service.registrar_medico(**datos)
    return jsonify({"ok": True, "data": resultado}), 201