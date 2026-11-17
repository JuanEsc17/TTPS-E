"""Blueprint para consultas al chatbot sobre patologias (/api/v1/chatbot)."""
from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services import chatbot_service
from src.web.decorators.auth import requiere_sesion
from src.web.validators.chatbot_validator import ConsultaChatbotSchema

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/api/v1/chatbot")


@chatbot_bp.post("/consultas")
@requiere_sesion(
    roles=(Rol.PACIENTE,),
    codigo_rol_denegado="ACCESO_CHATBOT_NO_AUTORIZADO",
    codigo_password_inicial="ACCESO_CHATBOT_NO_AUTORIZADO",
)
def consultar_chatbot():
    payload = request.get_json(silent=True) or {}
    datos = ConsultaChatbotSchema().load(payload)
    resultado = chatbot_service.consultar_chatbot(
        usuario_id=g.usuario_actual.id,
        pregunta=datos["pregunta"] or "",
        patologia_id=datos["patologia_id"],
        conversacion_id=datos["conversacion_id"],
    )
    return jsonify({"ok": True, "data": resultado}), 200
