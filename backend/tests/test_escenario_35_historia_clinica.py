"""Tests de aceptacion para Escenario 35: Grabar la historia clinica."""
from datetime import date
from io import BytesIO

from src.core.models import Medico, Paciente, Patologia, Rol, Usuario
from src.core.services import paciente_service
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)


def _seed_e35(app, session):
    med_user = Usuario(
        email="dr.e35@hospital.org",
        password_hash=hashear_password("Medico123!"),
        rol=Rol.MEDICO,
        nombre="Sofia",
        apellido="Castro",
        telefono="2214007788",
        debe_cambiar_password=False,
    )
    pac_user = Usuario(
        email="pac.e35@example.com",
        password_hash=hashear_password("ClaveTemp1"),
        rol=Rol.PACIENTE,
        nombre="Tomas",
        apellido="Ruiz",
        telefono="2215007788",
        debe_cambiar_password=True,
    )
    session.add_all([med_user, pac_user])
    session.flush()

    medico = Medico(usuario_id=med_user.id, matricula="MP-3500")
    pat = Patologia(nombre="Fabry", descripcion="Fabry")
    session.add_all([medico, pat])
    session.flush()

    paciente = Paciente(
        usuario_id=pac_user.id,
        medico_id=medico.id,
        dni="41222333",
        fecha_nacimiento=date(1996, 2, 20),
        diagnostico_presuntivo_id=pat.id,
        historia_clinica="Texto previo.",
        tipo_sospecha="clinica",
    )
    session.add(paciente)
    session.commit()

    token = emitir_token(
        app.config["SECRET_KEY"],
        usuario_id=med_user.id,
        rol=Rol.MEDICO.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return token, paciente


def test_e35_audio_vacio_rechaza_422(app, client, session):
    token, _ = _seed_e35(app, session)
    resp = client.post(
        "/api/v1/pacientes/historia-clinica/transcribir",
        headers={"Authorization": f"Bearer {token}"},
        data={"audio": (BytesIO(b""), "vacio.webm", "audio/webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "AUDIO_VACIO"


def test_e35_formato_no_soportado_rechaza_415(app, client, session):
    token, _ = _seed_e35(app, session)
    resp = client.post(
        "/api/v1/pacientes/historia-clinica/transcribir",
        headers={"Authorization": f"Bearer {token}"},
        data={"audio": (BytesIO(b"%PDF-1.4"), "doc.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 415
    assert resp.get_json()["code"] == "FORMATO_AUDIO_NO_SOPORTADO"


def test_e35_transcribir_para_alta_sin_paciente_id(app, client, session, monkeypatch):
    token, _ = _seed_e35(app, session)

    class _FakeTranscriptor:
        def transcribir(self, **kwargs):
            return "Paciente con acroparestesias desde la infancia."

    monkeypatch.setattr(paciente_service, "TranscriptorClient", _FakeTranscriptor)

    resp = client.post(
        "/api/v1/pacientes/historia-clinica/transcribir",
        headers={"Authorization": f"Bearer {token}"},
        data={"audio": (BytesIO(b"fake-audio-bytes"), "nota.webm", "audio/webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["guardado_en_bd"] is False
    assert "acroparestesias" in data["historia_clinica"]


def test_e35_transcribir_y_guardar_en_paciente_existente(app, client, session, monkeypatch):
    token, paciente = _seed_e35(app, session)

    class _FakeTranscriptor:
        def transcribir(self, **kwargs):
            return "Historia clinica actualizada por voz."

    monkeypatch.setattr(paciente_service, "TranscriptorClient", _FakeTranscriptor)

    resp = client.post(
        "/api/v1/pacientes/historia-clinica/transcribir",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "audio": (BytesIO(b"fake-audio-bytes"), "nota.webm", "audio/webm"),
            "paciente_id": str(paciente.id),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["guardado_en_bd"] is True

    session.refresh(paciente)
    assert paciente.historia_clinica == "Historia clinica actualizada por voz."


def test_e35_patch_historia_clinica_directa(app, client, session):
    token, paciente = _seed_e35(app, session)
    resp = client.patch(
        f"/api/v1/pacientes/{paciente.id}/historia-clinica",
        headers={"Authorization": f"Bearer {token}"},
        json={"historia_clinica": "Resumen dictado desde el navegador."},
    )
    assert resp.status_code == 200
    session.refresh(paciente)
    assert paciente.historia_clinica == "Resumen dictado desde el navegador."