"""Cliente HTTP liviano para almacenamiento privado de archivos en Supabase Storage."""
from __future__ import annotations

import os
from urllib.parse import quote

import httpx

from .exceptions import (
    ClienteAutenticacionError,
    ClienteConexionError,
    ClienteServicioError,
)

BUCKET_DEFAULT = "exoma-storage"


class SupabaseStorageClient:
    """Gestiona subida, descarga y eliminacion de archivos en Supabase Storage via REST."""

    def __init__(
        self,
        supabase_url: str | None = None,
        service_role_key: str | None = None,
        bucket: str | None = None,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.supabase_url = (
            supabase_url if supabase_url is not None else os.environ.get("SUPABASE_URL", "")
        ).strip().rstrip("/")
        self.service_role_key = (
            service_role_key
            if service_role_key is not None
            else os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        ).strip()
        self.bucket = (
            bucket
            if bucket is not None
            else os.environ.get("SUPABASE_STORAGE_BUCKET", BUCKET_DEFAULT)
        ).strip() or BUCKET_DEFAULT
        self.timeout = timeout
        self._client = client

    def esta_configurado(self) -> bool:
        """Indica si el cliente posee URL y credencial de servicio configuradas."""
        return bool(self.supabase_url and self.service_role_key and self.bucket)

    def _headers_base(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
        }

    def _url_objeto(self, ruta_objeto: str) -> str:
        clave = quote(ruta_objeto.lstrip("/"), safe="/")
        return f"{self.supabase_url}/storage/v1/object/{quote(self.bucket, safe='')}/{clave}"

    def _ejecutar(self, fn):
        if self._client is not None:
            return fn(self._client)
        with httpx.Client(timeout=self.timeout) as cliente:
            return fn(cliente)

    @staticmethod
    def _es_objeto_inexistente(resp: httpx.Response) -> bool:
        if resp.status_code == 404:
            return True
        if resp.status_code == 400:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            status_interno = str(body.get("statusCode", ""))
            error_texto = f"{body.get('error', '')} {body.get('message', '')}".lower()
            return status_interno == "404" or "not_found" in error_texto or "not found" in error_texto
        return False

    @staticmethod
    def _elevar_error_http(resp: httpx.Response, operacion: str) -> None:
        detalle = resp.text[:300]
        if resp.status_code in (401, 403):
            raise ClienteAutenticacionError(
                f"Error de autenticacion en Supabase Storage al {operacion} ({resp.status_code}): {detalle}",
                codigo_http=resp.status_code,
                respuesta=detalle,
            )
        raise ClienteServicioError(
            f"Error en Supabase Storage al {operacion} ({resp.status_code}): {detalle}",
            codigo_http=resp.status_code,
            respuesta=detalle,
        )

    def subir_archivo(
        self,
        ruta_objeto: str,
        contenido: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Sube o reemplaza (upsert) un archivo binario en el bucket configurado."""
        url = self._url_objeto(ruta_objeto)
        headers = {
            **self._headers_base(),
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        try:
            resp = self._ejecutar(lambda c: c.post(url, headers=headers, content=contenido))
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"No se pudo conectar con Supabase Storage para subir {ruta_objeto!r}: {exc}"
            ) from exc

        if not resp.is_success:
            self._elevar_error_http(resp, f"subir {ruta_objeto!r}")

    def descargar_archivo(self, ruta_objeto: str) -> bytes | None:
        """Descarga un archivo del bucket o retorna None si no existe."""
        url = self._url_objeto(ruta_objeto)
        headers = self._headers_base()
        try:
            resp = self._ejecutar(lambda c: c.get(url, headers=headers))
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"No se pudo conectar con Supabase Storage para descargar {ruta_objeto!r}: {exc}"
            ) from exc

        if self._es_objeto_inexistente(resp):
            return None
        if not resp.is_success:
            self._elevar_error_http(resp, f"descargar {ruta_objeto!r}")
        return resp.content

    def eliminar_archivo(self, ruta_objeto: str) -> None:
        """Elimina un archivo del bucket si existe."""
        url = f"{self.supabase_url}/storage/v1/object/{quote(self.bucket, safe='')}"
        headers = {
            **self._headers_base(),
            "Content-Type": "application/json",
        }
        clave = ruta_objeto.lstrip("/")
        try:
            resp = self._ejecutar(
                lambda c: c.request("DELETE", url, headers=headers, json={"prefixes": [clave]})
            )
        except httpx.RequestError as exc:
            raise ClienteConexionError(
                f"No se pudo conectar con Supabase Storage para eliminar {ruta_objeto!r}: {exc}"
            ) from exc

        if self._es_objeto_inexistente(resp):
            return
        if not resp.is_success:
            self._elevar_error_http(resp, f"eliminar {ruta_objeto!r}")
