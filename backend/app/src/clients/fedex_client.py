"""Cliente HTTP para la API de FedEx - Retiros programados y seguimiento (TTPS-E)."""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

import httpx

from ._base import ejecutar_peticion
from .exceptions import ClienteValidacionError

BASE_URL_DEFAULT = "https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex"
USUARIO_DEFAULT = "grupo01"
_PATRON_FECHA_LOCAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class FedexClient:
    """Cliente para programar y seguir retiros de muestras en FedEx."""

    def __init__(
        self,
        base_url: str | None = None,
        usuario: str | None = None,
        password: str | None = None,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("FEDEX_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.usuario = usuario or os.environ.get("FEDEX_USER") or USUARIO_DEFAULT
        self.password = (
            password
            or os.environ.get("FEDEX_PASS")
            or os.environ.get("FEDEX_API_KEY")
            or ""
        )
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _auth(self) -> tuple[str, str]:
        return (self.usuario, self.password)

    def programar_retiro(
        self,
        lugar: str,
        fecha_programada: str | datetime,
    ) -> dict[str, Any]:
        """Programa un retiro en horario argentino (YYYY-MM-DDTHH:mm:ss sin sufijo)."""
        lugar_limpio = lugar.strip()
        if not lugar_limpio or len(lugar_limpio) > 500:
            raise ClienteValidacionError(
                "El lugar de retiro debe tener entre 1 y 500 caracteres."
            )

        if isinstance(fecha_programada, datetime):
            fecha_str = fecha_programada.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            fecha_str = fecha_programada.strip()
            if not _PATRON_FECHA_LOCAL.match(fecha_str):
                raise ClienteValidacionError(
                    "La fecha_programada debe respetar YYYY-MM-DDTHH:mm:ss sin zona horaria."
                )

        resp = ejecutar_peticion(
            self._client,
            "API FedEx",
            "POST",
            f"{self.base_url}/retiros",
            auth=self._auth(),
            json={"lugar": lugar_limpio, "fecha_programada": fecha_str},
        )
        return resp.json()

    def listar_retiros(self, pagina: int = 1, limite: int = 10) -> dict[str, Any]:
        """Lista los retiros programados por el grupo autenticado con paginacion."""
        if not (1 <= pagina <= 100000):
            raise ClienteValidacionError("La pagina debe estar entre 1 y 100000.")
        if not (1 <= limite <= 50):
            raise ClienteValidacionError("El limite debe estar entre 1 y 50.")

        resp = ejecutar_peticion(
            self._client,
            "API FedEx",
            "GET",
            f"{self.base_url}/retiros",
            auth=self._auth(),
            params={"pagina": pagina, "limite": limite},
        )
        return resp.json()

    def consultar_retiro(self, retiro_id: str) -> dict[str, Any]:
        """Consulta el estado publico de un retiro por su UUID (PROGRAMADO o RETIRADO)."""
        retiro_limpio = retiro_id.strip()
        if not retiro_limpio:
            raise ClienteValidacionError("El UUID del retiro es obligatorio.")

        resp = ejecutar_peticion(
            self._client,
            "API FedEx",
            "GET",
            f"{self.base_url}/retiros/{retiro_limpio}",
        )
        return resp.json()


FedExClient = FedexClient

