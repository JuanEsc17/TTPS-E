"""Logica de autenticacion (Escenario 27: Iniciar sesion)."""
import logging
import secrets
from datetime import timedelta
from typing import Any

from flask import current_app
from src.clients import (
    ClienteConexionError,
    ClienteError,
    ClienteServicioError,
    EmailClient,
)
from src.core.database import db
from src.core.models import Rol, Usuario
from src.core.repos import usuario_repo
from src.core.services.excepciones import ErrorDominio
from src.core.services.seguridad import (
    DUMMY_PASSWORD_HASH,
    SCOPE_ACCESO_COMPLETO,
    SCOPE_CAMBIO_PASSWORD_INICIAL,
    SCOPE_VERIFICAR_DISPOSITIVO,
    emitir_token,
    hashear_password,
    sha256_hex,
    validar_politica_password,
    verificar_password,
)

logger = logging.getLogger(__name__)

RUTA_INICIO_POR_ROL: dict[Rol, str] = {
    Rol.PACIENTE: "/paciente/estudios",
    Rol.MEDICO: "/medico/estudios",
    Rol.GERENTE_MEDICO: "/gerencia/patologias",
    Rol.ADMINISTRATIVO: "/administracion/estudios",
    Rol.BIOINFORMATICO: "/bioinformatica/cola",
    Rol.TRANSPORTISTA: "/transporte/orden-del-dia",
    Rol.ADMIN_GENERAL: "/admin/dashboard",
}


def _serializar_usuario(usuario: Usuario) -> dict[str, Any]:
    return {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "email": usuario.email,
        "rol": usuario.rol.value,
        "debe_cambiar_password": usuario.debe_cambiar_password,
    }


def _enviar_codigo_mail(usuario: Usuario, codigo: str, email_client: EmailClient | None) -> None:
    cliente = email_client or current_app.extensions.get("email_client") or EmailClient()
    asunto = "Codigo de verificacion por ingreso desde un equipo nuevo"
    mensaje = (
        f"Hola {usuario.nombre} {usuario.apellido},\n\n"
        f"Detectamos un inicio de sesion desde una maquina nueva.\n"
        f"Tu codigo de verificacion es: {codigo}\n"
        "Vence en 10 minutos."
    )
    for intento in range(3):
        try:
            cliente.enviar_aviso(
                asunto=asunto,
                mensaje=mensaje,
                destinatarios=[usuario.email],
                referencia=f"2FA-{usuario.id}",
            )
            return
        except (ClienteConexionError, ClienteServicioError) as exc:
            if intento == 2:
                raise ErrorDominio(
                    "No pudimos enviar el codigo de verificacion por correo. Intente nuevamente.",
                    codigo="ERROR_ENVIO_CODIGO_MAIL",
                    http_status=503,
                    reintentable=True,
                ) from exc
        except ClienteError as exc:
            raise ErrorDominio(
                "Error de configuracion o formato al enviar el correo de verificacion.",
                codigo="ERROR_ENVIO_CODIGO_MAIL",
                http_status=503,
                reintentable=False,
            ) from exc


def iniciar_sesion(
    *,
    email: str,
    password: str,
    dispositivo_identificador: str,
    email_client: EmailClient | None = None,
) -> dict[str, Any]:
    email_norm = email.strip().lower()
    dispositivo_hash = sha256_hex(dispositivo_identificador)
    secret_key = str(current_app.config["SECRET_KEY"])

    usuario = usuario_repo.buscar_por_email(email_norm)
    hash_a_validar = usuario.password_hash if usuario else DUMMY_PASSWORD_HASH
    password_ok = verificar_password(hash_a_validar, password)
    if usuario is None or not password_ok:
        raise ErrorDominio(
            "Correo electronico o contrasena incorrectos.",
            codigo="CREDENCIALES_INVALIDAS",
            http_status=401,
        )

    logger.info("[auth_service] credenciales validadas usuario_id=%s rol=%s", usuario.id, usuario.rol.value)

    # Filtro 1: primer ingreso (deriva al Escenario 20 sin habilitar acceso completo)
    if usuario.debe_cambiar_password:
        token = emitir_token(
            secret_key,
            usuario_id=usuario.id,
            rol=usuario.rol.value,
            scope=SCOPE_CAMBIO_PASSWORD_INICIAL,
            ttl_segundos=15 * 60,
        )
        return {
            "estado_login": "REQUIERE_CAMBIO_PASSWORD_INICIAL",
            "requiere_cambio_password": True,
            "requiere_verificacion_dispositivo": False,
            "access_token": token,
            "usuario": _serializar_usuario(usuario),
        }

    # Filtro 2: verificar si el equipo ya es conocido (si no, deriva al Escenario 26)
    dispositivo = usuario_repo.buscar_dispositivo(usuario.id, dispositivo_hash)
    if dispositivo is None:
        codigo_plano = f"{secrets.randbelow(1_000_000):06d}"
        expira_en = usuario_repo.ahora_utc() + timedelta(minutes=10)
        usuario_repo.crear_codigo_verificacion(
            usuario_id=usuario.id,
            codigo_hash=sha256_hex(codigo_plano),
            dispositivo_hash=dispositivo_hash,
            expira_en=expira_en,
        )
        try:
            _enviar_codigo_mail(usuario, codigo_plano, email_client)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        challenge_token = emitir_token(
            secret_key,
            usuario_id=usuario.id,
            rol=usuario.rol.value,
            scope=SCOPE_VERIFICAR_DISPOSITIVO,
            ttl_segundos=10 * 60,
            dispositivo_hash=dispositivo_hash,
        )
        return {
            "estado_login": "REQUIERE_VERIFICACION_DISPOSITIVO",
            "requiere_cambio_password": False,
            "requiere_verificacion_dispositivo": True,
            "challenge_token": challenge_token,
            "usuario": _serializar_usuario(usuario),
        }

    # Camino feliz: maquina conocida -> actualiza ultimo acceso y entrega sesion completa
    usuario_repo.actualizar_ultimo_acceso(dispositivo)
    db.session.commit()
    token = emitir_token(
        secret_key,
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=8 * 3600,
        dispositivo_hash=dispositivo_hash,
    )
    return {
        "estado_login": "AUTENTICADO",
        "requiere_cambio_password": False,
        "requiere_verificacion_dispositivo": False,
        "access_token": token,
        "ruta_inicio": RUTA_INICIO_POR_ROL[usuario.rol],
        "usuario": _serializar_usuario(usuario),
    }

def cambiar_password_inicial(
    *,
    usuario_id: int,
    password_inicial: str,
    nueva_password: str,
    confirmacion_password: str,
    dispositivo_identificador: str,
) -> dict[str, Any]:
    if nueva_password != confirmacion_password:
        raise ErrorDominio(
            "La confirmacion no coincide con la nueva contrasena.",
            codigo="NUEVA_PASSWORD_INVALIDA",
            http_status=400,
        )
    
    validar_politica_password(nueva_password, codigo="NUEVA_PASSWORD_INVALIDA")
    if nueva_password == password_inicial:
        raise ErrorDominio(
            "La nueva contrasena no puede ser igual a la contrasena inicial.",
            codigo="PASSWORD_IGUAL_A_INICIAL",
            http_status=400
        )
    
    usuario = usuario_repo.buscar_por_id(usuario_id, for_update=True)
    if usuario is None:
        raise ErrorDominio(
            "Usuario inexistente.",
            codigo="TOKEN_INVALIDO_O_EXPIRADO",
            http_status=401,
        )
    if not usuario.debe_cambiar_password:
        raise ErrorDominio(
            "La contrasena inicial ya fue cambiada previamente.",
            codigo="PASSWORD_INICIAL_YA_CAMBIADA",
            http_status=409
        )
    if not verificar_password(usuario.password_hash, password_inicial):
        raise ErrorDominio(
            "La contrasena inicial es incorrecta.",
            codigo="PASSWORD_INICIAL_INCORRECTA",
            http_status=401
        )
    if verificar_password(usuario.password_hash, nueva_password):
        raise ErrorDominio(
            "La nueva contrasena no puede ser igual a la contrasena inicial.",
            codigo="PASSWORD_IGUAL_A_INICIAL",
            http_status=400
        )

    dispositivo_hash = sha256_hex(dispositivo_identificador)
    usuario.password_hash = hashear_password(nueva_password)
    usuario.debe_cambiar_password = False
    usuario_repo.registrar_dispositivo(usuario.id, dispositivo_hash)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    logger.info("[auth_service] password inicial cambiada usuario_id=%s", usuario.id)
    token = emitir_token(
        str(current_app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=8 * 3600,
        dispositivo_hash=dispositivo_hash,
    )
    return {
        "estado_login": "AUTENTICADO",
        "dispositivo_registrado": True,
        "access_token": token,
        "ruta_inicio": RUTA_INICIO_POR_ROL[usuario.rol],
        "usuario": _serializar_usuario(usuario),
    }