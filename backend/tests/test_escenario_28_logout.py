"""Tests de aceptacion para Escenario 28: Cerrar sesion."""
from datetime import datetime

import pytest
from sqlalchemy import select
from src.core.models import DispositivoConocido, Rol, Usuario
from src.core.services.seguridad import (
    SCOPE_CAMBIO_PASSWORD_INICIAL,
    SCOPE_VERIFICAR_DISPOSITIVO,
    emitir_token,
    hashear_password,
    sha256_hex,
)


def _crear_usuario_con_dispositivo(
    session,
    *,
    email: str = "medico@lab.org",
    rol: Rol = Rol.MEDICO,
    dispositivo_id: str = "pc-habitual",
    debe_cambiar_password: bool = False,
) -> Usuario:
    usuario = Usuario(
        email=email,
        password_hash=hashear_password("Clave1234"),
        rol=rol,
        nombre="Sofia",
        apellido="Gomez",
        telefono="1133445566",
        debe_cambiar_password=debe_cambiar_password,
    )
    session.add(usuario)
    session.flush()
    session.add(
        DispositivoConocido(
            usuario_id=usuario.id,
            identificador=sha256_hex(dispositivo_id),
            ultimo_acceso=datetime(2026, 1, 1, 9, 0, 0),
        )
    )
    session.commit()
    return usuario


def _iniciar_sesion(client, email: str, dispositivo_id: str = "pc-habitual") -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "Clave1234",
            "dispositivo_identificador": dispositivo_id,
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["estado_login"] == "AUTENTICADO"
    return body["access_token"]


def test_tc01_logout_exitoso(client, session):
    usuario = _crear_usuario_con_dispositivo(session)
    token = _iniciar_sesion(client, usuario.email)

    resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["sesion_finalizada"] is True
    assert body["redirect_to"] == "/login"


def test_tc02_ruta_protegida_rechaza_token_revocado(client, session):
    usuario = _crear_usuario_con_dispositivo(session)
    token = _iniciar_sesion(client, usuario.email)

    resp_antes = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp_antes.status_code == 200

    resp_logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp_logout.status_code == 200

    resp_despues = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp_despues.status_code == 401
    assert resp_despues.get_json()["code"] == "SESION_CERRADA_O_INVALIDA"


def test_tc03_ruta_protegida_sin_token_o_token_invalido(client):
    resp_sin = client.get("/api/v1/auth/me")
    assert resp_sin.status_code == 401

    resp_malo = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer token.falso.123"})
    assert resp_malo.status_code == 401


def test_tc04_logout_idempotente_y_sin_token(client, session):
    usuario = _crear_usuario_con_dispositivo(session)
    token = _iniciar_sesion(client, usuario.email)

    primero = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    segundo = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    sin_header = client.post("/api/v1/auth/logout")
    invalido = client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer invalido"})

    for resp in (primero, segundo, sin_header, invalido):
        assert resp.status_code == 200
        assert resp.get_json()["sesion_finalizada"] is True
        assert resp.get_json()["redirect_to"] == "/login"


def test_tc05_logout_conserva_dispositivo_conocido_para_proximo_login(client, session):
    usuario = _crear_usuario_con_dispositivo(session, dispositivo_id="pc-consultorio")
    token_1 = _iniciar_sesion(client, usuario.email, dispositivo_id="pc-consultorio")

    resp_logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token_1}"})
    assert resp_logout.status_code == 200

    dispositivos = session.scalars(
        select(DispositivoConocido).where(DispositivoConocido.usuario_id == usuario.id)
    ).all()
    assert len(dispositivos) == 1

    # Al volver a ingresar desde la misma maquina no pide verificacion 2FA
    token_2 = _iniciar_sesion(client, usuario.email, dispositivo_id="pc-consultorio")
    assert token_2 != token_1
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_1}"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_2}"}).status_code == 200


@pytest.mark.parametrize("scope", [SCOPE_CAMBIO_PASSWORD_INICIAL, SCOPE_VERIFICAR_DISPOSITIVO])
def test_tc06_logout_revoca_tokens_intermedios(app, client, session, scope):
    usuario = _crear_usuario_con_dispositivo(session, debe_cambiar_password=True)
    token_temp = emitir_token(
        app.config["SECRET_KEY"],
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=scope,
        ttl_segundos=600,
    )

    resp_logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token_temp}"})
    assert resp_logout.status_code == 200

    resp_uso = client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token_temp}"},
        json={
            "password_inicial": "Clave1234",
            "nueva_password": "NuevaClave123",
            "confirmacion_password": "NuevaClave123",
            "dispositivo_identificador": "pc-habitual",
        },
    )
    assert resp_uso.status_code == 401
    assert resp_uso.get_json()["code"] == "SESION_CERRADA_O_INVALIDA"


@pytest.mark.parametrize("rol", list(Rol))
def test_tc07_logout_todos_los_roles(client, session, rol):
    usuario = _crear_usuario_con_dispositivo(session, email=f"{rol.value}@lab.org", rol=rol)
    token = _iniciar_sesion(client, usuario.email)

    assert client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
