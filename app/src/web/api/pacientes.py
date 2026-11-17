"""Blueprint de pacientes (/api/v1/pacientes)."""
from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services import paciente_service
from src.web.decorators.auth import requiere_sesion
from src.web.validators.pacientes_validator import AltaPacienteSchema

pacientes_bp = Blueprint("pacientes", __name__, url_prefix="/api/v1/pacientes")


@pacientes_bp.get("")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def listar_pacientes():
    pacientes = paciente_service.listar_pacientes_medico(g.usuario_actual.id)
    return jsonify({"ok": True, "data": pacientes}), 200


@pacientes_bp.post("")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def dar_de_alta_paciente():
    payload = request.get_json(silent=True) or {}
    datos = AltaPacienteSchema().load(payload)
    resultado = paciente_service.dar_de_alta_paciente(
        usuario_actual_id=g.usuario_actual.id,
        datos=datos,
    )
    return jsonify({"ok": True, "data": resultado}), 201