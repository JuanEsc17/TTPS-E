"""Utilidades de hash y emision de JWT."""
import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

from .excepciones import ErrorDominio

SCOPE_ACCESO_COMPLETO = "acceso_completo"
SCOPE_CAMBIO_PASSWORD_INICIAL = "cambio_password_inicial"
SCOPE_VERIFICAR_DISPOSITIVO = "verificar_dispositivo"

# Se verifica igual cuando el email no existe para no filtrar cuentas por tiempo de respuesta
DUMMY_PASSWORD_HASH = generate_password_hash("dummy-timing-guard")


def hashear_password(password: str) -> str:
    return generate_password_hash(password)


def verificar_password(password_hash: str, password_plano: str) -> bool:
    return check_password_hash(password_hash, password_plano)


def sha256_hex(texto: str) -> str:
    return hashlib.sha256(texto.strip().encode("utf-8")).hexdigest()


def emitir_token(
    secret_key: str,
    *,
    usuario_id: int,
    rol: str,
    scope: str,
    ttl_segundos: int,
    dispositivo_hash: str | None = None,
) -> str:
    ahora = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(usuario_id),
        "rol": rol,
        "scope": scope,
        "jti": uuid.uuid4().hex,
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + timedelta(seconds=ttl_segundos)).timestamp()),
    }
    if dispositivo_hash:
        payload["dispositivo_hash"] = dispositivo_hash
    return jwt.encode(payload, secret_key, algorithm="HS256")

_REGEX_LETRA = re.compile(r"[A-Za-z]")
_REGEX_DIGITO = re.compile(r"\d")

def validar_politica_password(password: str, codigo: str = "NUEVA_PASSWORD_INVALIDA") -> None:
    if len(password) < 8 or len(password) > 128:
        raise ErrorDominio(
            "La contrasena debe tener entre 8 y 128 caracteres.",
            codigo=codigo,
            http_status=400
        )
    
    if not _REGEX_LETRA.search(password) or not _REGEX_DIGITO.search(password):
        raise ErrorDominio(
            "La contrasena debe incluir al menos una letra y un numero.",
            codigo=codigo,
            http_status=400
        )

def decodificar_token(token: str, secret_key:str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ErrorDominio(
            "El token de sesion ha expirado.",
            codigo="TOKEN_INVALIDO_O_EXPIRADO",
            http_status=401,
        ) from exc
        
    except jwt.InvalidTokenError as exc:
        raise ErrorDominio(
            "El token de sesion es invalido.",
            codigo="TOKEN_INVALIDO_O_EXPIRADO",
            http_status=401,
        ) from exc
    
    if "sub" not in payload or "scope" not in payload:
        raise ErrorDominio(
            "Token de sesion incompleto.",
            codigo="TOKEN_INVALIDO_O_EXPIRADO",
            http_status=401
        )
    return payload