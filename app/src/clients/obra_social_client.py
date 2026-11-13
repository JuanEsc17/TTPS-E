"""Cliente HTTP para la API de Obras Sociales (TTPS-E Modulo 6)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from ._base import ejecutar_peticion
from .exceptions import ClienteValidacionError

BASE_URL_DEFAULT = "https://bxsvmfesrtjrqubblgws.supabase.co/functions/v1/api"
MAX_PDF_BYTES = 5 * 1024 * 1024


class ObraSocialClient:
    """Cliente para interactuar con la API externa de Obras Sociales."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("OBRA_SOCIAL_API_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("OBRA_SOCIAL_API_KEY", "")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _headers(self, incluir_json: bool = True) -> dict[str, str]:
        headers = {"x-api-key": self.api_key}
        if incluir_json:
            headers["Content-Type"] = "application/json"
        return headers

    def verificar_estado(self) -> dict[str, Any]:
        """Consulta el endpoint raiz de informacion del servicio (sin API key)."""
        resp = ejecutar_peticion(
            self._client,
            "API Obras Sociales",
            "GET",
            f"{self.base_url}/",
        )
        return resp.json()

    def listar_obras_sociales(
        self,
        buscar: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> dict[str, Any]:
        """Lista las obras sociales activas y su porcentaje de cobertura."""
        if pagina < 1:
            raise ClienteValidacionError("El parametro 'pagina' debe ser >= 1.")
        if not (1 <= por_pagina <= 100):
            raise ClienteValidacionError("El parametro 'por_pagina' debe estar entre 1 y 100.")

        params: dict[str, Any] = {"pagina": pagina, "por_pagina": por_pagina}
        if buscar:
            params["buscar"] = buscar.strip()[:100]

        resp = ejecutar_peticion(
            self._client,
            "API Obras Sociales",
            "GET",
            f"{self.base_url}/obras-sociales",
            headers=self._headers(incluir_json=False),
            params=params,
        )
        return resp.json()

    def listar_solicitudes(
        self,
        estado: str | None = None,
        buscar: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> dict[str, Any]:
        """Lista las solicitudes de autorizacion del grupo."""
        if pagina < 1:
            raise ClienteValidacionError("El parametro 'pagina' debe ser >= 1.")
        if not (1 <= por_pagina <= 100):
            raise ClienteValidacionError("El parametro 'por_pagina' debe estar entre 1 y 100.")

        params: dict[str, Any] = {"pagina": pagina, "por_pagina": por_pagina}
        if estado:
            params["estado"] = estado
        if buscar:
            params["buscar"] = buscar.strip()[:100]

        resp = ejecutar_peticion(
            self._client,
            "API Obras Sociales",
            "GET",
            f"{self.base_url}/solicitudes",
            headers=self._headers(incluir_json=False),
            params=params,
        )
        return resp.json()

    def crear_solicitud(
        self,
        obra_social_id: str,
        paciente_nombre: str,
        fecha: str | date,
        referencia_externa: str | None = None,
    ) -> dict[str, Any]:
        """Da de alta una solicitud de autorizacion de estudio en estado pendiente."""
        nombre_limpio = paciente_nombre.strip()
        if len(nombre_limpio) < 2 or len(nombre_limpio) > 200:
            raise ClienteValidacionError(
                "El nombre del paciente debe tener entre 2 y 200 caracteres."
            )

        fecha_str = fecha.isoformat() if isinstance(fecha, date) else fecha.strip()
        payload: dict[str, Any] = {
            "obra_social_id": str(obra_social_id),
            "paciente_nombre": nombre_limpio,
            "fecha": fecha_str,
        }
        if referencia_externa is not None:
            payload["referencia_externa"] = str(referencia_externa)[:100]

        resp = ejecutar_peticion(
            self._client,
            "API Obras Sociales",
            "POST",
            f"{self.base_url}/solicitudes",
            headers=self._headers(),
            json=payload,
        )
        return resp.json()

    def consultar_solicitud(self, solicitud_id: str) -> dict[str, Any]:
        """Consulta el estado actual de una solicitud de autorizacion por su UUID."""
        resp = ejecutar_peticion(
            self._client,
            "API Obras Sociales",
            "GET",
            f"{self.base_url}/solicitudes/{solicitud_id.strip()}",
            headers=self._headers(incluir_json=False),
        )
        return resp.json()

    def presentar_demanda(
        self,
        solicitud_id: str,
        archivo_pdf: bytes | str | Path,
        nombre_archivo: str = "demanda.pdf",
    ) -> dict[str, Any]:
        """Presenta una demanda en PDF (max 5 MB) sobre una solicitud rechazada."""
        if isinstance(archivo_pdf, (str, Path)):
            ruta = Path(archivo_pdf)
            contenido = ruta.read_bytes()
            nombre_archivo = ruta.name
        else:
            contenido = archivo_pdf

        if not contenido:
            raise ClienteValidacionError("El archivo PDF de la demanda esta vacio.")
        if len(contenido) > MAX_PDF_BYTES:
            raise ClienteValidacionError(
                "El archivo PDF de la demanda supera el maximo permitido de 5 MB."
            )

        resp = ejecutar_peticion(
            self._client,
            "API Obras Sociales",
            "POST",
            f"{self.base_url}/solicitudes/{solicitud_id.strip()}/demanda",
            headers=self._headers(incluir_json=False),
            files={"archivo": (nombre_archivo, contenido, "application/pdf")},
        )
        return resp.json()

    def _url_simulacion(self, token_o_url: str, accion: str) -> str:
        valor = token_o_url.strip()
        if valor.startswith(("http://", "https://")):
            return valor
        return f"{self.base_url}/simulacion/{valor}/{accion}"

    def simular_autorizacion(
        self,
        token_o_url: str,
        porcentaje: float | None = None,
    ) -> dict[str, Any]:
        """Simula que la obra social autoriza la solicitud usando su token o URL."""
        url = self._url_simulacion(token_o_url, "autorizar")
        kwargs: dict[str, Any] = {}
        if porcentaje is not None:
            kwargs["json"] = {"porcentaje": porcentaje}
        resp = ejecutar_peticion(
            self._client,
            "API Obras Sociales",
            "POST",
            url,
            **kwargs,
        )
        return resp.json()

    def simular_rechazo(self, token_o_url: str, motivo: str) -> dict[str, Any]:
        """Simula que la obra social rechaza la solicitud indicando el motivo."""
        motivo_limpio = motivo.strip()
        if len(motivo_limpio) < 3 or len(motivo_limpio) > 500:
            raise ClienteValidacionError(
                "El motivo del rechazo debe tener entre 3 y 500 caracteres."
            )
        url = self._url_simulacion(token_o_url, "rechazar")
        resp = ejecutar_peticion(
            self._client,
            "API Obras Sociales",
            "POST",
            url,
            json={"motivo": motivo_limpio},
        )
        return resp.json()


ObrasSocialesClient = ObraSocialClient

