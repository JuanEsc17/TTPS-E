"""Cliente HTTP para el modulo externo de Familiograma (TTPS-E Grupo 1)."""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import httpx

from .exceptions import (
    ClienteAutenticacionError,
    ClienteConexionError,
    ClienteServicioError,
    ClienteValidacionError,
)

BASE_URL_DEFAULT = (
    "https://cnylfdemauswqeqmvwmz.supabase.co/functions/v1/familiograma"
)
API_KEY_GRUPO_1_DEFAULT = os.environ.get("FAMILIOGRAMA_API_KEY", "")

# Catalogo estandarizado de parentescos (segun API_Familiograma.md)
PARENTESCOS_MAP: dict[int, str] = {
    0: "paciente",
    1: "progenitor",
    2: "hermano/a",
    3: "abuelo/a materno/a",
    4: "abuelo/a paterno/a",
    5: "tío/a materno/a",
    6: "tío/a paterno/a",
    7: "primo/a materno/a",
    8: "primo/a paterno/a",
    9: "hijo/a",
    10: "medio hermano/a materno/a",
    11: "medio hermano/a paterno/a",
    12: "pareja del paciente",
    13: "suegro/a",
    14: "sobrino/a",
    15: "nieto/a",
}

# Mapa inverso para resolver IDs a partir de etiquetas usuales
PARENTESCOS_POR_NOMBRE: dict[str, int] = {
    "paciente": 0,
    "progenitor": 1,
    "padre": 1,
    "madre": 1,
    "hermano/a": 2,
    "hermano": 2,
    "hermana": 2,
    "abuelo/a materno/a": 3,
    "abuelo materno": 3,
    "abuela materna": 3,
    "abuelo/a paterno/a": 4,
    "abuelo paterno": 4,
    "abuela paterna": 4,
    "tío/a materno/a": 5,
    "tio materno": 5,
    "tia materna": 5,
    "tío/a paterno/a": 6,
    "tio paterno": 6,
    "tia paterna": 6,
    "primo/a materno/a": 7,
    "primo materno": 7,
    "prima materna": 7,
    "primo/a paterno/a": 8,
    "primo paterno": 8,
    "prima paterna": 8,
    "hijo/a": 9,
    "hijo": 9,
    "hija": 9,
    "medio hermano/a materno/a": 10,
    "medio hermano materno": 10,
    "media hermana materna": 10,
    "medio hermano/a paterno/a": 11,
    "medio hermano paterno": 11,
    "media hermana paterna": 11,
    "pareja del paciente": 12,
    "pareja": 12,
    "conyuge": 12,
    "suegro/a": 13,
    "suegro": 13,
    "suegra": 13,
    "sobrino/a": 14,
    "sobrino": 14,
    "sobrina": 14,
    "nieto/a": 15,
    "nieto": 15,
    "nieta": 15,
}


class FamiliogramaClient:
    """Cliente para interactuar con la API externa de Familiograma."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("FAMILIOGRAMA_API_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("FAMILIOGRAMA_API_KEY")
            or API_KEY_GRUPO_1_DEFAULT
        )
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def _procesar_error(self, response: httpx.Response) -> None:
        try:
            datos_error = response.json()
            mensaje = (
                datos_error.get("error", {}).get("mensaje")
                if isinstance(datos_error.get("error"), dict)
                else datos_error.get("error") or datos_error.get("mensaje") or response.text
            )
        except (ValueError, KeyError):
            datos_error = response.text
            mensaje = response.text

        codigo = response.status_code
        if codigo in (401, 403):
            raise ClienteAutenticacionError(
                f"Error de autenticacion en API Familiograma ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        if codigo in (400, 415, 422):
            raise ClienteValidacionError(
                f"Error de validacion en API Familiograma ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        if codigo >= 500:
            raise ClienteServicioError(
                f"Error interno en API Familiograma ({codigo}): {mensaje}",
                codigo_http=codigo,
                respuesta=datos_error,
            )
        response.raise_for_status()

    def verificar_salud(self) -> dict[str, Any]:
        """Consulta el endpoint de salud (publico)."""
        url = f"{self.base_url}/salud"
        try:
            resp = self._client.get(url)
            if not resp.is_success:
                self._procesar_error(resp)
            return resp.json()
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"No se pudo conectar con el endpoint de salud de Familiograma: {exc}"
            ) from exc

    def obtener_parentescos(self) -> list[dict[str, Any]]:
        """Devuelve el catalogo de parentescos (16 opciones)."""
        url = f"{self.base_url}/parentescos"
        try:
            resp = self._client.get(url, headers=self._headers())
            if not resp.is_success:
                self._procesar_error(resp)
            return resp.json()
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"No se pudo consultar el catalogo de parentescos: {exc}"
            ) from exc

    def generar_familiograma(
        self,
        personas: list[dict[str, Any]],
        regla_sospecha: str | None = None,
    ) -> dict[str, Any]:
        """
        Genera el familiograma enviando la nomina de personas.

        Parametros:
            personas: lista de dicts con:
                - parentesco: int (0..15)
                - nombre: str
                - apellido: str
                - sexo: 'hombre' | 'mujer' | 'no_identificado' (opcional)
                - edad: float | int (opcional)
                - fallecido: bool (opcional)
                - sintomas: list[dict] (opcional)
                - diagnosticos: list[dict] (opcional)
            regla_sospecha: 'desactivada' | 'un_cardinal_o_dos_secundarios' (opcional)

        Retorna:
            dict con {"advertencias": list, "imagen": {"tipo": "image/svg+xml", "base64": str}}
        """
        payload: dict[str, Any] = {"personas": personas}
        if regla_sospecha:
            payload["opciones"] = {"reglaSospecha": regla_sospecha}

        try:
            resp = self._client.post(
                self.base_url,
                headers=self._headers(),
                json=payload,
            )
            if not resp.is_success:
                self._procesar_error(resp)
            return resp.json()
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"Fallo de conexion al generar familiograma: {exc}"
            ) from exc

    @staticmethod
    def decodificar_svg(base64_str: str) -> str:
        """Decodifica la cadena base64 devuelta por la API a contenido SVG en texto UTF-8."""
        return base64.b64decode(base64_str).decode("utf-8")

    @staticmethod
    def guardar_svg(base64_str: str, destino_path: str | Path) -> Path:
        """Guarda la imagen SVG decodificada en un archivo en disco."""
        path = Path(destino_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        contenido = base64.b64decode(base64_str)
        path.write_bytes(contenido)
        return path
