"""Cliente HTTP para la API de Cupones (TTPS-E / EXOMA CARE)."""
from __future__ import annotations

import os
from typing import Any

import httpx

from ._base import ejecutar_peticion
from .exceptions import ClienteValidacionError

BASE_URL_DEFAULT = "https://vekuhonbpqtzakqbcoph.supabase.co/functions/v1/cupones-api"


class CuponesClient:
    """Cliente para interactuar con la API externa de cupones de descuento."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("CUPONES_API_URL")
            or os.environ.get("CUPONES_API_BASE_URL")
            or BASE_URL_DEFAULT
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("CUPONES_API_KEY", "")
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=self.timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _peticion(self, metodo: str, ruta: str, **kwargs: Any) -> httpx.Response:
        # En Cupones, 403 indica regla de negocio (grupo ya tiene otro gerente).
        return ejecutar_peticion(
            self._client,
            "API Cupones",
            metodo,
            f"{self.base_url}/{ruta.lstrip('/')}",
            headers=self._headers(),
            codigos_autenticacion=(401,),
            codigos_validacion=(400, 403, 404, 405, 409, 413, 415, 422),
            **kwargs,
        )

    def listar_cupones(
        self,
        estado: str | None = None,
        medico_id: str | None = None,
        gerente_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Consulta los cupones del grupo con filtros y paginacion."""
        if not (1 <= limit <= 100):
            raise ClienteValidacionError("El parametro 'limit' debe estar entre 1 y 100.")
        if offset < 0:
            raise ClienteValidacionError("El parametro 'offset' debe ser mayor o igual a 0.")

        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if estado:
            params["estado"] = estado
        if medico_id:
            params["medico_id"] = medico_id
        if gerente_id:
            params["gerente_id"] = gerente_id

        resp = self._peticion("GET", "/cupones", params=params)
        return resp.json()

    def generar_cupones_gerencia(
        self,
        gerente_id: str,
        cantidad: int,
        porcentaje_descuento: float,
    ) -> list[dict[str, Any]]:
        """Genera un lote de cupones disponibles para el gerente del grupo."""
        if cantidad <= 0:
            raise ClienteValidacionError("La cantidad de cupones debe ser mayor a 0.")
        if porcentaje_descuento <= 0:
            raise ClienteValidacionError("El porcentaje de descuento debe ser positivo.")

        payload = {
            "p_gerente_id": str(gerente_id),
            "p_cantidad": cantidad,
            "p_porcentaje_descuento": porcentaje_descuento,
        }
        resp = self._peticion("POST", "/generar_cupones_gerencia", json=payload)
        return resp.json()

    def asignar_cupon_a_medico(
        self,
        gerente_id: str,
        medico_id: str,
        codigo: str,
    ) -> bool:
        """Asigna un cupon disponible del gerente a un medico."""
        payload = {
            "p_gerente_id": str(gerente_id),
            "p_medico_id": str(medico_id),
            "p_codigo": codigo.strip(),
        }
        resp = self._peticion("POST", "/asignar_cupon_a_medico", json=payload)
        return bool(resp.json())

    def asignar_cupon_a_paciente(
        self,
        medico_id: str,
        paciente_id: str,
        codigo: str,
    ) -> bool:
        """Asigna un cupon vigente del medico a un paciente."""
        payload = {
            "p_medico_id": str(medico_id),
            "p_paciente_id": str(paciente_id),
            "p_codigo": codigo.strip(),
        }
        resp = self._peticion("POST", "/asignar_cupon_a_paciente", json=payload)
        return bool(resp.json())

    def canjear_cupon(self, paciente_id: str, codigo: str) -> bool:
        """Canjea un cupon asignado al paciente y registra su uso."""
        payload = {
            "p_paciente_id": str(paciente_id),
            "p_codigo": codigo.strip(),
        }
        resp = self._peticion("POST", "/canjear_cupon", json=payload)
        return bool(resp.json())

