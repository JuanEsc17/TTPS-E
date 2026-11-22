"""Tests de aceptacion para Escenario 26: Verificar el ingreso desde una maquina nueva."""
import json
import re
from datetime import timedelta

import httpx
import jwt
import pytest
from sqlalchemy import select
from src.clients import EmailClient
from src.core.models import CodigoVerificacion, DispositivoConocido, Rol, Usuario
from src.core.repos import usuario_repo
from src.core.services.auth_service import RUTA_INICIO_POR_ROL
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    hashear_password,
    sha256_hex,
)


def _crear_usuario(session, *, email: str = "bio@lab.org", rol: Rol = Rol.BIOINFORMATICO) -> Usuario:
    usuario = Usuario(
        email=email,
        password_hash=hashear_password("Clave1234"),
        rol=rol,
        nombre="Ariadna",
        apellido="Guarino",
        telefono="2215000003",
        debe_cambiar_password=False,
    )
    session.add(usuario)
    session.commit()
    return usuario


def _mock_email_y_capturar_codigos(app) -> list[str]:
    codigos_enviados: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.read().decode("utf-8"))
        match = re.search(r"\b(\d{6})\b", cuerpo.get("mensaje", ""))
        if match:
            codigos_enviados.append(match.group(1))
        return httpx.Response(202, json={"id": "aviso-2fa", "estado": "pendiente", "creado": True})

    app.extensions["email_client"] = EmailClient(
        base_url="https://mail.mock.test",
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return codigos_enviados


def _iniciar_desafio(app, client, email: str, dispositivo: str = "notebook-nueva") -> tuple[str, str]:
    codigos = _mock_email_y_capturar_codigos(app)
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "Clave1234",
            "dispositivo_identificador": dispositivo,
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["estado_login"] == "REQUIERE_VERIFICACION_DISPOSITIVO"
    assert len(codigos) == 1
    return body["challenge_token"], codigos[0]


def test_tc01_verificar_dispositivo_nuevo_ok_y_proximo_login_directo(app, client, session):
    usuario = _crear_usuario(session)
    challenge_token, codigo_mail = _iniciar_desafio(app, client, usuario.email, "pc-casa")

    resp = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"codigo": f" {codigo_mail} ", "dispositivo_identificador": "pc-casa"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["estado_login"] == "AUTENTICADO"
    assert body["dispositivo_verificado"] is True
    assert body["ruta_inicio"] == RUTA_INICIO_POR_ROL[Rol.BIOINFORMATICO]

    claims = jwt.decode(body["access_token"], app.config["SECRET_KEY"], algorithms=["HS256"])
    assert claims["scope"] == SCOPE_ACCESO_COMPLETO

    registro = session.scalar(select(CodigoVerificacion).where(CodigoVerificacion.usuario_id == usuario.id))
    assert registro is not None and registro.usado is True

    dispositivos = session.scalars(
        select(DispositivoConocido).where(DispositivoConocido.usuario_id == usuario.id)
    ).all()
    assert len(dispositivos) == 1
    assert dispositivos[0].identificador == sha256_hex("pc-casa")

    # Proximo login desde la misma maquina entra directo sin pedir codigo nuevo
    resp_next = client.post(
        "/api/v1/auth/login",
        json={"email": usuario.email, "password": "Clave1234", "dispositivo_identificador": "pc-casa"},
    )
    assert resp_next.status_code == 200
    assert resp_next.get_json()["estado_login"] == "AUTENTICADO"


def test_tc02_codigo_incorrecto_retorna_401_sin_quemar_codigo(app, client, session):
    usuario = _crear_usuario(session)
    challenge_token, codigo_mail = _iniciar_desafio(app, client, usuario.email, "pc-casa")
    codigo_erroneo = "000000" if codigo_mail != "000000" else "999999"

    resp_mal = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"codigo": codigo_erroneo, "dispositivo_identificador": "pc-casa"},
    )
    assert resp_mal.status_code == 401
    assert resp_mal.get_json()["code"] == "CODIGO_VERIFICACION_INCORRECTO"

    # Todavia puede reintentar con el codigo correcto
    resp_ok = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"codigo": codigo_mail, "dispositivo_identificador": "pc-casa"},
    )
    assert resp_ok.status_code == 200


def test_tc03_codigo_expirado_retorna_410(app, client, session):
    usuario = _crear_usuario(session)
    challenge_token, codigo_mail = _iniciar_desafio(app, client, usuario.email, "pc-casa")

    registro = session.scalar(select(CodigoVerificacion).where(CodigoVerificacion.usuario_id == usuario.id))
    assert registro is not None
    registro.expira_en = usuario_repo.ahora_utc() - timedelta(minutes=1)
    session.commit()

    resp = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"codigo": codigo_mail, "dispositivo_identificador": "pc-casa"},
    )
    assert resp.status_code == 410
    assert resp.get_json()["code"] == "CODIGO_EXPIRADO"


def test_tc04_codigo_ya_usado_retorna_409(app, client, session):
    usuario = _crear_usuario(session)
    challenge_token, codigo_mail = _iniciar_desafio(app, client, usuario.email, "pc-casa")

    primero = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"codigo": codigo_mail, "dispositivo_identificador": "pc-casa"},
    )
    segundo = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"codigo": codigo_mail, "dispositivo_identificador": "pc-casa"},
    )

    assert primero.status_code == 200
    assert segundo.status_code == 409
    assert segundo.get_json()["code"] == "CODIGO_YA_UTILIZADO"


def test_tc05_canje_desde_otro_dispositivo_retorna_401(app, client, session):
    usuario = _crear_usuario(session)
    challenge_token, codigo_mail = _iniciar_desafio(app, client, usuario.email, "pc-origen")

    resp = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"codigo": codigo_mail, "dispositivo_identificador": "pc-atacante"},
    )

    assert resp.status_code == 401
    assert resp.get_json()["code"] == "CODIGO_VERIFICACION_INCORRECTO"


def test_tc06_challenge_token_bloqueado_en_rutas_protegidas(app, client, session):
    usuario = _crear_usuario(session)
    challenge_token, _ = _iniciar_desafio(app, client, usuario.email)

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {challenge_token}"})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "DISPOSITIVO_NO_VERIFICADO"


@pytest.mark.parametrize("codigo_invalido", ["12345", "1234567", "abc123", ""])
def test_formato_codigo_invalido_retorna_400(app, client, session, codigo_invalido):
    usuario = _crear_usuario(session)
    challenge_token, _ = _iniciar_desafio(app, client, usuario.email)

    resp = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"codigo": codigo_invalido, "dispositivo_identificador": "notebook-nueva"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "DATOS_INVALIDOS"


def test_reenviar_codigo_genera_nuevo_e_invalida_anterior(app, client, session):
    usuario = _crear_usuario(session)
    challenge_token, codigo_1 = _iniciar_desafio(app, client, usuario.email, "pc-casa")

    codigos_reenvio = _mock_email_y_capturar_codigos(app)
    resp_reenvio = client.post(
        "/api/v1/auth/reenviar-codigo-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"dispositivo_identificador": "pc-casa"},
    )
    assert resp_reenvio.status_code == 200
    assert len(codigos_reenvio) == 1
    codigo_2 = codigos_reenvio[0]
    nuevo_token = resp_reenvio.get_json()["challenge_token"]

    if codigo_1 != codigo_2:
        resp_viejo = client.post(
            "/api/v1/auth/verificar-dispositivo",
            headers={"Authorization": f"Bearer {nuevo_token}"},
            json={"codigo": codigo_1, "dispositivo_identificador": "pc-casa"},
        )
        assert resp_viejo.status_code == 401

    resp_nuevo = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {nuevo_token}"},
        json={"codigo": codigo_2, "dispositivo_identificador": "pc-casa"},
    )
    assert resp_nuevo.status_code == 200


@pytest.mark.parametrize("rol", list(Rol))
def test_tc08_verificacion_dispositivo_todos_los_roles(app, client, session, rol):
    usuario = _crear_usuario(session, email=f"{rol.value}@lab.org", rol=rol)
    challenge_token, codigo = _iniciar_desafio(app, client, usuario.email, f"equipo-{rol.value}")

    resp = client.post(
        "/api/v1/auth/verificar-dispositivo",
        headers={"Authorization": f"Bearer {challenge_token}"},
        json={"codigo": codigo, "dispositivo_identificador": f"equipo-{rol.value}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["ruta_inicio"] == RUTA_INICIO_POR_ROL[rol]
