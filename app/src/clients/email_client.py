"""Cliente HTTP para la API de Notificaciones por Email (TTPS-E)."""
from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

from .exceptions import (
    ClienteAutenticacionError,
    ClienteConexionError,
    ClienteServicioError,
    ClienteValidacionError,
)

BASE_URL_DEFAULT = "https://jpnbycihugrzeeolobev.supabase.co/functions/v1"


class EmailClient:
    """Cliente para interactuar con la API externa de Notificaciones por Email."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("EMAIL_API_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("EMAIL_API_KEY", "")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _procesar_error(self, response: httpx.Response) -> None:
        try:
            datos_error = response.json()
            mensaje = datos_error.get("error") or response.text
        except (ValueError, KeyError):
            datos_error = response.text
            mensaje = response.text

        codigo = response.status_code
        if codigo in (401, 403):
            raise ClienteAutenticacionError(
                f"Error de autenticacion en API de Email ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        if codigo in (400, 409, 413, 415, 422):
            raise ClienteValidacionError(
                f"Error en peticion a API de Email ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        if codigo >= 500:
            raise ClienteServicioError(
                f"Error interno en API de Email ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        response.raise_for_status()

    def verificar_conexion(self) -> dict[str, Any]:
        """Comprueba que la API Key sea valida y consulta el nombre del sistema asignado."""
        url = f"{self.base_url}/avisos"
        try:
            resp = self._client.get(url, headers=self._headers())
            if not resp.is_success:
                self._procesar_error(resp)
            return resp.json()
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"No se pudo conectar con la API de Notificaciones: {exc}"
            ) from exc

    def enviar_aviso(
        self,
        asunto: str,
        mensaje: str,
        destinatarios: list[str | dict[str, str]],
        referencia: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Pide el envio asincrono de un correo a uno o varios destinatarios.

        Parametros:
            asunto: Asunto del mail (max 200 chars).
            mensaje: Cuerpo del mensaje en texto plano (max 10.000 chars).
            destinatarios: Lista de emails o dicts {"canal": "email", "destino": "..."}.
            referencia: Identificador opcional para trazabilidad (ej. 'RESULTADO-123').
            idempotency_key: Clave unica de idempotencia. Si se omite, se genera una aleatoria.

        Retorna:
            dict con {"id": "<uuid>", "estado": "pendiente", "creado": True/False}
        """
        clave_idempotencia = idempotency_key or f"aviso-{uuid.uuid4().hex}"

        destinatarios_formateados = []
        for dest in destinatarios:
            if isinstance(dest, str):
                destinatarios_formateados.append({"canal": "email", "destino": dest})
            else:
                destinatarios_formateados.append(dest)

        payload: dict[str, Any] = {
            "asunto": asunto,
            "mensaje": mensaje,
            "destinatarios": destinatarios_formateados,
        }
        if referencia:
            payload["referencia"] = referencia

        url = f"{self.base_url}/avisos"
        headers = self._headers(idempotency_key=clave_idempotencia)

        try:
            resp = self._client.post(url, headers=headers, json=payload)
            # 202 Accepted (creado) o 200 OK (idempotente)
            if resp.status_code in (200, 202):
                return resp.json()
            self._procesar_error(resp)
            return resp.json()
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"Fallo de conexion al enviar aviso por email: {exc}"
            ) from exc

    def consultar_estado(self, aviso_id: str) -> dict[str, Any]:
        """Consulta el estado de entrega y detalle por destinatario de un aviso por su ID."""
        url = f"{self.base_url}/avisos/{aviso_id}"
        try:
            resp = self._client.get(url, headers=self._headers())
            if not resp.is_success:
                self._procesar_error(resp)
            return resp.json()
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"Fallo de conexion al consultar estado del aviso {aviso_id}: {exc}"
            ) from exc

    def listar_pendientes(self, limite: int = 25) -> dict[str, Any]:
        """Lista los avisos que continuan pendientes de envio."""
        url = f"{self.base_url}/avisos/pendientes"
        params = {"limite": limite}
        try:
            resp = self._client.get(url, headers=self._headers(), params=params)
            if not resp.is_success:
                self._procesar_error(resp)
            return resp.json()
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"Fallo de conexion al listar avisos pendientes: {exc}"
            ) from exc
