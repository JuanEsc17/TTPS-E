"""Cliente HTTP para Apigen - API de Bioinformatica (TTPS-E Grupo 10 / Modulo 5)."""
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

BASE_URL_DEFAULT = "https://edmrjmfjklwgazzztjcl.supabase.co/rest/v1"
API_KEY_DEFAULT = "sb_publishable_Ogyld01ST0Gu8zlPBjLmow_9FYtNamo"
GRUPO_ID_DEFAULT = "grupo1"


class ApigenClient:
    """Cliente para interactuar con la API externa de Bioinformatica (Apigen)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        grupo_id: str | None = None,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("APIGEN_API_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("APIGEN_API_KEY")
            or API_KEY_DEFAULT
        )
        self.grupo_id = (
            grupo_id
            or os.environ.get("APIGEN_GRUPO_ID")
            or GRUPO_ID_DEFAULT
        )
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _procesar_error(self, response: httpx.Response) -> None:
        try:
            datos_error = response.json()
            mensaje = (
                datos_error.get("message")
                or datos_error.get("error")
                or response.text
            )
        except (ValueError, KeyError, AttributeError):
            datos_error = response.text
            mensaje = response.text

        codigo = response.status_code
        if codigo in (401, 403):
            raise ClienteAutenticacionError(
                f"Error de autenticacion en Apigen ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        if codigo in (400, 422):
            raise ClienteValidacionError(
                f"Error de validacion en Apigen ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        if codigo >= 500:
            raise ClienteServicioError(
                f"Error interno en Apigen ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        response.raise_for_status()

    def _request(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = f"{self.base_url}/{ruta.lstrip('/')}"
        try:
            resp = self._client.request(
                metodo,
                url,
                params=params,
                json=json,
                headers=self._headers(headers),
            )
            if not resp.is_success:
                self._procesar_error(resp)
            return resp
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"Fallo de conexion con Apigen ({ruta}): {exc}"
            ) from exc

    def buscar_genes(self, prefijo: str, limite: int = 20) -> list[dict[str, Any]]:
        """Endpoint 1: Busca genes por prefijo de simbolo (ej. 'GA' -> [{'simbolo': 'GAA'}, ...])."""
        resp = self._request(
            "GET",
            "/gen",
            params={
                "simbolo": f"ilike.{prefijo.strip()}*",
                "select": "simbolo",
                "limit": limite,
            },
        )
        return resp.json()

    def listar_patologias(
        self,
        grupo_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Endpoint 2: Lista las patologias base mas las registradas por el grupo."""
        payload: dict[str, Any] = {"p_grupo_id": grupo_id or self.grupo_id}
        resp = self._request("POST", "/rpc/listar_patologias", json=payload)
        return resp.json()

    def obtener_genes_por_patologia(
        self,
        patologia: str,
        grupo_id: str | None = None,
    ) -> list[str]:
        """Endpoint 3: Devuelve la lista de simbolos de genes asociados a una patologia."""
        payload: dict[str, Any] = {
            "p_patologia": patologia,
            "p_grupo_id": grupo_id or self.grupo_id,
        }
        resp = self._request("POST", "/rpc/genes_por_patologia", json=payload)
        return resp.json()

    def obtener_genes_hallazgos_secundarios(self) -> list[dict[str, Any]]:
        """Endpoint 4: Devuelve los 84 genes de hallazgos secundarios (ACMG SF v3.3)."""
        resp = self._request(
            "GET",
            "/genes_hallazgos_secundarios",
            params={"select": "gen,condicion,herencia"},
        )
        return resp.json()

    def obtener_variantes(
        self,
        gen: str,
        hgvs_c: str | None = None,
        clasificacion: str | None = None,
        limite: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Endpoint 5: Consulta las variantes conocidas de un gen con filtros opcionales."""
        params: dict[str, Any] = {
            "gen": f"eq.{gen.strip()}",
            "select": "id,hgvs_c,proteina,clasificacion",
            "limit": limite,
            "offset": offset,
        }
        if hgvs_c:
            params["hgvs_c"] = f"ilike.*{hgvs_c.strip()}*"
        if clasificacion:
            params["clasificacion"] = f"eq.{clasificacion.strip()}"

        resp = self._request(
            "GET",
            "/variantes",
            params=params,
            headers={"Prefer": "count=exact"},
        )
        return resp.json()

    def confirmar_diagnostico(
        self,
        patologia: str,
        variantes: list[str],
        grupo_id: str | None = None,
    ) -> bool:
        """Endpoint 6: Evalua si las variantes halladas confirman la patologia (True/False)."""
        payload: dict[str, Any] = {
            "p_patologia": patologia,
            "p_variantes": variantes,
            "p_grupo_id": grupo_id or self.grupo_id,
        }
        resp = self._request("POST", "/rpc/confirma_diagnostico", json=payload)
        return bool(resp.json())

    def obtener_resultado_diagnostico(
        self,
        patologia: str,
        variantes: list[str],
        grupo_id: str | None = None,
    ) -> str:
        """Endpoint 7: Devuelve el resultado diagnostico ('positivo', 'portador' o 'negativo')."""
        payload: dict[str, Any] = {
            "p_patologia": patologia,
            "p_variantes": variantes,
            "p_grupo_id": grupo_id or self.grupo_id,
        }
        resp = self._request("POST", "/rpc/resultado_diagnostico", json=payload)
        return resp.json()

    def obtener_hallazgos_secundarios(
        self,
        variantes: list[str],
        excluir_patologias: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Endpoint 8: Evalua hallazgos secundarios ACMG excluyendo las patologias estudiadas."""
        payload: dict[str, Any] = {
            "p_variantes": variantes,
            "p_excluir_patologias": excluir_patologias or [],
        }
        resp = self._request("POST", "/rpc/hallazgos_secundarios", json=payload)
        return resp.json()

    def registrar_patologia(
        self,
        codigo: str,
        nombre: str,
        genes: list[str],
        herencia: str,
        grupo_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Endpoint 9: Registra o actualiza una patologia propia del grupo en Apigen."""
        payload: dict[str, Any] = {
            "p_grupo_id": grupo_id or self.grupo_id,
            "p_codigo": codigo,
            "p_nombre": nombre,
            "p_genes": genes,
            "p_herencia": herencia,
        }
        resp = self._request("POST", "/rpc/alta_patologia", json=payload)
        return resp.json()


# Alias para compatibilidad con specs que lo referencian como BioinformaticaClient
BioinformaticaClient = ApigenClient

