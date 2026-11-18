"""Blueprint de pacientes (/api/v1/pacientes)."""
from flask import Blueprint, g, jsonify, request, send_file
from src.core.models import Rol
from src.core.services import paciente_service
from src.web.decorators.auth import requiere_sesion
from src.web.validators.pacientes_validator import (
    AltaPacienteSchema,
    GestionarFamiliaresSchema,
)

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

@pacientes_bp.get("/<int:paciente_id>/familiares")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def obtener_familiares(paciente_id: int):
    resultado = paciente_service.obtener_familiares_paciente(
        usuario_actual_id=g.usuario_actual.id,
        paciente_id=paciente_id,
    )
    return jsonify({"ok": True, "data": resultado}), 200


@pacientes_bp.put("/<int:paciente_id>/familiares")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def gestionar_familiares(paciente_id: int):
    payload = request.get_json(silent=True) or {}
    datos = GestionarFamiliaresSchema().load(payload)
    resultado = paciente_service.gestionar_informacion_familiar(
        usuario_actual_id=g.usuario_actual.id,
        paciente_id=paciente_id,
        familiares_input=datos["familiares"],
    )
    return jsonify({"ok": True, "data": resultado}), 200


@pacientes_bp.get("/<int:paciente_id>/familiograma")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def ver_familiograma(paciente_id: int):
    ruta = paciente_service.obtener_archivo_familiograma(
        usuario_actual_id=g.usuario_actual.id,
        paciente_id=paciente_id,
    )
    return send_file(ruta, mimetype="image/svg+xml")