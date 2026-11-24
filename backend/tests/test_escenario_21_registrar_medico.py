"""Tests de aceptacion para Escenario 21: Registrar un medico."""
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from src.core.models import Especialidad, Medico, MedicoEspecialidad, Rol, Usuario


def _seed_especialidades(session) -> list[Especialidad]:
    e1 = Especialidad(nombre="Genetica Medica")
    e2 = Especialidad(nombre="Neurologia")
    e3 = Especialidad(nombre="Pediatria")
    session.add_all([e1, e2, e3])
    session.commit()
    return [e1, e2, e3]


def _payload_valido(especialidades_ids: list[int]) -> dict:
    return {
        "nombre": "Martin",
        "apellido": "Gomez",
        "telefono": "+5492214448899",
        "email": "martin.gomez@hospital.org.ar",
        "password": "DrGomez2026!Secure",
        "matricula": "MP-114523",
        "especialidades_ids": especialidades_ids,
        "dispositivo_identificador": "fp_sha256_medico_workstation_01",
    }


def test_listar_especialidades(client, session):
    _seed_especialidades(session)

    resp = client.get("/api/v1/especialidades")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert [e["nombre"] for e in body["data"]] == [
        "Genetica Medica",
        "Neurologia",
        "Pediatria",
    ]


def test_tc01_registro_medico_valido(client, session):
    e1, _, e3 = _seed_especialidades(session)

    resp = client.post(
        "/api/v1/medicos/registro",
        json=_payload_valido([e1.id, e3.id]),
    )

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["rol"] == "medico"
    assert data["matricula"] == "MP-114523"
    assert len(data["especialidades"]) == 2

    usuario = session.scalar(select(Usuario).where(Usuario.email == "martin.gomez@hospital.org.ar"))
    assert usuario is not None
    assert usuario.rol == Rol.MEDICO
    assert usuario.debe_cambiar_password is False

    medico = session.scalar(select(Medico).where(Medico.usuario_id == usuario.id))
    assert medico is not None
    vinculos = session.scalars(
        select(MedicoEspecialidad).where(MedicoEspecialidad.medico_id == medico.id)
    ).all()
    assert len(vinculos) == 2


def test_tc02_registro_sin_especialidades(client, session):
    _seed_especialidades(session)

    resp = client.post("/api/v1/medicos/registro", json=_payload_valido([]))

    assert resp.status_code == 400
    assert resp.get_json()["code"] == "DATOS_MEDICO_INVALIDOS"
    assert session.scalars(select(Usuario)).all() == []


def test_tc03_especialidad_inexistente(client, session):
    _seed_especialidades(session)

    resp = client.post("/api/v1/medicos/registro", json=_payload_valido([9999]))

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "ESPECIALIDAD_INEXISTENTE"
    assert session.scalars(select(Medico)).all() == []


def test_tc04_matricula_duplicada(client, session):
    e1, _, _ = _seed_especialidades(session)
    assert client.post("/api/v1/medicos/registro", json=_payload_valido([e1.id])).status_code == 201

    otro = _payload_valido([e1.id])
    otro["email"] = "otro.medico@hospital.org.ar"
    resp = client.post("/api/v1/medicos/registro", json=otro)

    assert resp.status_code == 409
    assert resp.get_json()["code"] == "MATRICULA_YA_REGISTRADA"


def test_tc05_email_duplicado(client, session):
    e1, _, _ = _seed_especialidades(session)
    assert client.post("/api/v1/medicos/registro", json=_payload_valido([e1.id])).status_code == 201

    otro = _payload_valido([e1.id])
    otro["matricula"] = "MP-999999"
    resp = client.post("/api/v1/medicos/registro", json=otro)

    assert resp.status_code == 409
    assert resp.get_json()["code"] == "EMAIL_YA_REGISTRADO"


def test_tc06_ignora_rol_inyectado_en_payload(client, session):
    e1, _, _ = _seed_especialidades(session)
    payload = _payload_valido([e1.id])
    payload["rol"] = "gerente_medico"

    resp = client.post("/api/v1/medicos/registro", json=payload)

    assert resp.status_code == 201
    assert resp.get_json()["data"]["rol"] == "medico"


def test_tc07_rollback_si_falla_transaccion(client, session, monkeypatch):
    e1, _, _ = _seed_especialidades(session)

    def _fallar_commit():
        raise SQLAlchemyError("Fallo simulado en commit")

    monkeypatch.setattr(session, "commit", _fallar_commit)

    resp = client.post("/api/v1/medicos/registro", json=_payload_valido([e1.id]))

    assert resp.status_code == 503
    assert resp.get_json()["code"] == "ERROR_BASE_DATOS"
    assert session.scalars(select(Usuario)).all() == []
    assert session.scalars(select(Medico)).all() == []