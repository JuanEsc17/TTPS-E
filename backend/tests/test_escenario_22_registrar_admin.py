"""Tests de aceptacion para Escenario 22: Registrar un administrativo."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from src.core.models import Rol, Usuario
from src.core.repos import usuario_repo
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)

URL = "/api/v1/admin/administrativos"
EMAIL_ADMINISTRATIVO = "carolina.suarez@labcentral.com.ar"
PASSWORD = "AdminLab2026!Secure"


def _crear_usuario(session, rol, email="admin@exoma.com"):
    """ Crea un usuario con el rol y email especificados, y lo guarda en la base de datos. """
    u = Usuario(email=email, password_hash=hashear_password("Clave1234"), rol=rol,
                nombre="X", apellido="Y", telefono="1", debe_cambiar_password=False)
    session.add(u)
    session.commit()
    return u


def _headers(app, usuario):
    """ Genera los headers de autenticacion para un usuario dado. """
    token = emitir_token(str(app.config["SECRET_KEY"]), usuario_id=usuario.id,
                         rol=usuario.rol.value, scope=SCOPE_ACCESO_COMPLETO, ttl_segundos=3600)
    return {"Authorization": f"Bearer {token}"}


def _payload(**cambios):
    """ Genera un payload para crear un administrativo, con la posibilidad de cambiar campos.
    """
    base = {"nombre": "Carolina", "apellido": "Suárez", "telefono": "+5492216001122",
            "email": EMAIL_ADMINISTRATIVO, "password": PASSWORD}
    return {**base, **cambios}


def _buscar_usuario(session, email=EMAIL_ADMINISTRATIVO):
    """ Busca un usuario por email en la base de datos. """
    return session.scalar(select(Usuario).where(Usuario.email == email))


def _contar_usuarios(session):
    """ Cuenta la cantidad de usuarios en la base de datos. """
    return session.scalar(select(func.count()).select_from(Usuario))


def test_tc01_alta_administrativo(app, client, session):
    """ Se puede crear un administrativo con todos los campos requeridos. """
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)

    resp = client.post(URL, json=_payload(), headers=_headers(app, admin))

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["ok"] is True
    data = body["data"]
    assert data["rol"] == Rol.ADMINISTRATIVO.value
    assert data["email"] == EMAIL_ADMINISTRATIVO
    assert data["debe_cambiar_password"] is False
    assert "password" not in data and "password_hash" not in data

    usuario = _buscar_usuario(session)
    assert usuario is not None
    assert usuario.rol == Rol.ADMINISTRATIVO
    assert usuario.debe_cambiar_password is False
    assert usuario.password_hash != PASSWORD


def test_tc01b_normaliza_email_y_espacios(app, client, session):
    """ El email se guarda en minusculas y se eliminan espacios al inicio y al final de los campos. """
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    payload = _payload(email=EMAIL_ADMINISTRATIVO.upper(), nombre="  Carolina  ")

    resp = client.post(URL, json=payload, headers=_headers(app, admin))

    assert resp.status_code == 201
    usuario = _buscar_usuario(session)
    assert usuario is not None
    assert usuario.nombre == "Carolina"


@pytest.mark.parametrize(
    "rol", [Rol.ADMINISTRATIVO, Rol.GERENTE_MEDICO, Rol.MEDICO, Rol.PACIENTE]
)
def test_tc02_rechaza_usuario_sin_rol_admin_general(app, client, session, rol):
    """ Solo un usuario con rol ADMIN_GENERAL puede crear un administrativo. """
    no_admin = _crear_usuario(session, rol, email="otro@exoma.com")

    resp = client.post(URL, json=_payload(), headers=_headers(app, no_admin))

    assert resp.status_code == 403
    assert resp.get_json()["code"] == "SOLO_ADMIN_GENERAL"
    assert _buscar_usuario(session) is None


def test_tc03_rechaza_sin_sesion(client, session):
    """ No se puede crear un administrativo sin estar logueado. """
    resp = client.post(URL, json=_payload())

    assert resp.status_code == 401
    assert _buscar_usuario(session) is None


@pytest.mark.parametrize("cambio", [
    {"nombre": ""},
    {"nombre": "   "},
    {"apellido": ""},
    {"telefono": ""},
    {"nombre": "a" * 101},
    {"apellido": "a" * 101},
    {"telefono": "1" * 31},
    {"email": "a" * 250 + "@x.com"},
])
def test_tc04_campos_vacios_o_largos(app, client, session, cambio):
    """ Campos vacios o demasiado largos. """
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)

    resp = client.post(URL, json=_payload(**cambio), headers=_headers(app, admin))

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "DATOS_ENTRADA_INVALIDOS"
    assert _contar_usuarios(session) == 1  # solo el admin


@pytest.mark.parametrize("campo", ["nombre", "apellido", "telefono", "email", "password"])
def test_tc04b_campo_faltante(app, client, session, campo):
    """ Omite un campo requerido en el payload. """
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    payload = {k: v for k, v in _payload().items() if k != campo}

    resp = client.post(URL, json=payload, headers=_headers(app, admin))

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "DATOS_ENTRADA_INVALIDOS"
    assert _contar_usuarios(session) == 1


@pytest.mark.parametrize("cambio", [{"email": "correo-invalido"}, {"password": "123"}])
def test_tc05_email_o_password_invalidos(app, client, session, cambio):
    """ Email invalido o password que no cumple con la politica de seguridad. """
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)

    resp = client.post(URL, json=_payload(**cambio), headers=_headers(app, admin))

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "DATOS_ENTRADA_INVALIDOS"
    assert _contar_usuarios(session) == 1


def test_tc06_rechaza_email_duplicado_de_otro_rol(app, client, session):
    """ No se puede crear un administrativo con el mismo email que otro usuario de distinto rol. """
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    _crear_usuario(session, Rol.MEDICO, email=EMAIL_ADMINISTRATIVO)

    resp = client.post(URL, json=_payload(), headers=_headers(app, admin))

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "EMAIL_YA_REGISTRADO"
    assert body["retryable"] is False
    assert _contar_usuarios(session) == 2
    assert _buscar_usuario(session).rol == Rol.MEDICO


def test_tc07_colision_concurrente_integrity_error(app, client, session, monkeypatch):
    """Simula una colision concurrente de email, que pasa el check de existencia pero falla en el INSERT."""
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    _crear_usuario(session, Rol.MEDICO, email=EMAIL_ADMINISTRATIVO)
    # Simula la carrera: STEP 2 no ve el email, pero el INSERT viola UNIQUE.
    monkeypatch.setattr(usuario_repo, "buscar_por_email", lambda email: None)

    resp = client.post(URL, json=_payload(), headers=_headers(app, admin))

    assert resp.status_code == 409
    assert resp.get_json()["code"] == "EMAIL_YA_REGISTRADO"
    assert _contar_usuarios(session) == 2


def test_tc07b_rollback_si_falla_la_base(app, client, session, monkeypatch):
    """Simula un fallo de la base de datos en el commit, y verifica que no se persista el usuario."""
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    headers = _headers(app, admin)

    def _fallar_commit():
        raise SQLAlchemyError("Fallo simulado en commit")

    monkeypatch.setattr(session, "commit", _fallar_commit)

    resp = client.post(URL, json=_payload(), headers=headers)

    assert resp.status_code == 500
    body = resp.get_json()
    assert body["code"] == "DB_ERROR"
    assert body["retryable"] is True
    assert _buscar_usuario(session) is None


def test_tc08_no_se_puede_borrar_administrativo(app, client, session):
    """ No se puede borrar un usuario con rol administrativo. """
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    administrativo = _crear_usuario(session, Rol.ADMINISTRATIVO, email=EMAIL_ADMINISTRATIVO)

    resp = client.delete(f"{URL}/{administrativo.id}", headers=_headers(app, admin))

    assert resp.status_code in (403, 405)
    assert _buscar_usuario(session) is not None


def test_ignora_rol_inyectado_en_payload(app, client, session):
    """ El rol del usuario a crear siempre es ADMINISTRATIVO, aunque se intente inyectar otro. """
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)

    resp = client.post(URL, json=_payload(rol="admin_general"), headers=_headers(app, admin))

    assert resp.status_code == 201
    assert resp.get_json()["data"]["rol"] == Rol.ADMINISTRATIVO.value
    assert _buscar_usuario(session).rol == Rol.ADMINISTRATIVO