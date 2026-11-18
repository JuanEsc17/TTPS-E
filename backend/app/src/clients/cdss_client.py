"""Cliente HTTP para el modulo CDSS - Soporte a la Decision Clinica (TTPS-E)."""
from __future__ import annotations

import os
from typing import Any

import httpx

from ._base import ejecutar_peticion
from .exceptions import ClienteValidacionError

BASE_URL_DEFAULT = "https://genexoma.onrender.com"


class CdssClient:
    """Cliente para interactuar con la API externa de CDSS (genExoma)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 45.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("CDSS_API_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("CDSS_API_KEY", "")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def verificar_salud(self) -> dict[str, Any]:
        """Verifica que el servicio y su base de datos esten operativos (sin API key)."""
        resp = ejecutar_peticion(
            self._client,
            "API CDSS",
            "GET",
            f"{self.base_url}/health",
        )
        return resp.json()

    def listar_patologias(self) -> list[dict[str, Any]]:
        """Obtiene el catalogo de patologias lisosomales con sus sintomas y cardinales."""
        resp = ejecutar_peticion(
            self._client,
            "API CDSS",
            "GET",
            f"{self.base_url}/api/v1/patologias",
            headers=self._headers(),
        )
        return resp.json()

    def listar_estrategias(self) -> list[Any]:
        """Devuelve las estrategias de evaluacion clinica disponibles."""
        resp = ejecutar_peticion(
            self._client,
            "API CDSS",
            "GET",
            f"{self.base_url}/api/v1/estrategias",
            headers=self._headers(),
        )
        return resp.json()

    def sugerir_diagnostico(self, sintomas: list[str]) -> dict[str, Any]:
        """Solicita una sugerencia diagnostica a partir de codigos SNOMED de sintomas."""
        if not sintomas:
            raise ClienteValidacionError(
                "Debe enviar al menos un codigo SNOMED en 'sintomas'."
            )
        resp = ejecutar_peticion(
            self._client,
            "API CDSS",
            "POST",
            f"{self.base_url}/api/v1/diagnostico",
            headers=self._headers(),
            json={"sintomas": [str(s) for s in sintomas]},
        )
        return resp.json()

    def obtener_configuracion(self) -> dict[str, Any]:
        """Consulta el grupo y la estrategia activa configurada en el CDSS."""
        resp = ejecutar_peticion(
            self._client,
            "API CDSS",
            "GET",
            f"{self.base_url}/api/v1/configuracion",
            headers=self._headers(),
        )
        return resp.json()

    def actualizar_estrategia(self, estrategia: str) -> dict[str, Any]:
        """Actualiza la estrategia activa del grupo en el CDSS."""
        estrategia_limpia = estrategia.strip()
        if not estrategia_limpia:
            raise ClienteValidacionError("El nombre de la estrategia es obligatorio.")
        resp = ejecutar_peticion(
            self._client,
            "API CDSS",
            "PUT",
            f"{self.base_url}/api/v1/configuracion/estrategia",
            headers=self._headers(),
            json={"estrategia": estrategia_limpia},
        )
        return resp.json()


CDSSClient = CdssClient

