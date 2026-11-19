"""Blueprint de autenticacion (/api/v1/auth)."""
from flask import Blueprint, g, jsonify, request
from src.core.services import auth_service
from src.core.services.seguridad import (
    SCOPE_CAMBIO_PASSWORD_INICIAL,
    SCOPE_VERIFICAR_DISPOSITIVO,
)
from src.web.decorators.auth import extraer_payload_opcional, requiere_sesion
from src.web.validators.auth_validator import (
    CambiarPasswordInicialSchema,
    CambiarPasswordSchema,
    LoginSchema,
    ReenviarCodigoSchema,
    VerificarDispositivoSchema,
)

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

@auth_bp.post("/cambiar-password-inicial")
@requiere_sesion(scopes_permitidos=(SCOPE_CAMBIO_PASSWORD_INICIAL,))
def cambiar_password_inicial():
    payload = request.get_json(silent=True) or {}
    datos = CambiarPasswordInicialSchema().load(payload)
    resultado = auth_service.cambiar_password_inicial(
        usuario_id=g.usuario_actual.id,
        password_inicial=datos["password_inicial"],
        nueva_password=datos["nueva_password"],
        confirmacion_password=datos["confirmacion_password"],
        dispositivo_identificador=datos["dispositivo_identificador"],
    )
    return jsonify({"ok": True, **resultado}), 200

@auth_bp.get("/me")
@requiere_sesion()
def me():
    u = g.usuario_actual
    return (
        jsonify(
            {
                "ok": True,
                "usuario": {
                    "id": u.id,
                    "nombre": u.nombre,
                    "apellido": u.apellido,
                    "email": u.email,
                    "rol": u.rol.value,
                    "debe_cambiar_password": u.debe_cambiar_password
                }
            }
        ),
        200
    )

@auth_bp.post("/logout")
def logout():
    payload = extraer_payload_opcional()
    resultado = auth_service.cerrar_sesion(payload)
    return jsonify({"ok": True, **resultado}), 200


@auth_bp.post("/verificar-dispositivo")
@requiere_sesion(scopes_permitidos=(SCOPE_VERIFICAR_DISPOSITIVO,))
def verificar_dispositivo():
    payload = request.get_json(silent=True) or {}
    datos = VerificarDispositivoSchema().load(payload)
    resultado = auth_service.verificar_dispositivo(
        usuario_id=g.usuario_actual.id,
        codigo=datos["codigo"],
        dispositivo_identificador=datos["dispositivo_identificador"],
        token_payload=g.token_payload,
    )
    return jsonify({"ok": True, **resultado}), 200


@auth_bp.post("/reenviar-codigo-dispositivo")
@requiere_sesion(scopes_permitidos=(SCOPE_VERIFICAR_DISPOSITIVO,))
def reenviar_codigo_dispositivo():
    payload = request.get_json(silent=True) or {}
    datos = ReenviarCodigoSchema().load(payload)
    resultado = auth_service.reenviar_codigo_dispositivo(
        usuario_id=g.usuario_actual.id,
        dispositivo_identificador=datos["dispositivo_identificador"],
        token_payload=g.token_payload,
    )
    return jsonify({"ok": True, **resultado}), 200


@auth_bp.post("/cambiar-password")
@requiere_sesion()
def cambiar_password():
    payload = request.get_json(silent=True) or {}
    datos = CambiarPasswordSchema().load(payload)
    resultado = auth_service.cambiar_password(
        usuario_id=g.usuario_actual.id,
        password_actual=datos["password_actual"],
        password_nueva=datos["password_nueva"],
        password_nueva_confirmacion=datos["password_nueva_confirmacion"],
        token_payload=g.token_payload,
    )
    return jsonify({"ok": True, **resultado}), 200