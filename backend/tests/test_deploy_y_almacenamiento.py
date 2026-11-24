"""Tests para configuracion de deploy (Render + Supabase), healthcheck y almacenamiento."""
from __future__ import annotations

import httpx
import pytest
from src.clients import (
    ClienteAutenticacionError,
    ClienteServicioError,
    SupabaseStorageClient,
)
from src.core.database import construir_config_engine, normalizar_database_url
from src.core.services import almacenamiento_service
from src.core.services.excepciones import ErrorDominio


def test_normalizar_database_url_convierte_esquemas_postgres_y_agrega_ssl_supabase():
    url_pooler = "postgres://postgres.abc:clave@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
    assert normalizar_database_url(url_pooler) == (
        "postgresql+psycopg://postgres.abc:clave@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
    )

    url_postgresql = "postgresql://user:pass@localhost:5432/exoma"
    assert normalizar_database_url(url_postgresql) == "postgresql+psycopg://user:pass@localhost:5432/exoma"

    url_con_ssl = (
        "postgresql+psycopg://postgres.abc:clave@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
        "?sslmode=verify-full"
    )
    assert normalizar_database_url(url_con_ssl) == url_con_ssl
    assert normalizar_database_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_construir_config_engine_diferencia_sqlite_y_postgresql(monkeypatch):
    assert construir_config_engine("sqlite:///:memory:") == "sqlite:///:memory:"

    monkeypatch.setenv("DB_POOL_SIZE", "4")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "1")
    cfg = construir_config_engine("postgres://user:pass@db.ejemplo.com:5432/exoma")
    assert isinstance(cfg, dict)
    assert cfg["url"] == "postgresql+psycopg://user:pass@db.ejemplo.com:5432/exoma"
    assert cfg["pool_pre_ping"] is True
    assert cfg["pool_size"] == 4
    assert cfg["max_overflow"] == 1
    assert cfg["pool_recycle"] == 300


def test_health_endpoint_ok_y_degradado(app, client, monkeypatch):
    resp_ok = client.get("/api/health")
    assert resp_ok.status_code == 200
    assert resp_ok.get_json() == {
        "ok": True,
        "estado": "operativo",
        "base_de_datos": "conectada",
    }

    from sqlalchemy.exc import OperationalError
    from src.core import database as database_mod
    from src.web.api import salud as salud_mod

    def _fallar_connect():
        raise OperationalError("SELECT 1", {}, Exception("sin red"))

    with app.app_context():
        monkeypatch.setattr(database_mod.db.engine, "connect", _fallar_connect)
        assert database_mod.verificar_conexion_db() is False

    monkeypatch.setattr(salud_mod, "verificar_conexion_db", lambda: False)
    resp_err = client.get("/api/health")
    assert resp_err.status_code == 503
    assert resp_err.get_json() == {
        "ok": False,
        "estado": "degradado",
        "base_de_datos": "desconectada",
    }


def test_cli_init_db_es_idempotente(app):
    runner = app.test_cli_runner()
    resultado = runner.invoke(args=["init-db"])
    assert resultado.exit_code == 0
    assert "Tablas verificadas/creadas correctamente." in resultado.output


def test_supabase_storage_client_subir_descargar_y_eliminar():
    almacen: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer service-secret"
        assert request.headers["apikey"] == "service-secret"

        if request.method == "POST":
            assert request.headers["x-upsert"] == "true"
            clave = request.url.path.split("/storage/v1/object/exoma-storage/", 1)[1]
            almacen[clave] = request.content
            return httpx.Response(200, json={"Key": f"exoma-storage/{clave}"})

        if request.method == "GET":
            clave = request.url.path.split("/storage/v1/object/exoma-storage/", 1)[1]
            if clave not in almacen:
                return httpx.Response(
                    400,
                    json={"statusCode": "404", "error": "not_found", "message": "Object not found"},
                )
            return httpx.Response(200, content=almacen[clave])

        if request.method == "DELETE":
            for prefijo in httpx.Response(200, content=request.content).json()["prefixes"]:
                almacen.pop(prefijo, None)
            return httpx.Response(200, json=[])

        return httpx.Response(405)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    storage_client = SupabaseStorageClient(
        supabase_url="https://proyecto.supabase.co",
        service_role_key="service-secret",
        bucket="exoma-storage",
        client=http_client,
    )

    assert storage_client.esta_configurado() is True
    storage_client.subir_archivo("resultados/estudio_1.pdf", b"%PDF-1.4 demo", content_type="application/pdf")
    assert storage_client.descargar_archivo("resultados/estudio_1.pdf") == b"%PDF-1.4 demo"

    storage_client.eliminar_archivo("resultados/estudio_1.pdf")
    assert storage_client.descargar_archivo("resultados/estudio_1.pdf") is None


def test_supabase_storage_client_mapea_errores_http():
    def handler_401(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized")

    client_401 = SupabaseStorageClient(
        supabase_url="https://proyecto.supabase.co",
        service_role_key="bad",
        bucket="exoma-storage",
        client=httpx.Client(transport=httpx.MockTransport(handler_401)),
    )
    with pytest.raises(ClienteAutenticacionError):
        client_401.subir_archivo("datos_crudos/estudio_1.txt", b"ACTG")

    def handler_500(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal error")

    client_500 = SupabaseStorageClient(
        supabase_url="https://proyecto.supabase.co",
        service_role_key="good",
        bucket="exoma-storage",
        client=httpx.Client(transport=httpx.MockTransport(handler_500)),
    )
    with pytest.raises(ClienteServicioError):
        client_500.descargar_archivo("datos_crudos/estudio_1.txt")


def test_almacenamiento_service_local_remoto_y_path_traversal(app, tmp_path):
    app.config["STORAGE_DIR"] = str(tmp_path)

    with app.app_context():
        # En TESTING usa local aunque haya variables de entorno remotas
        assert almacenamiento_service.usar_storage_remoto() is False

        almacenamiento_service.guardar_bytes("storage/datos_crudos/estudio_99.txt", b"ACGTACGT")
        assert almacenamiento_service.leer_bytes("storage/datos_crudos/estudio_99.txt") == b"ACGTACGT"
        almacenamiento_service.eliminar_archivo("storage/datos_crudos/estudio_99.txt")
        assert almacenamiento_service.leer_bytes("storage/datos_crudos/estudio_99.txt") is None

        # Bloquea path traversal tanto en local como en remoto
        app.config["USAR_STORAGE_REMOTO"] = True
        with pytest.raises(ErrorDominio) as exc_info:
            almacenamiento_service.leer_bytes("../../etc/passwd")
        assert exc_info.value.codigo == "RUTA_ARCHIVO_INVALIDA"
        assert exc_info.value.http_status == 400

        # Modo remoto explicito delega al cliente HTTP
        objetos: dict[str, bytes] = {}

        class _FakeStorage:
            def subir_archivo(self, ruta_objeto: str, contenido: bytes, *, content_type: str = ""):
                objetos[ruta_objeto] = contenido

            def descargar_archivo(self, ruta_objeto: str) -> bytes | None:
                return objetos.get(ruta_objeto)

            def eliminar_archivo(self, ruta_objeto: str) -> None:
                objetos.pop(ruta_objeto, None)

        fake = _FakeStorage()
        almacenamiento_service.guardar_bytes(
            "storage/familiogramas/paciente_dni_123.svg",
            b"<svg/>",
            content_type="image/svg+xml",
            cliente=fake,
        )
        assert objetos["familiogramas/paciente_dni_123.svg"] == b"<svg/>"
        assert (
            almacenamiento_service.leer_bytes("storage/familiogramas/paciente_dni_123.svg", cliente=fake)
            == b"<svg/>"
        )
        almacenamiento_service.eliminar_archivo("storage/familiogramas/paciente_dni_123.svg", cliente=fake)
        assert (
            almacenamiento_service.leer_bytes("storage/familiogramas/paciente_dni_123.svg", cliente=fake)
            is None
        )
