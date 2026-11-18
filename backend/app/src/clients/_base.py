"""Utilidades compartidas para los clientes HTTP de APIs externas."""
from __future__ import annotations

from typing import Any

import httpx

from .exceptions import (
    ClienteAutenticacionError,
    ClienteConexionError,
    ClienteServicioError,
    ClienteValidacionError,
)


def extraer_mensaje_error(datos: Any, fallback: str) -> str:
    """Extrae un mensaje legible desde los distintos formatos de error JSON."""
    if isinstance(datos, dict):
        err = datos.get("error")
        if isinstance(err, dict):
            return str(
                err.get("mensaje")
                or err.get("message")
                or err.get("detail")
                or fallback
            )
        if err:
            return str(err)
        for clave in ("detail", "message", "mensaje", "detalle"):
            if datos.get(clave):
                return str(datos[clave])
    return fallback


def manejar_error_http(
    response: httpx.Response,
    servicio: str,
    *,
    codigos_autenticacion: tuple[int, ...] = (401, 403),
    codigos_validacion: tuple[int, ...] = (400, 404, 405, 409, 413, 415, 422),
) -> None:
    """Traduce respuestas HTTP no exitosas a excepciones de dominio ClienteError."""
    try:
        datos_error: dict | str = response.json()
        mensaje = extraer_mensaje_error(datos_error, response.text)
    except (ValueError, KeyError, AttributeError):
        datos_error = response.text
        mensaje = response.text

    codigo = response.status_code
    if codigo in codigos_autenticacion:
        raise ClienteAutenticacionError(
            f"Error de autenticacion en {servicio} ({codigo}): {mensaje}",
            codigo_http=codigo,
            respuesta=datos_error,
        )
    if codigo in codigos_validacion:
        raise ClienteValidacionError(
            f"Error en peticion a {servicio} ({codigo}): {mensaje}",
            codigo_http=codigo,
            respuesta=datos_error,
        )
    if codigo == 429 or codigo >= 500:
        raise ClienteServicioError(
            f"Error de servicio en {servicio} ({codigo}): {mensaje}",
            codigo_http=codigo,
            respuesta=datos_error,
        )
    response.raise_for_status()


def ejecutar_peticion(
    client: httpx.Client,
    servicio: str,
    metodo: str,
    url: str,
    *,
    codigos_autenticacion: tuple[int, ...] = (401, 403),
    codigos_validacion: tuple[int, ...] = (400, 404, 405, 409, 413, 415, 422),
    **kwargs: Any,
) -> httpx.Response:
    """Ejecuta una peticion HTTP manejando errores de red y codigos de estado."""
    try:
        resp = client.request(metodo, url, **kwargs)
        if not resp.is_success:
            manejar_error_http(
                resp,
                servicio,
                codigos_autenticacion=codigos_autenticacion,
                codigos_validacion=codigos_validacion,
            )
        return resp
    except httpx.RequestError as exc:
        raise ClienteConexionError(
            f"Fallo de conexion con {servicio}: {exc}"
        ) from exc

