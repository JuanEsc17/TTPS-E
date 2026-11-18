"""Tests de aceptacion para Escenario 20: Cambiar la contrasena inicial."""
import jwt
import pytest
from sqlalchemy import select
from src.core.models import DispositivoConocido, Rol, Usuario
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    SCOPE_CAMBIO_PASSWORD_INICIAL,
    emitir_token,
    hashear_password,
    sha256_hex,
)


def _crear_paciente_inicial(
    session,
    *,
    email: str = "paciente.nuevo@lab.org",
    password_inicial: str = "Temp1234",
    debe_cambiar_password: bool = True,
) -> Usuario:
    usuario = Usuario(
        email=email,
        password_hash=hashear_password(password_inicial),
        rol=Rol.PACIENTE,
        nombre="Lucia",
        apellido="Fernandez",
        telefono="1144556677",
        debe_cambiar_password=debe_cambiar_password,
    )
    session.add(usuario)
    session.commit()
    return usuario


def _login_primer_ingreso(client, email: str, password_inicial: str, dispositivo: str = "pc-casa") -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password_inicial,
            "dispositivo_identificador": dispositivo,
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["estado_login"] == "REQUIERE_CAMBIO_PASSWORD_INICIAL"
    return body["access_token"]


def test_tc01_cambio_password_inicial_exitoso_y_login_posterior_directo(app, client, session):
    usuario = _crear_paciente_inicial(session)
    token_inicial = _login_primer_ingreso(client, usuario.email, "Temp1234", "pc-lucia")

    resp = client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token_inicial}"},
        json={
            "password_inicial": "Temp1234",
            "nueva_password": "MiClaveSegura2026",
            "confirmacion_password": "MiClaveSegura2026",
            "dispositivo_identificador": "pc-lucia",
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["estado_login"] == "AUTENTICADO"
    assert body["dispositivo_registrado"] is True
    assert body["ruta_inicio"] == "/paciente/estudios"

    claims = jwt.decode(body["access_token"], app.config["SECRET_KEY"], algorithms=["HS256"])
    assert claims["scope"] == SCOPE_ACCESO_COMPLETO

    session.refresh(usuario)
    assert usuario.debe_cambiar_password is False

    dispositivos = session.scalars(
        select(DispositivoConocido).where(DispositivoConocido.usuario_id == usuario.id)
    ).all()
    assert len(dispositivos) == 1
    assert dispositivos[0].identificador == sha256_hex("pc-lucia")

    # Con la nueva clave y desde el mismo equipo ya ingresa directo sin 2FA
    resp_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": usuario.email,
            "password": "MiClaveSegura2026",
            "dispositivo_identificador": "pc-lucia",
        },
    )
    assert resp_login.status_code == 200
    assert resp_login.get_json()["estado_login"] == "AUTENTICADO"


@pytest.mark.parametrize(
    ("nueva_password", "codigo_esperado"),
    [
        ("Temp1234", "PASSWORD_IGUAL_A_INICIAL"),
        ("corta1", "NUEVA_PASSWORD_INVALIDA"),
        ("sololetras", "NUEVA_PASSWORD_INVALIDA"),
        ("12345678", "NUEVA_PASSWORD_INVALIDA"),
    ],
)
def test_tc02_nueva_password_igual_o_debil_retorna_400(
    client, session, nueva_password, codigo_esperado
):
    usuario = _crear_paciente_inicial(session)
    token_inicial = _login_primer_ingreso(client, usuario.email, "Temp1234")

    resp = client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token_inicial}"},
        json={
            "password_inicial": "Temp1234",
            "nueva_password": nueva_password,
            "confirmacion_password": nueva_password,
            "dispositivo_identificador": "pc-casa",
        },
    )

    assert resp.status_code == 400
    assert resp.get_json()["code"] == codigo_esperado
    session.refresh(usuario)
    assert usuario.debe_cambiar_password is True


def test_tc03_confirmacion_no_coincide_retorna_400(client, session):
    usuario = _crear_paciente_inicial(session)
    token_inicial = _login_primer_ingreso(client, usuario.email, "Temp1234")

    resp = client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token_inicial}"},
        json={
            "password_inicial": "Temp1234",
            "nueva_password": "MiClaveSegura2026",
            "confirmacion_password": "OtraClaveDistinta1",
            "dispositivo_identificador": "pc-casa",
        },
    )

    assert resp.status_code == 400
    assert resp.get_json()["code"] == "NUEVA_PASSWORD_INVALIDA"


def test_tc04_password_inicial_incorrecta_retorna_401(client, session):
    usuario = _crear_paciente_inicial(session)
    hash_original = usuario.password_hash
    token_inicial = _login_primer_ingreso(client, usuario.email, "Temp1234")

    resp = client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token_inicial}"},
        json={
            "password_inicial": "Incorrecta999",
            "nueva_password": "MiClaveSegura2026",
            "confirmacion_password": "MiClaveSegura2026",
            "dispositivo_identificador": "pc-casa",
        },
    )

    assert resp.status_code == 401
    assert resp.get_json()["code"] == "PASSWORD_INICIAL_INCORRECTA"
    session.refresh(usuario)
    assert usuario.password_hash == hash_original
    assert usuario.debe_cambiar_password is True


def test_tc05_usuario_ya_cambio_password_inicial_retorna_409(app, client, session):
    usuario = _crear_paciente_inicial(session, debe_cambiar_password=False)
    token_restringido = emitir_token(
        app.config["SECRET_KEY"],
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_CAMBIO_PASSWORD_INICIAL,
        ttl_segundos=600,
    )

    resp = client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token_restringido}"},
        json={
            "password_inicial": "Temp1234",
            "nueva_password": "MiClaveSegura2026",
            "confirmacion_password": "MiClaveSegura2026",
            "dispositivo_identificador": "pc-casa",
        },
    )

    assert resp.status_code == 409
    assert resp.get_json()["code"] == "PASSWORD_INICIAL_YA_CAMBIADA"


def test_tc06_bloquea_rutas_protegidas_mientras_debe_cambiar_password(app, client, session):
    usuario = _crear_paciente_inicial(session, debe_cambiar_password=True)
    token_inicial = _login_primer_ingreso(client, usuario.email, "Temp1234")

    resp_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_inicial}"},
    )
    assert resp_me.status_code == 403
    assert resp_me.get_json()["code"] == "DEBE_CAMBIAR_PASSWORD_INICIAL"

    # Incluso con un token de acceso completo, el flag en BD bloquea el ingreso
    token_completo = emitir_token(
        app.config["SECRET_KEY"],
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=600,
    )
    resp_me_bd = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_completo}"},
    )
    assert resp_me_bd.status_code == 403
    assert resp_me_bd.get_json()["code"] == "DEBE_CAMBIAR_PASSWORD_INICIAL"


def test_tc07_doble_envio_el_segundo_retorna_409(client, session):
    usuario = _crear_paciente_inicial(session)
    token_inicial = _login_primer_ingreso(client, usuario.email, "Temp1234")
    payload = {
        "password_inicial": "Temp1234",
        "nueva_password": "MiClaveSegura2026",
        "confirmacion_password": "MiClaveSegura2026",
        "dispositivo_identificador": "pc-casa",
    }

    primero = client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token_inicial}"},
        json=payload,
    )
    segundo = client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token_inicial}"},
        json=payload,
    )

    assert primero.status_code == 200
    assert segundo.status_code == 409
    assert segundo.get_json()["code"] == "PASSWORD_INICIAL_YA_CAMBIADA"


def test_sin_token_retorna_401(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "NO_AUTENTICADO"
