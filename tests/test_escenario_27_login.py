"""Tests de aceptacion para Escenario 27: Iniciar sesion."""
from datetime import datetime, timedelta

import httpx
import jwt
import pytest
from sqlalchemy import select

from src.clients import EmailClient
from src.core.models import CodigoVerificacion, DispositivoConocido, Rol, Usuario
from src.core.services.auth_service import RUTA_INICIO_POR_ROL
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    SCOPE_CAMBIO_PASSWORD_INICIAL,
    SCOPE_VERIFICAR_DISPOSITIVO,
    hashear_password,
    sha256_hex,
)


def _crear_usuario(
    session,
    *,
    email: str = "usuario@lab.org",
    password: str = "Clave1234",
    rol: Rol = Rol.MEDICO,
    debe_cambiar_password: bool = False,
) -> Usuario:
    usuario = Usuario(
        email=email,
        password_hash=hashear_password(password),
        rol=rol,
        nombre="Ana",
        apellido="Perez",
        telefono="1122334455",
        debe_cambiar_password=debe_cambiar_password,
    )
    session.add(usuario)
    session.commit()
    return usuario


def _registrar_dispositivo(
    session,
    usuario_id: int,
    dispositivo_id: str,
    *,
    ultimo_acceso: datetime | None = None,
) -> DispositivoConocido:
    dispositivo = DispositivoConocido(
        usuario_id=usuario_id,
        identificador=sha256_hex(dispositivo_id),
        ultimo_acceso=ultimo_acceso or datetime(2026, 1, 1, 10, 0, 0),
    )
    session.add(dispositivo)
    session.commit()
    return dispositivo


def _mock_email_client(app, *, status_code: int = 202) -> list[dict]:
    enviados: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        enviados.append({"url": str(request.url), "body": request.read().decode("utf-8")})
        if status_code >= 500:
            return httpx.Response(status_code, json={"error": "Servicio caido"})
        return httpx.Response(status_code, json={"id": "aviso-1", "estado": "pendiente", "creado": True})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    app.extensions["email_client"] = EmailClient(
        base_url="https://mail.mock.test",
        api_key="test-key",
        client=http_client,
    )
    return enviados


def test_tc01_login_maquina_conocida_ok(app, client, session):
    usuario = _crear_usuario(session, email="medico@lab.org", rol=Rol.MEDICO)
    fecha_vieja = datetime.now() - timedelta(days=2)
    dispositivo = _registrar_dispositivo(session, usuario.id, "pc-consultorio", ultimo_acceso=fecha_vieja)

    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "  MEDICO@lab.org ",
            "password": "Clave1234",
            "dispositivo_identificador": "pc-consultorio",
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["estado_login"] == "AUTENTICADO"
    assert body["ruta_inicio"] == RUTA_INICIO_POR_ROL[Rol.MEDICO]

    claims = jwt.decode(body["access_token"], app.config["SECRET_KEY"], algorithms=["HS256"])
    assert claims["sub"] == str(usuario.id)
    assert claims["scope"] == SCOPE_ACCESO_COMPLETO

    session.refresh(dispositivo)
    assert dispositivo.ultimo_acceso > fecha_vieja


def test_tc02_login_primer_ingreso_requiere_cambio_password(app, client, session):
    _crear_usuario(
        session,
        email="paciente@lab.org",
        rol=Rol.PACIENTE,
        debe_cambiar_password=True,
    )
    enviados = _mock_email_client(app)

    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "paciente@lab.org",
            "password": "Clave1234",
            "dispositivo_identificador": "pc-casa",
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["estado_login"] == "REQUIERE_CAMBIO_PASSWORD_INICIAL"
    assert body["requiere_cambio_password"] is True
    assert "ruta_inicio" not in body

    claims = jwt.decode(body["access_token"], app.config["SECRET_KEY"], algorithms=["HS256"])
    assert claims["scope"] == SCOPE_CAMBIO_PASSWORD_INICIAL
    assert enviados == []
    assert session.scalars(select(CodigoVerificacion)).all() == []


def test_tc03_login_maquina_nueva_envia_codigo_y_challenge_token(app, client, session):
    usuario = _crear_usuario(session, email="bio@lab.org", rol=Rol.BIOINFORMATICO)
    enviados = _mock_email_client(app)

    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "bio@lab.org",
            "password": "Clave1234",
            "dispositivo_identificador": "notebook-nueva",
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["estado_login"] == "REQUIERE_VERIFICACION_DISPOSITIVO"
    assert body["requiere_verificacion_dispositivo"] is True

    claims = jwt.decode(body["challenge_token"], app.config["SECRET_KEY"], algorithms=["HS256"])
    assert claims["scope"] == SCOPE_VERIFICAR_DISPOSITIVO
    assert claims["dispositivo_hash"] == sha256_hex("notebook-nueva")

    assert len(enviados) == 1
    codigos = session.scalars(select(CodigoVerificacion)).all()
    assert len(codigos) == 1
    assert codigos[0].usuario_id == usuario.id
    assert codigos[0].usado is False


def test_tc04_tc05_credenciales_invalidas_respuesta_identica(client, session):
    _crear_usuario(session, email="real@lab.org")

    resp_pass_mal = client.post(
        "/api/v1/auth/login",
        json={
            "email": "real@lab.org",
            "password": "Incorrecta",
            "dispositivo_identificador": "pc-1",
        },
    )
    resp_mail_inexistente = client.post(
        "/api/v1/auth/login",
        json={
            "email": "noexiste@lab.org",
            "password": "Incorrecta",
            "dispositivo_identificador": "pc-1",
        },
    )

    assert resp_pass_mal.status_code == 401
    assert resp_mail_inexistente.status_code == 401
    assert resp_pass_mal.get_json() == resp_mail_inexistente.get_json()
    assert resp_pass_mal.get_json()["code"] == "CREDENCIALES_INVALIDAS"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "no-es-mail", "password": "123", "dispositivo_identificador": "pc"},
        {"email": "a@b.com", "password": "", "dispositivo_identificador": "pc"},
        {"email": "a@b.com", "password": "123", "dispositivo_identificador": "   "},
    ],
)
def test_tc06_datos_invalidos_retorna_400(client, payload):
    resp = client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "DATOS_INVALIDOS"


@pytest.mark.parametrize("rol", list(Rol))
def test_tc07_login_exitoso_todos_los_roles(client, session, rol):
    email = f"{rol.value}@lab.org"
    usuario = _crear_usuario(session, email=email, rol=rol)
    _registrar_dispositivo(session, usuario.id, "equipo-rol")

    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "Clave1234",
            "dispositivo_identificador": "equipo-rol",
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["usuario"]["rol"] == rol.value
    assert body["ruta_inicio"] == RUTA_INICIO_POR_ROL[rol]


def test_tc08_fallo_envio_mail_hace_rollback_del_codigo(app, client, session):
    _crear_usuario(session, email="nuevo@lab.org")
    enviados = _mock_email_client(app, status_code=503)

    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "nuevo@lab.org",
            "password": "Clave1234",
            "dispositivo_identificador": "pc-sin-mail",
        },
    )

    assert resp.status_code == 503
    body = resp.get_json()
    assert body["code"] == "ERROR_ENVIO_CODIGO_MAIL"
    assert body["retryable"] is True
    assert len(enviados) == 3  # 1 intento + 2 reintentos
    assert session.scalars(select(CodigoVerificacion)).all() == []
