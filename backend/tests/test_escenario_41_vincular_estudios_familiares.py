"""Tests de aceptacion para Escenario 41: Vincular y consultar estudios de familiares."""
from datetime import date

from sqlalchemy import select
from src.core.models import (
    EstudioFamiliarVinculado,
    Medico,
    Patologia,
    PatologiaSintoma,
    Rol,
    Sintoma,
    Usuario,
)
from src.core.services import estudio_service, paciente_service
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)


def _seed_entorno_41(app, session):
    med_user = Usuario(
        email="dr.e41@hospital.org",
        password_hash=hashear_password("Medico123!"),
        rol=Rol.MEDICO,
        nombre="Elena",
        apellido="Paz",
        telefono="2214004141",
        debe_cambiar_password=False,
    )
    session.add(med_user)
    session.flush()
    session.add(Medico(usuario_id=med_user.id, matricula="MP-4100"))

    pat = Patologia(nombre="Fabry", descripcion="Fabry")
    cardinal = Sintoma(snomed_id="225566008", descripcion="Acroparestesia")
    session.add_all([pat, cardinal])
    session.flush()
    session.add(PatologiaSintoma(patologia_id=pat.id, sintoma_id=cardinal.id, es_cardinal=True))
    session.commit()

    token = emitir_token(
        app.config["SECRET_KEY"],
        usuario_id=med_user.id,
        rol=Rol.MEDICO.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return token, pat, cardinal


def test_e41_vinculacion_automatica_bidireccional_y_consulta(app, client, session, monkeypatch):
    token, pat, cardinal = _seed_entorno_41(app, session)

    class _FakeApigen:
        def __init__(self, *args, **kwargs):
            pass

        def obtener_genes_por_patologia(self, patologia):
            return ["GLA"]

    monkeypatch.setattr(estudio_service, "ApigenClient", _FakeApigen)
    monkeypatch.setattr(paciente_service, "_generar_svg_familiograma", lambda **kwargs: None)

    # 1. Alta paciente P1 declarando como familiar a hermano con DNI 30111222
    r_p1 = client.post(
        "/api/v1/pacientes",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "dni": "30000111",
            "nombre": "Ana",
            "apellido": "Gomez",
            "telefono": "2215000111",
            "email": "ana.e41@example.com",
            "fecha_nacimiento": "1992-01-10",
            "diagnostico_presuntivo_id": pat.id,
            "historia_clinica": "HC Ana.",
            "tipo_sospecha": "familiar",
            "sintomas_snomed_ids": [cardinal.snomed_id],
            "familiares": [
                {"parentesco": "hermano", "nombre": "Luis Gomez", "dni": "30111222"}
            ],
        },
    )
    assert r_p1.status_code == 201
    p1_id = r_p1.get_json()["data"]["paciente_id"]

    # Estudio E1 para P1
    r_e1 = client.post(
        "/api/v1/estudios",
        headers={"Authorization": f"Bearer {token}"},
        json={"paciente_id": p1_id, "patologia_sospechada_id": pat.id},
    )
    assert r_e1.status_code == 201
    e1_id = r_e1.get_json()["data"]["estudio_id"]

    # 2. Alta paciente P2 con DNI 30111222 (sin familiares propios) y estudio E2
    r_p2 = client.post(
        "/api/v1/pacientes",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "dni": "30111222",
            "nombre": "Luis",
            "apellido": "Gomez",
            "telefono": "2215000222",
            "email": "luis.e41@example.com",
            "fecha_nacimiento": date(1994, 6, 15).isoformat(),
            "diagnostico_presuntivo_id": pat.id,
            "historia_clinica": "HC Luis.",
            "tipo_sospecha": "familiar",
            "sintomas_snomed_ids": [cardinal.snomed_id],
            "sin_informacion_familiar": True,
            "familiares": [],
        },
    )
    assert r_p2.status_code == 201
    p2_id = r_p2.get_json()["data"]["paciente_id"]

    r_e2 = client.post(
        "/api/v1/estudios",
        headers={"Authorization": f"Bearer {token}"},
        json={"paciente_id": p2_id, "patologia_sospechada_id": pat.id},
    )
    assert r_e2.status_code == 201
    e2_id = r_e2.get_json()["data"]["estudio_id"]

    # Verifica vinculos bidireccionales en BD
    vinculos = session.scalars(select(EstudioFamiliarVinculado)).all()
    assert len(vinculos) == 2

    # 3. Medico consulta vinculados desde E1 y navega al detalle de E2
    r_list = client.get(
        f"/api/v1/estudios/{e1_id}/familiares-vinculados",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_list.status_code == 200
    assert r_list.get_json()["data"][0]["estudio_relacionado_id"] == e2_id

    r_det = client.get(
        f"/api/v1/estudios/{e1_id}/familiares-vinculados/{e2_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_det.status_code == 200
    assert r_det.get_json()["data"]["estudio_id"] == e2_id
    assert r_det.get_json()["data"]["genes"][0]["simbolo"] == "GLA"