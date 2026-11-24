"""Tests de aceptacion para Escenario 18: Gestionar informacion familiar."""
import base64

from sqlalchemy import select
from src.core.models import (
    Familiar,
    Medico,
    Paciente,
    Patologia,
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


def _seed_paciente(app, session) -> tuple[str, Paciente, Sintoma]:
    medico_user = Usuario(
        email="dr.fam@hospital.org",
        password_hash=hashear_password("Medico123!"),
        rol=Rol.MEDICO,
        nombre="Laura",
        apellido="Mendez",
        telefono="2214009988",
        debe_cambiar_password=False,
    )
    pac_user = Usuario(
        email="pac.fam@example.com",
        password_hash=hashear_password("ClaveTemp1"),
        rol=Rol.PACIENTE,
        nombre="Sofia",
        apellido="Gomez",
        telefono="2215001122",
        debe_cambiar_password=True,
    )
    session.add_all([medico_user, pac_user])
    session.flush()

    medico = Medico(usuario_id=medico_user.id, matricula="MP-8899")
    pat = Patologia(nombre="Fabry", descripcion="Enfermedad de Fabry")
    sintoma = Sintoma(snomed_id="25064002", descripcion="Cefalea")
    session.add_all([medico, pat, sintoma])
    session.flush()

    from datetime import date

    paciente = Paciente(
        usuario_id=pac_user.id,
        medico_id=medico.id,
        dni="38111222",
        fecha_nacimiento=date(1998, 3, 15),
        diagnostico_presuntivo_id=pat.id,
        historia_clinica="Historia clinica inicial.",
        tipo_sospecha="familiar",
    )
    session.add(paciente)
    session.commit()

    token = emitir_token(
        app.config["SECRET_KEY"],
        usuario_id=medico_user.id,
        rol=Rol.MEDICO.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return token, paciente, sintoma


def test_e18_actualizar_familiares_y_ver_familiograma(app, client, session, monkeypatch, tmp_path):
    token, paciente, sintoma = _seed_paciente(app, session)
    monkeypatch.setattr(paciente_service, "_STORAGE_FAMILIOGRAMAS", tmp_path)

    class _FakeFamiliograma:
        def __init__(self, *args, **kwargs):
            pass

        def generar_familiograma(self, personas):
            b64 = base64.b64encode(b"<svg><text>OK</text></svg>").decode("utf-8")
            return {"advertencias": [], "imagen": {"tipo": "image/svg+xml", "base64": b64}}

        def guardar_svg(self, b64, destino):
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(base64.b64decode(b64))
            return destino

    monkeypatch.setattr(paciente_service, "FamiliogramaClient", _FakeFamiliograma)

    resp = client.put(
        f"/api/v1/pacientes/{paciente.id}/familiares",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "familiares": [
                {
                    "nombre": "Carlos Gomez",
                    "parentesco": "padre",
                    "diagnostico_previo": "Fabry",
                    "sintomas_snomed_ids": [sintoma.snomed_id],
                }
            ]
        },
    )

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["familiograma_generado"] is True
    assert len(data["familiares"]) == 1
    assert data["familiares"][0]["sintomas"][0]["snomed_id"] == "25064002"

    # Verifica que el endpoint de visualizacion devuelva el SVG
    resp_svg = client.get(
        f"/api/v1/pacientes/{paciente.id}/familiograma",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_svg.status_code == 200
    assert resp_svg.mimetype == "image/svg+xml"


def test_e18_lista_vacia_limpia_familiares_y_familiograma(app, client, session, monkeypatch):
    token, paciente, _ = _seed_paciente(app, session)

    def _no_llamar(*args, **kwargs):
        raise AssertionError("No debe invocar FamiliogramaClient con lista vacia")

    monkeypatch.setattr(paciente_service, "FamiliogramaClient", _no_llamar)

    resp = client.put(
        f"/api/v1/pacientes/{paciente.id}/familiares",
        headers={"Authorization": f"Bearer {token}"},
        json={"familiares": []},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["familiograma_generado"] is False
    assert session.scalars(select(Familiar)).all() == []


def test_e18_sintoma_inexistente_rechaza_400(app, client, session):
    token, paciente, _ = _seed_paciente(app, session)

    resp = client.put(
        f"/api/v1/pacientes/{paciente.id}/familiares",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "familiares": [
                {
                    "nombre": "Carlos Gomez",
                    "parentesco": "padre",
                    "sintomas_snomed_ids": ["999999999"],
                }
            ]
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "DATOS_FAMILIARES_INVALIDOS"