import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from src.core.models import Especialidad, Medico, MedicoEspecialidad, Rol, Usuario
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)

URL = "/api/v1/admin/gerentes-medicos"
EMAIL_GERENTE = "laura.gomez@exoma.com"

def _seed_especialidades(session):              # crea 2 especialidades en la BD
    e1, e2 = Especialidad(nombre="Genetica Medica"), Especialidad(nombre="Pediatria")
    session.add_all([e1, e2]); session.commit()
    return e1, e2

def _crear_usuario(session, rol, email="admin@exoma.com"):   # crea un usuario cualquiera
    u = Usuario(email=email, password_hash=hashear_password("Clave1234"), rol=rol,
                nombre="X", apellido="Y", telefono="1", debe_cambiar_password=False)
    session.add(u); session.commit()
    return u

def _headers(app, usuario):                     # "inicia sesion" generando un token (igual que test_escenario_11)
    token = emitir_token(str(app.config["SECRET_KEY"]), usuario_id=usuario.id,
                         rol=usuario.rol.value, scope=SCOPE_ACCESO_COMPLETO, ttl_segundos=3600)
    return {"Authorization": f"Bearer {token}"}

def _payload(ids):
    return {"nombre": "Laura", "apellido": "Gómez", "telefono": "+5492214556677",
            "email": EMAIL_GERENTE, "password": "ClaveSegura2026!",
            "matricula": "MP-114589", "especialidades_ids": ids}

def _buscar_usuario(session, email=EMAIL_GERENTE):
    return session.scalar(select(Usuario).where(Usuario.email == email))

def _contar(session, modelo):
    return session.scalar(select(func.count()).select_from(modelo))


def test_tc01_alta_completa_gerente_medico(app, client, session):
    e1, e2 = _seed_especialidades(session)
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)

    resp = client.post(URL, json=_payload([e1.id, e2.id]), headers=_headers(app, admin))

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["rol"] == Rol.GERENTE_MEDICO.value
    assert {e["id"] for e in data["especialidades"]} == {e1.id, e2.id}

    usuario = _buscar_usuario(session)
    assert usuario is not None
    assert usuario.rol == Rol.GERENTE_MEDICO
    assert usuario.password_hash != "ClaveSegura2026!"

    medico = session.scalar(select(Medico).where(Medico.usuario_id == usuario.id))
    assert medico is not None
    assert medico.matricula == "MP-114589"
    assert _contar(session, MedicoEspecialidad) == 2


@pytest.mark.parametrize("rol", [Rol.GERENTE_MEDICO, Rol.MEDICO, Rol.ADMINISTRATIVO])
def test_tc02_rechaza_usuario_sin_rol_admin(app, client, session, rol):
    e1, _ = _seed_especialidades(session)
    no_admin = _crear_usuario(session, rol, email="otro@exoma.com")

    resp = client.post(URL, json=_payload([e1.id]), headers=_headers(app, no_admin))

    assert resp.status_code == 403
    assert resp.get_json()["code"] == "SOLO_ADMIN_GENERAL"
    assert _buscar_usuario(session) is None
    assert _contar(session, Medico) == 0


def test_tc03_rechaza_email_duplicado(app, client, session):
    e1, _ = _seed_especialidades(session)
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    _crear_usuario(session, Rol.ADMINISTRATIVO, email=EMAIL_GERENTE)

    resp = client.post(URL, json=_payload([e1.id]), headers=_headers(app, admin))

    assert resp.status_code == 409
    assert resp.get_json()["code"] == "EMAIL_YA_REGISTRADO"
    assert _contar(session, Medico) == 0


def test_tc04_rechaza_matricula_duplicada(app, client, session):
    e1, _ = _seed_especialidades(session)
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    assert client.post(URL, json=_payload([e1.id]), headers=_headers(app, admin)).status_code == 201

    otro = {**_payload([e1.id]), "email": "otro.gerente@exoma.com"}
    resp = client.post(URL, json=otro, headers=_headers(app, admin))

    assert resp.status_code == 409
    assert resp.get_json()["code"] == "MATRICULA_YA_REGISTRADA"
    assert _buscar_usuario(session, "otro.gerente@exoma.com") is None
    assert _contar(session, Medico) == 1


def test_tc05_rechaza_especialidad_inexistente(app, client, session):
    e1, _ = _seed_especialidades(session)
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)

    resp = client.post(URL, json=_payload([e1.id, 9999]), headers=_headers(app, admin))

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "ESPECIALIDAD_INEXISTENTE"
    assert _buscar_usuario(session) is None
    assert _contar(session, Medico) == 0


@pytest.mark.parametrize("cambio", [{"especialidades_ids": []}, {"matricula": ""}])
def test_tc06_rechaza_especialidades_vacias_o_campos_faltantes(app, client, session, cambio):
    e1, _ = _seed_especialidades(session)
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    payload = {**_payload([e1.id]), **cambio}

    resp = client.post(URL, json=payload, headers=_headers(app, admin))

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "DATOS_ENTRADA_INVALIDOS"
    assert _buscar_usuario(session) is None


def test_tc07_rollback_si_falla_transaccion(app, client, session, monkeypatch):
    e1, _ = _seed_especialidades(session)
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)   # se crea antes de romper commit
    headers = _headers(app, admin)

    def _fallar_commit():
        raise SQLAlchemyError("Fallo simulado en commit")

    monkeypatch.setattr(session, "commit", _fallar_commit)

    resp = client.post(URL, json=_payload([e1.id]), headers=headers)

    assert resp.status_code == 500
    assert resp.get_json()["code"] == "DB_ERROR"
    assert _buscar_usuario(session) is None
    assert _contar(session, Medico) == 0


def test_rechaza_telefono_con_formato_invalido(app, client, session):
    e1, _ = _seed_especialidades(session)
    admin = _crear_usuario(session, Rol.ADMIN_GENERAL)
    payload = {**_payload([e1.id]), "telefono": "hola"}

    resp = client.post(URL, json=payload, headers=_headers(app, admin))

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "DATOS_ENTRADA_INVALIDOS"
    assert _buscar_usuario(session) is None
