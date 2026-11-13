"""Cliente HTTP para la API de sintomas SNOMED CT (TTPS-E)."""
from __future__ import annotations

import os
from typing import Any

import httpx

from .exceptions import (
    ClienteAutenticacionError,
    ClienteConexionError,
    ClienteServicioError,
    ClienteValidacionError,
)

BASE_URL_DEFAULT = (
    "https://hwmpslajqivdqeaylhdc.supabase.co/functions/v1/terminologia/sintomas"
)
API_KEY_GRUPO_1_DEFAULT = os.environ.get("SNOMED_API_KEY", "")


class SnomedClient:
    """Cliente para interactuar con la API externa de sintomas SNOMED CT."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        region: str = "us-east-1",
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("SNOMED_API_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("SNOMED_API_KEY")
            or API_KEY_GRUPO_1_DEFAULT
        )
        self.region = region
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "x-region": self.region,
        }

    def _procesar_error(self, response: httpx.Response) -> None:
        try:
            datos_error = response.json()
            mensaje = (
                datos_error.get("detalle")
                or datos_error.get("error")
                or response.text
            )
        except (ValueError, KeyError, AttributeError):
            datos_error = response.text
            mensaje = response.text

        codigo = response.status_code
        if codigo in (401, 403):
            raise ClienteAutenticacionError(
                f"Error de autenticacion en API SNOMED ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        if codigo in (400, 422):
            raise ClienteValidacionError(
                f"Error de validacion en API SNOMED ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        if codigo >= 500:
            raise ClienteServicioError(
                f"Error interno en API SNOMED ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        response.raise_for_status()

    def buscar_sintomas(
        self,
        texto: str,
        limite: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Busca sintomas en SNOMED CT Edicion Argentina (directa, lexica y semantica).

        Parametros:
            texto: Texto libre ingresado por el medico (minimo 3 caracteres).
            limite: Maximo de resultados a devolver (entre 1 y 50, por defecto 10).

        Retorna:
            Lista de dicts con {"sctid": str, "termino_preferido": str, "estrategia": str, ...}.
        """
        texto_limpio = texto.strip()
        if len(texto_limpio) < 3:
            raise ClienteValidacionError(
                "El texto de busqueda en SNOMED debe tener al menos 3 caracteres."
            )
        if not (1 <= limite <= 50):
            raise ClienteValidacionError(
                "El limite de resultados de SNOMED debe estar entre 1 y 50."
            )

        try:
            resp = self._client.get(
                self.base_url,
                params={"q": texto_limpio, "limite": limite},
                headers=self._headers(),
            )
            if not resp.is_success:
                self._procesar_error(resp)
            datos = resp.json()
            resultados = datos.get("resultados", []) if isinstance(datos, dict) else datos
            for item in resultados:
                if "sctid" in item and item["sctid"] is not None:
                    item["sctid"] = str(item["sctid"])
            return resultados
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"Fallo de conexion con la API de SNOMED: {exc}"
            ) from exc

