"""Cliente HTTP para la API de Optimizacion de Recorridos (OSRM / TTPS-E)."""
from __future__ import annotations

import os
from typing import Any

import httpx

from .exceptions import (
    ClienteConexionError,
    ClienteServicioError,
    ClienteValidacionError,
)

BASE_URL_DEFAULT = "https://optimizacionapi.vercel.app/"


class OptimizacionClient:
    """Cliente para interactuar con el microservicio/API de optimizacion de recorridos."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("OPTIMIZACION_API_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _procesar_error(self, response: httpx.Response) -> None:
        try:
            datos_error = response.json()
            mensaje = datos_error.get("error") or datos_error.get("errores_validacion") or response.text
        except (ValueError, KeyError):
            datos_error = response.text
            mensaje = response.text

        codigo = response.status_code
        if codigo in (400, 422):
            raise ClienteValidacionError(
                f"Error en peticion de optimizacion ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        if codigo >= 500:
            raise ClienteServicioError(
                f"Error del servidor de mapas OSRM ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        response.raise_for_status()

    def optimizar_recorrido(
        self,
        coordenadas: list[dict[str, float]],
    ) -> list[dict[str, float]]:
        """
        Optimiza el orden de las paradas intermedias de un itinerario.

        Parametros:
            coordenadas: Lista de al menos 2 coordenadas [{"lat": float, "lon": float}, ...].
                         La 1.ª coordenada es el origen fijo y la última el destino fijo.

        Retorna:
            Lista de coordenadas en el orden optimizado por OSRM.
        """
        if len(coordenadas) < 2:
            raise ClienteValidacionError(
                "Se requieren al menos 2 coordenadas para optimizar el recorrido (origen y destino)."
            )

        payload: dict[str, Any] = {"coordenadas": coordenadas}
        url = f"{self.base_url}/api/optimizacion"

        try:
            resp = self._client.post(url, json=payload)
            if not resp.is_success:
                self._procesar_error(resp)
            data = resp.json()
            # La API devuelve {"coordenadas": [...]} o directamente [...]
            if isinstance(data, dict) and "coordenadas" in data:
                return data["coordenadas"]
            if isinstance(data, list):
                return data
            return data
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"Fallo de conexion con la API de optimizacion de recorridos: {exc}"
            ) from exc
