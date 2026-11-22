"""Tests de aceptacion para Escenario 34: Cambiar la contrasena."""
import pytest
from src.core.database import db
from src.core.models import DispositivoConocido, Rol, Usuario
from src.core.services.seguridad import (
    SCOPE_CAMBIO_PASSWORD_INICIAL,
    emitir_token,
    hashear_password,
    sha256_hex,
)


def _crear_usuario_y_login(
    client,
    session,
    *,
    rol: Rol = Rol.PACIENTE,
    email: str = "usuario@lab.org",
    password: str = "ClaveActual1",
    dispositivo: str = "pc-habitual",
) -> tuple[Usuario, str]:
    usuario = Usuario(
        email=email,
        password_hash=hashear_password(password),
        rol=rol,
        nombre="Ana",
        apellido="Gomez",
        telefono="1144556677",
        debe_cambiar_password=False,
    )
    session.add(usuario)
    session.flush()
    session.add(DispositivoConocido(usuario_id=usuario.id, identificador=sha256_hex(dispositivo)))
    session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "dispositivo_identificador": dispositivo},
    )
    assert resp.status_code == 200
    return usuario, resp.get_json()["access_token"]


def test_tc01_cambio_password_exitoso_rota_sesion_y_actualiza_login(client, session):
    usuario, token_anterior = _crear_usuario_y_login(client, session)

    resp = client.post(
        "/api/v1/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token_anterior}"},
        json={
            "password_actual": "ClaveActual1",
            "password_nueva": "ClaveNueva2026",
            "password_nueva_confirmacion": "ClaveNueva2026",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["usuario_id"] == usuario.id
    token_nuevo = body["access_token"]
    assert token_nuevo != token_anterior

    # El token anterior queda revocado y el nuevo sigue autenticado
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_anterior}"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_nuevo}"}).status_code == 200

    # Login con clave vieja falla y con la nueva funciona directamente (conserva dispositivo conocido)
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": usuario.email, "password": "ClaveActual1", "dispositivo_identificador": "pc-habitual"},
        ).status_code
        == 401
    )
    login_nuevo = client.post(
        "/api/v1/auth/login",
        json={"email": usuario.email, "password": "ClaveNueva2026", "dispositivo_identificador": "pc-habitual"},
    )
    assert login_nuevo.status_code == 200
    assert login_nuevo.get_json()["estado_login"] == "AUTENTICADO"


@pytest.mark.parametrize("rol", list(Rol))
def test_tc02_habilitado_para_los_7_roles(client, session, rol):
    _, token = _crear_usuario_y_login(client, session, rol=rol, email=f"{rol.value.lower()}@lab.org")

    resp = client.post(
        "/api/v1/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "password_actual": "ClaveActual1",
            "password_nueva": "ClaveSegura99",
            "password_nueva_confirmacion": "ClaveSegura99",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["usuario"]["rol"] == rol.value


def test_tc03_rechazo_por_password_actual_incorrecta(client, session):
    usuario, token = _crear_usuario_y_login(client, session)
    hash_original = usuario.password_hash

    resp = client.post(
        "/api/v1/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "password_actual": "Incorrecta99",
            "password_nueva": "ClaveNueva2026",
            "password_nueva_confirmacion": "ClaveNueva2026",
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "PASSWORD_ACTUAL_INCORRECTA"
    session.refresh(usuario)
    assert usuario.password_hash == hash_original


def test_tc04_rechazo_cuando_nueva_password_igual_a_actual(client, session):
    _, token = _crear_usuario_y_login(client, session)

    resp = client.post(
        "/api/v1/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "password_actual": "ClaveActual1",
            "password_nueva": "ClaveActual1",
            "password_nueva_confirmacion": "ClaveActual1",
        },
    )
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "PASSWORD_IGUAL_A_ACTUAL"


@pytest.mark.parametrize(
    ("nueva", "confirmacion", "codigo_esperado"),
    [
        ("ClaveNueva2026", "OtraClave2026", "CONFIRMACION_NO_COINCIDE"),
        ("Abc12", "Abc12", "PASSWORD_DEBIL"),
        ("SoloLetrasSinNum", "SoloLetrasSinNum", "PASSWORD_DEBIL"),
    ],
)
def test_tc05_rechazo_confirmacion_o_password_debil(client, session, nueva, confirmacion, codigo_esperado):
    _, token = _crear_usuario_y_login(client, session)

    resp = client.post(
        "/api/v1/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "password_actual": "ClaveActual1",
            "password_nueva": nueva,
            "password_nueva_confirmacion": confirmacion,
        },
    )
    assert resp.status_code == 422
    assert resp.get_json()["code"] == codigo_esperado


def test_tc06_rechazo_sin_sesion_o_con_primer_ingreso_pendiente(app, client, session):
    assert client.post("/api/v1/auth/cambiar-password", json={}).status_code == 401

    usuario = Usuario(
        email="inicial@lab.org",
        password_hash=hashear_password("Temp1234"),
        rol=Rol.PACIENTE,
        nombre="Luis",
        apellido="Paz",
        telefono="1122334455",
        debe_cambiar_password=True,
    )
    session.add(usuario)
    session.commit()
    token_inicial = emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_CAMBIO_PASSWORD_INICIAL,
        ttl_segundos=600,
    )

    resp = client.post(
        "/api/v1/auth/cambiar-password",
        headers={"Authorization": f"Bearer {token_inicial}"},
        json={
            "password_actual": "Temp1234",
            "password_nueva": "ClaveSegura99",
            "password_nueva_confirmacion": "ClaveSegura99",
        },
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "DEBE_CAMBIAR_PASSWORD_INICIAL"


def test_tc07_fallo_bd_en_commit_hace_rollback_y_preserva_clave_y_sesion(client, session, monkeypatch):
    usuario, token = _crear_usuario_y_login(client, session)

    def _fallar_commit():
        raise RuntimeError("Fallo simulado de BD")

    monkeypatch.setattr(db.session, "commit", _fallar_commit)
    with pytest.raises(RuntimeError, match="Fallo simulado"):
        client.post(
            "/api/v1/auth/cambiar-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "password_actual": "ClaveActual1",
                "password_nueva": "ClaveNueva2026",
                "password_nueva_confirmacion": "ClaveNueva2026",
            },
        )
    monkeypatch.undo()

    # Tanto la sesion como la clave anterior siguen intactas
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": usuario.email, "password": "ClaveActual1", "dispositivo_identificador": "pc-habitual"},
        ).status_code
        == 200
    )
