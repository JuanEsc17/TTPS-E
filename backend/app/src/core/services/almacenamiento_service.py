"""Servicio centralizado de almacenamiento de archivos (local en dev/tests o Supabase Storage en prod)."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from flask import current_app, has_app_context
from src.clients import ClienteError, SupabaseStorageClient
from src.core.services.excepciones import ErrorDominio

logger = logging.getLogger(__name__)


def _obtener_directorio_base_local() -> Path:
    if has_app_context() and current_app.config.get("STORAGE_DIR"):
        return Path(str(current_app.config["STORAGE_DIR"])).resolve()
    env_dir = os.environ.get("STORAGE_DIR", "").strip()
    if env_dir:
        return Path(env_dir).resolve()
    return (Path(__file__).resolve().parents[3] / "storage").resolve()


def resolver_ruta_local(ruta_relativa: str) -> Path:
    """Resuelve y valida una ruta logica 'storage/...' dentro del directorio local permitido."""
    if not ruta_relativa or "\x00" in ruta_relativa:
        raise ErrorDominio(
            "Ruta de archivo invalida.",
            codigo="RUTA_ARCHIVO_INVALIDA",
            http_status=400,
        )

    base_dir = _obtener_directorio_base_local()
    limpia = ruta_relativa.replace("\\", "/").lstrip("/")
    limpia = limpia.removeprefix("storage/")

    ruta_fisica = (base_dir / limpia).resolve()
    if not ruta_fisica.is_relative_to(base_dir) or ruta_fisica == base_dir:
        raise ErrorDominio(
            "Ruta de archivo fuera del directorio permitido.",
            codigo="RUTA_ARCHIVO_INVALIDA",
            http_status=400,
        )
    return ruta_fisica


def normalizar_clave_storage(ruta_relativa: str) -> str:
    """Valida la ruta logica y devuelve la clave relativa normalizada para buckets remotos."""
    ruta_fisica = resolver_ruta_local(ruta_relativa)
    base_dir = _obtener_directorio_base_local()
    return ruta_fisica.relative_to(base_dir).as_posix()


def usar_storage_remoto() -> bool:
    """Determina si se debe persistir en Supabase Storage en lugar de disco local."""
    if has_app_context():
        override = current_app.config.get("USAR_STORAGE_REMOTO")
        if override is not None:
            return bool(override)
        if current_app.config.get("TESTING"):
            return False
    return SupabaseStorageClient().esta_configurado()


def guardar_bytes(
    ruta_relativa: str,
    contenido: bytes,
    *,
    content_type: str = "application/octet-stream",
    cliente: SupabaseStorageClient | None = None,
) -> Path:
    """Persiste bytes de forma atomica en disco local o en Supabase Storage."""
    ruta_fisica = resolver_ruta_local(ruta_relativa)
    if usar_storage_remoto():
        clave = normalizar_clave_storage(ruta_relativa)
        storage_client = cliente or SupabaseStorageClient()
        storage_client.subir_archivo(clave, contenido, content_type=content_type)
        return ruta_fisica

    ruta_fisica.parent.mkdir(parents=True, exist_ok=True)
    ruta_tmp = ruta_fisica.with_name(f".{ruta_fisica.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        ruta_tmp.write_bytes(contenido)
        os.replace(ruta_tmp, ruta_fisica)
    finally:
        ruta_tmp.unlink(missing_ok=True)
    return ruta_fisica


def leer_bytes(
    ruta_relativa: str,
    *,
    cliente: SupabaseStorageClient | None = None,
) -> bytes | None:
    """Lee bytes desde Supabase Storage o disco local; retorna None si el archivo no existe."""
    ruta_fisica = resolver_ruta_local(ruta_relativa)
    if usar_storage_remoto():
        clave = normalizar_clave_storage(ruta_relativa)
        storage_client = cliente or SupabaseStorageClient()
        return storage_client.descargar_archivo(clave)

    if not ruta_fisica.is_file():
        return None
    return ruta_fisica.read_bytes()


def eliminar_archivo(
    ruta_relativa: str,
    *,
    cliente: SupabaseStorageClient | None = None,
) -> None:
    """Elimina un archivo en modo best-effort tanto en almacenamiento remoto como local."""
    try:
        ruta_fisica = resolver_ruta_local(ruta_relativa)
    except ErrorDominio:
        return

    if usar_storage_remoto():
        try:
            clave = normalizar_clave_storage(ruta_relativa)
            storage_client = cliente or SupabaseStorageClient()
            storage_client.eliminar_archivo(clave)
        except ClienteError as exc:
            logger.warning(
                "[almacenamiento_service] error_eliminar_remoto ruta=%r err=%s",
                ruta_relativa,
                exc,
            )

    ruta_fisica.unlink(missing_ok=True)
