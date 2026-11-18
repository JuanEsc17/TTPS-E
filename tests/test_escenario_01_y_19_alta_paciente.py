"""Tests de aceptacion para Escenarios 1 y 19: Alta de paciente con y sin familiares."""
import base64

from sqlalchemy import select
from src.core.models import (
    Familiar,
    Medico,
    Paciente,
    Patologia,
    PatologiaSintoma,
    Rol,
    Sintoma,
    Usuario,
)
from src.core.services import paciente_service
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)


def _preparar_entorno(app, session) -> tuple[str, Patologia, Sintoma, Sintoma]:
    medico_user = Usuario(
        email="dr.alta@hospital.org",
        password_hash=hashear_password("Medico123!"),
        rol=Rol.MEDICO,
        nombre="Carlos",
        apellido="Ruiz",
        telefono="2214002233",
        debe_cambiar_password=False,
    )
    session.add(medico_user)
    session.flush()
    session.add(Medico(usuario_id=medico_user.id, matricula="MP-7788"))

    pat = Patologia(nombre="Fabry", descripcion="Enfermedad de Fabry")
    cardinal = Sintoma(snomed_id="225566008", descripcion="Acroparestesia")
    secundario = Sintoma(snomed_id="4556007", descripcion="Hipohidrosis")
    session.add_all([pat, cardinal, secundario])
    session.flush()
    session.add_all(
        [
            PatologiaSintoma(patologia_id=pat.id, sintoma_id=cardinal.id, es_cardinal=True),
            PatologiaSintoma(patologia_id=pat.id, sintoma_id=secundario.id, es_cardinal=False),
        ]
    )
    session.commit()

    token = emitir_token(
        app.config["SECRET_KEY"],
        usuario_id=medico_user.id,
        rol=Rol.MEDICO.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return token, pat, cardinal, secundario


def _payload_base(pat_id: int, sintomas_ids: list[str]) -> dict:
    return {
        "dni": "40123456",
        "nombre": "Juan",
        "apellido": "Perez",
        "telefono": "2215551122",
        "email": "juan.perez@example.com",
        "fecha_nacimiento": "1995-04-12",
        "diagnostico_presuntivo_id": pat_id,
        "historia_clinica": "Paciente con dolor neuropatico en extremidades.",
        "tipo_sospecha": "clinica",
        "sintomas_snomed_ids": sintomas_ids,
    }


def test_e1_alta_paciente_con_familiares_genera_familiograma(app, client, session, monkeypatch, tmp_path):
    token, pat, cardinal, _ = _preparar_entorno(app, session)
    monkeypatch.setattr(paciente_service, "_STORAGE_FAMILIOGRAMAS", tmp_path)

    class _FakeFamiliograma:
        def __init__(self, *args, **kwargs):
            pass

        def generar_familiograma(self, personas):
            svg_b64 = base64.b64encode(b"<svg></svg>").decode("utf-8")
            return {"advertencias": [], "imagen": {"tipo": "image/svg+xml", "base64": svg_b64}}

        def guardar_svg(self, b64, destino):
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(base64.b64decode(b64))
            return destino

    class _FakeEmail:
        def __init__(self, *args, **kwargs):
            pass

        def enviar_aviso(self, **kwargs):
            return {"ok": True}

    monkeypatch.setattr(paciente_service, "FamiliogramaClient", _FakeFamiliograma)
    monkeypatch.setattr(paciente_service, "EmailClient", _FakeEmail)

    payload = _payload_base(pat.id, [cardinal.snomed_id])
    payload["familiares"] = [
        {"parentesco": "padre", "nombre": "Roberto Perez", "diagnostico_previo": "Fabry"}
    ]

    resp = client.post("/api/v1/pacientes", headers={"Authorization": f"Bearer {token}"}, json=payload)

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["debe_cambiar_password"] is True
    assert data["familiograma_pdf_path"] is not None
    assert len(session.scalars(select(Familiar)).all()) == 1


def test_e19_alta_paciente_sin_informacion_familiar(app, client, session, monkeypatch):
    token, pat, cardinal, _ = _preparar_entorno(app, session)

    def _no_debe_llamarse(*args, **kwargs):
        raise AssertionError("No debe invocar FamiliogramaClient en E19")

    monkeypatch.setattr(paciente_service, "FamiliogramaClient", _no_debe_llamarse)
    monkeypatch.setattr(
        paciente_service,
        "EmailClient",
        type("_FakeMail", (), {"__init__": lambda *a, **k: None, "enviar_aviso": lambda *a, **k: {"ok": True}}),
    )

    payload = _payload_base(pat.id, [cardinal.snomed_id])
    payload["sin_informacion_familiar"] = True
    payload["familiares"] = []

    resp = client.post("/api/v1/pacientes", headers={"Authorization": f"Bearer {token}"}, json=payload)

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["familiograma_pdf_path"] is None
    assert session.scalars(select(Familiar)).all() == []


def test_e1_menor_sin_responsable_falla_400(app, client, session):
    token, pat, cardinal, _ = _preparar_entorno(app, session)
    payload = _payload_base(pat.id, [cardinal.snomed_id])
    payload["fecha_nacimiento"] = "2018-05-10"

    resp = client.post("/api/v1/pacientes", headers={"Authorization": f"Bearer {token}"}, json=payload)

    assert resp.status_code == 400
    assert resp.get_json()["code"] == "DATOS_PACIENTE_INVALIDOS"


def test_e1_sintomas_incompatibles_rechaza_422(app, client, session):
    token, pat, _, secundario = _preparar_entorno(app, session)
    # Solo 1 sintoma secundario sin cardinal no alcanza
    payload = _payload_base(pat.id, [secundario.snomed_id])

    resp = client.post("/api/v1/pacientes", headers={"Authorization": f"Bearer {token}"}, json=payload)

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "SINTOMAS_INCOMPATIBLES_PATOLOGIA"
    assert session.scalars(select(Paciente)).all() == []