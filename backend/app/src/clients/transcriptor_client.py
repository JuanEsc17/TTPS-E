"""Cliente HTTP para el servicio externo de transcripcion de audio (Escenario 35)."""
from __future__ import annotations

import os

import httpx

from src.clients.exceptions import (
    ClienteConexionError,
    ClienteServicioError,
    ClienteValidacionError,
)


class TranscriptorClient:
    """Envia grabaciones de audio al transcriptor ASR externo."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("TRANSCRIPTOR_API_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("TRANSCRIPTOR_API_KEY", "")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def transcribir(
        self,
        *,
        audio_bytes: bytes,
        content_type: str,
        filename: str = "historia_clinica.webm",
        language: str = "es-AR",
    ) -> str:
        if not self.base_url:
            raise ClienteConexionError(
                "No hay un servicio externo de transcripcion configurado (TRANSCRIPTOR_API_BASE_URL)."
            )

        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        url = f"{self.base_url}/external/asr/transcribe"

        try:
            resp = self._client.post(
                url,
                headers=headers,
                files={"audio": (filename, audio_bytes, content_type)},
                data={"language": language},
            )
            if resp.status_code in (400, 415, 422):
                raise ClienteValidacionError(
                    "El transcriptor no pudo procesar el audio.",
                    codigo_http=resp.status_code,
                    respuesta=resp.text,
                )
            if not resp.is_success:
                raise ClienteServicioError(
                    f"Error del servicio transcriptor ({resp.status_code}).",
                    codigo_http=resp.status_code,
                    respuesta=resp.text,
                )
            datos = resp.json()
            return str(datos.get("texto") or datos.get("text") or "").strip()
        except httpx.RequestError as exc:
            raise ClienteConexionError(f"Error de conexion con el transcriptor: {exc}") from exc