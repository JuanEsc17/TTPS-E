"""Utilidades de hash y emision de JWT."""
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

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