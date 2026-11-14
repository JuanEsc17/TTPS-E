"""Decoradores de autenticacion y autorizacion de roles."""
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any

from flask import current_app, g, request
from src.core.models import Rol
from src.core.repos import usuario_repo
from src.core.services.excepciones import ErrorDominio
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    SCOPE_CAMBIO_PASSWORD_INICIAL,
    decodificar_token,
)


def requiere_sesion(
    roles: Rol | str | Iterable[Rol | str] | None = None, *,
    scopes_permitidos: tuple[str, ...] = (SCOPE_ACCESO_COMPLETO,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    roles_ok: set[str] | None = None
    if roles is not None:
        lista = [roles] if isinstance(roles, (Rol, str)) else list(roles)
        roles_ok = {r.value if isinstance(r, Rol) else str(r) for r in lista}
    
    def decorador(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            auth = request.headers.get("Authorization", "").strip()
            partes = auth.split(None, 1)
            if len(partes) != 2 or partes[0].lower() != "bearer" or not partes[1].strip():
                raise ErrorDominio(
                    "Debe iniciar sesion para acceder a este recurso.",
                    codigo="NO_AUTENTICADO",
                    http_status=401,
                )

            payload = decodificar_token(partes[1].strip(), str(current_app.config["SECRET_KEY"]))
            scope = str(payload.get("scope", ""))
            if scope not in scopes_permitidos:
                if scope == SCOPE_CAMBIO_PASSWORD_INICIAL:
                    raise ErrorDominio(
                        "Debe cambiar su contrasena inicial antes de operar.",
                        codigo="DEBE_CAMBIAR_PASSWORD_INICIAL",
                        http_status=403,
                    )
                raise ErrorDominio(
                    "El token no tiene permisos para esta operacion.",
                    codigo="SCOPE_NO_AUTORIZADO",
                    http_status=403,
                )

            try:
                usuario = usuario_repo.buscar_por_id(int(payload["sub"]))
            except (TypeError, ValueError) as exc:
                raise ErrorDominio(
                    "Token de sesion invalido.",
                    codigo="TOKEN_INVALIDO_O_EXPIRADO",
                    http_status=401,
                ) from exc

            if usuario is None:
                raise ErrorDominio("Usuario inexistente.", codigo="NO_AUTENTICADO", http_status=401)

            if SCOPE_ACCESO_COMPLETO in scopes_permitidos and usuario.debe_cambiar_password:
                raise ErrorDominio(
                    "Debe cambiar su contrasena inicial antes de operar.",
                    codigo="DEBE_CAMBIAR_PASSWORD_INICIAL",
                    http_status=403,
                )

            if roles_ok is not None and usuario.rol.value not in roles_ok:
                raise ErrorDominio(
                    "No tiene permisos suficientes para realizar esta accion.",
                    codigo="ROL_NO_AUTORIZADO",
                    http_status=403,
                )

            g.usuario_actual = usuario
            g.token_payload = payload
            return fn(*args, **kwargs)

        return wrapper

    return decorador