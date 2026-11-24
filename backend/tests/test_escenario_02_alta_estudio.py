"""Tests de aceptacion para Escenario 2: Dar de alta un estudio."""
from datetime import date

from sqlalchemy import select
from src.core.models import (
    Aviso,
    EstadoEstudio,
    Estudio,
    Medico,
    Paciente,
    Patologia,
    Rol,
    Usuario,
)
from src.core.services import estudio_service
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)


def _seed_estudio_env(app, session, *, fecha_nac: date, nombre_pat: str = "Fabry"):
    medico_user = Usuario(
        email="dr.estudio@hospital.org",
        password_hash=hashear_password("Medico123!"),
        rol=Rol.MEDICO,
        nombre="Marcos",
        apellido="Vega",
        telefono="2214003344",
        debe_cambiar_password=False,
    )
    pac_user = Usuario(
        email="pac.estudio@example.com",
        password_hash=hashear_password("ClaveTemp1"),
        rol=Rol.PACIENTE,
        nombre="Lucas",
        apellido="Diaz",
        telefono="2215003344",
        debe_cambiar_password=True,
    )
    admin_user = Usuario(
        email="admin.estudio@hospital.org",
        password_hash=hashear_password("Admin123!"),
        rol=Rol.ADMINISTRATIVO,
        nombre="Sofia",
        apellido="Admin",
        telefono="2214000000",
        debe_cambiar_password=False,
    )
    session.add_all([medico_user, pac_user, admin_user])
    session.flush()

    medico = Medico(usuario_id=medico_user.id, matricula="MP-3344")
    pat = Patologia(nombre=nombre_pat, descripcion="Patologia de prueba")
    session.add_all([medico, pat])
    session.flush()

    paciente = Paciente(
        usuario_id=pac_user.id,
        medico_id=medico.id,
        dni="39001122",
        fecha_nacimiento=fecha_nac,
        diagnostico_presuntivo_id=pat.id,
        historia_clinica="Historia clinica.",
        tipo_sospecha="clinica",
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
    return token, paciente, pat


def test_e2_alta_estudio_con_hallazgos_y_manuales(app, client, session, monkeypatch):
    token, paciente, pat = _seed_estudio_env(app, session, fecha_nac=date(1995, 5, 10))

    class _FakeApigen:
        def __init__(self, *args, **kwargs):
            pass

        def obtener_genes_por_patologia(self, patologia):
            return ["GLA"]

        def obtener_genes_hallazgos_secundarios(self):
            return [{"gen": "BRCA1", "condicion": "Cancer de mama"}]

    monkeypatch.setattr(estudio_service, "ApigenClient", _FakeApigen)

    resp = client.post(
        "/api/v1/estudios",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "paciente_id": paciente.id,
            "patologia_sospechada_id": pat.id,
            "quiere_hallazgos_secundarios": True,
            "genes_patologia_simbolos": ["GLA"],
            "genes_manuales_simbolos": ["IDUA"],
        },
    )

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["estado"] == EstadoEstudio.CREADO.value
    assert data["es_pompe_urgente"] is False
    assert data["cantidad_genes_total"] == 3
    # Verifica que se crearon avisos para administrativo y paciente
    assert len(session.scalars(select(Aviso)).all()) == 2


def test_e2_pompe_menor_4_meses_marca_urgente(app, client, session, monkeypatch):
    hoy = date.today()
    fecha_bebe = date(hoy.year, hoy.month, 1)
    token, paciente, pat = _seed_estudio_env(app, session, fecha_nac=fecha_bebe, nombre_pat="Pompe")

    class _FakeApigen:
        def __init__(self, *args, **kwargs):
            pass

        def obtener_genes_por_patologia(self, patologia):
            return ["GAA"]

    monkeypatch.setattr(estudio_service, "ApigenClient", _FakeApigen)

    resp = client.post(
        "/api/v1/estudios",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "paciente_id": paciente.id,
            "patologia_sospechada_id": pat.id,
            "quiere_hallazgos_secundarios": False,
        },
    )

    assert resp.status_code == 201
    assert resp.get_json()["data"]["es_pompe_urgente"] is True


def test_e2_lista_genes_vacia_rechaza_422(app, client, session, monkeypatch):
    token, paciente, pat = _seed_estudio_env(app, session, fecha_nac=date(1990, 1, 1))

    class _EmptyApigen:
        def __init__(self, *args, **kwargs):
            pass

        def obtener_genes_por_patologia(self, patologia):
            return []

    monkeypatch.setattr(estudio_service, "ApigenClient", _EmptyApigen)

    resp = client.post(
        "/api/v1/estudios",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "paciente_id": paciente.id,
            "patologia_sospechada_id": pat.id,
            "quiere_hallazgos_secundarios": False,
        },
    )

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "LISTA_GENES_VACIA"
    assert session.scalars(select(Estudio)).all() == []