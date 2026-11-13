"""Blueprint de autenticacion (/api/v1/auth)."""
from flask import Blueprint, jsonify, request
from src.core.services import auth_service
from src.web.validators.auth_validator import LoginSchema

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    datos = LoginSchema().load(payload)
    resultado = auth_service.iniciar_sesion(
        email=datos["email"],
        password=datos["password"],
        dispositivo_identificador=datos["dispositivo_identificador"],
    )
    return jsonify({"ok": True, **resultado}), 200