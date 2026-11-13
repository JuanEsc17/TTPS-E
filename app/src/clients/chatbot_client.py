"""Cliente HTTP para el Chatbot de GenLab (Modulo adicional 8 / M11)."""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

from ._base import ejecutar_peticion, manejar_error_http
from .exceptions import ClienteConexionError, ClienteValidacionError

BASE_URL_DEFAULT = "https://vglzngsrbyagquqqmakf.supabase.co/functions/v1/chat"
APIKEY_PUBLISHABLE_DEFAULT = "sb_publishable_oGrnSdrauwlw_NWXzCaXlA_hh1d3RaL"


class ChatbotClient:
    """Cliente para interactuar con la API externa del Chatbot de GenLab."""

    def __init__(
        self,
        base_url: str | None = None,
        apikey: str | None = None,
        token: str | None = None,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("CHATBOT_URL")
            or os.environ.get("CHATBOT_API_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.apikey = (
            apikey
            or os.environ.get("CHATBOT_APIKEY")
            or APIKEY_PUBLISHABLE_DEFAULT
        )
        self.token = token or os.environ.get("CHATBOT_TOKEN", "")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.apikey,
            "x-chatbot-token": self.token,
            "Content-Type": "application/json",
        }

    def verificar_estado(self) -> dict[str, Any]:
        """Verifica que el servicio del chatbot este activo (sin credenciales)."""
        resp = ejecutar_peticion(
            self._client,
            "API Chatbot",
            "GET",
            self.base_url,
        )
        return resp.json()

    def enviar_mensaje(
        self,
        mensaje: str,
        conversacion_id: str | None = None,
        *,
        reintentar_en_429: bool = True,
    ) -> dict[str, Any]:
        """Envia una consulta al chatbot y retorna respuesta, conversacion_id y tipo."""
        mensaje_limpio = mensaje.strip()
        if not mensaje_limpio or len(mensaje_limpio) > 1000:
            raise ClienteValidacionError(
                "El mensaje al chatbot debe tener entre 1 y 1000 caracteres no vacios."
            )
        if conversacion_id is not None and len(conversacion_id) > 200:
            raise ClienteValidacionError(
                "El conversacion_id no puede superar los 200 caracteres."
            )

        payload = {"mensaje": mensaje_limpio, "conversacion_id": conversacion_id}
        try:
            resp = self._client.post(
                self.base_url,
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code == 429 and reintentar_en_429:
                espera = float(resp.headers.get("Retry-After") or 5)
                time.sleep(min(max(espera, 0.0), 10.0))
                resp = self._client.post(
                    self.base_url,
                    headers=self._headers(),
                    json=payload,
                )
            if not resp.is_success:
                manejar_error_http(resp, "API Chatbot")
            return resp.json()
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"Fallo de conexion con API Chatbot: {exc}"
            ) from exc

