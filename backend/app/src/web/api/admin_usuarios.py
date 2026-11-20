"""Blueprint del panel del admin general (/api/v1/admin)."""
from flask import Blueprint, g, jsonify, request
from marshmallow import ValidationError
from src.core.services import usuario_service
from src.core.services.excepciones import ErrorDatosInvalidos
from src.web.decorators.auth import requiere_sesion
from src.web.validators.admin_usuarios_validator import RegistroGerenteMedicoSchema

admin_usuarios_bp = Blueprint("admin_usuarios", __name__, url_prefix="/api/v1/admin")


@admin_usuarios_bp.route("/gerentes-medicos", methods=["POST"])
@requiere_sesion()
def registrar_gerente_medico():
    payload = request.get_json(silent=True) or {}
    try:
        datos = RegistroGerenteMedicoSchema().load(payload)
    except ValidationError as exc:
        raise ErrorDatosInvalidos("Los datos enviados son invalidos o estan incompletos.") from exc    
    resultado = usuario_service.registrar_gerente_medico(
        admin=g.usuario_actual,
        **datos,)
    return jsonify({"ok": True, "data": resultado}), 201