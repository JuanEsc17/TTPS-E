"""Blueprint de pacientes (/api/v1/pacientes)."""
from flask import Blueprint, g, jsonify, make_response, request, send_file
from src.core.models import Rol
from src.core.services import paciente_service
from src.web.decorators.auth import requiere_sesion
from src.web.validators.pacientes_validator import (
    AltaPacienteSchema,
    AutorizarMedicosSchema,
    GestionarFamiliaresSchema,
    RevocarAutorizacionSchema,
)

pacientes_bp = Blueprint("pacientes", __name__, url_prefix="/api/v1/pacientes")


def _respuesta_privada(data: dict, status: int = 200):
    resp = make_response(jsonify({"ok": True, "data": data}), status)
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


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
        ip_origen=request.remote_addr,
    )
    return jsonify({"ok": True, "data": resultado}), 201


@pacientes_bp.get("/mi-perfil/medicos-autorizados")
@requiere_sesion(roles=Rol.PACIENTE)
def listar_mis_medicos_autorizados():
    resultado = paciente_service.listar_medicos_autorizados_paciente(
        usuario_actual_id=g.usuario_actual.id,
    )
    return _respuesta_privada(resultado, 200)


@pacientes_bp.post("/mi-perfil/medicos-autorizados")
@requiere_sesion(roles=Rol.PACIENTE)
def autorizar_medicos_historia_clinica():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    datos = AutorizarMedicosSchema().load(payload)
    resultado, http_status = paciente_service.autorizar_medicos_historia_clinica(
        usuario_actual_id=g.usuario_actual.id,
        medicos_ids=datos["medicos_ids"],
        motivo=datos["motivo"],
        ip_origen=request.remote_addr,
    )
    return _respuesta_privada(resultado, http_status)


@pacientes_bp.delete("/mi-perfil/medicos-autorizados/<int:medico_id>")
@requiere_sesion(roles=Rol.PACIENTE)
def revocar_autorizacion_medico(medico_id: int):
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {"motivo": request.args.get("motivo")} if request.args.get("motivo") else {}
    datos = RevocarAutorizacionSchema().load(payload)
    resultado = paciente_service.revocar_autorizacion_medico(
        usuario_actual_id=g.usuario_actual.id,
        medico_id=medico_id,
        motivo=datos["motivo"],
        ip_origen=request.remote_addr,
    )
    return _respuesta_privada(resultado, 200)


@pacientes_bp.get("/<int:paciente_id>/historia-clinica")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def consultar_historia_clinica(paciente_id: int):
    resultado = paciente_service.obtener_historia_clinica_paciente(
        usuario_actual_id=g.usuario_actual.id,
        paciente_id=paciente_id,
    )
    return _respuesta_privada(resultado, 200)


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

@pacientes_bp.post("/historia-clinica/transcribir")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def transcribir_historia_clinica():
    archivo = request.files.get("audio")
    audio_bytes = archivo.read() if archivo else b""
    content_type = archivo.mimetype if archivo else ""
    filename = (archivo.filename or "historia_clinica.webm") if archivo else "historia_clinica.webm"

    paciente_id_raw = request.form.get("paciente_id")
    paciente_id = int(paciente_id_raw) if paciente_id_raw and paciente_id_raw.isdigit() else None

    resultado = paciente_service.transcribir_historia_clinica(
        usuario_actual_id=g.usuario_actual.id,
        audio_bytes=audio_bytes,
        content_type=content_type,
        filename=filename,
        paciente_id=paciente_id,
    )
    return jsonify({"ok": True, "data": resultado}), 200


@pacientes_bp.patch("/<int:paciente_id>/historia-clinica")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def actualizar_historia_clinica(paciente_id: int):
    payload = request.get_json(silent=True) or {}
    resultado = paciente_service.actualizar_historia_clinica_paciente(
        usuario_actual_id=g.usuario_actual.id,
        paciente_id=paciente_id,
        historia_clinica=str(payload.get("historia_clinica") or ""),
    )
    return jsonify({"ok": True, "data": resultado}), 200