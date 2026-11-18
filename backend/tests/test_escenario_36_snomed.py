"""Tests de aceptacion para Escenario 36: Sintomas SNOMED y validacion clinica."""
from src.clients.exceptions import ClienteConexionError
from src.core.models import (
    Medico,
    Patologia,
    PatologiaSintoma,
    Rol,
    Sintoma,
    Usuario,
)
from src.core.services import clinica_service
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)


def _token_medico(app, session) -> str:
    usuario = Usuario(
        email="medico.snomed@hospital.org",
        password_hash=hashear_password("Medico123!"),
        rol=Rol.MEDICO,
        nombre="Ana",
        apellido="Lopez",
        telefono="2214001122",
        debe_cambiar_password=False,
    )
    session.add(usuario)
    session.flush()
    session.add(Medico(usuario_id=usuario.id, matricula="MP-5511"))
    session.commit()
    return emitir_token(
        app.config["SECRET_KEY"],
        usuario_id=usuario.id,
        rol=Rol.MEDICO.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )


def _seed_patologia(session) -> tuple[Patologia, Sintoma, Sintoma, Sintoma]:
    pat = Patologia(nombre="Fabry", descripcion="Enfermedad de Fabry")
    cardinal = Sintoma(snomed_id="225566008", descripcion="Acroparestesia")
    sec1 = Sintoma(snomed_id="4556007", descripcion="Hipohidrosis")
    sec2 = Sintoma(snomed_id="25064002", descripcion="Cefalea")
    session.add_all([pat, cardinal, sec1, sec2])
    session.flush()
    session.add_all(
        [
            PatologiaSintoma(patologia_id=pat.id, sintoma_id=cardinal.id, es_cardinal=True),
            PatologiaSintoma(patologia_id=pat.id, sintoma_id=sec1.id, es_cardinal=False),
            PatologiaSintoma(patologia_id=pat.id, sintoma_id=sec2.id, es_cardinal=False),
        ]
    )
    session.commit()
    return pat, cardinal, sec1, sec2


def test_snomed_prefijo_corto_rechaza_422(app, client, session):
    token = _token_medico(app, session)
    resp = client.get(
        "/api/v1/snomed/sintomas?q=ce",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "PREFIJO_DEMASIADO_CORTO"


def test_snomed_busqueda_exitosa_y_cache_local(app, client, session, monkeypatch):
    token = _token_medico(app, session)

    class _FakeSnomed:
        def __init__(self, *args, **kwargs):
            pass

        def buscar_sintomas(self, texto, limite=10):
            return [{"sctid": "25064002", "termino_preferido": "Cefalea"}]

    monkeypatch.setattr(clinica_service, "SnomedClient", _FakeSnomed)

    resp = client.get(
        "/api/v1/snomed/sintomas?q=cef",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["fuente"] == "snomed_api"
    assert data["resultados"] == [{"snomed_id": "25064002", "descripcion": "Cefalea"}]


def test_snomed_fallback_local_si_falla_api_externa(app, client, session, monkeypatch):
    token = _token_medico(app, session)
    _seed_patologia(session)

    class _FailSnomed:
        def __init__(self, *args, **kwargs):
            pass

        def buscar_sintomas(self, texto, limite=10):
            raise ClienteConexionError("Timeout SNOMED")

    monkeypatch.setattr(clinica_service, "SnomedClient", _FailSnomed)

    resp = client.get(
        "/api/v1/snomed/sintomas?q=cef",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["fuente"] == "local_fallback"
    assert data["resultados"][0]["snomed_id"] == "25064002"


def test_validar_sintomas_acepta_cardinal_o_dos_secundarios(app, client, session):
    token = _token_medico(app, session)
    pat, cardinal, sec1, sec2 = _seed_patologia(session)

    # Caso valido 1: 1 sintoma cardinal
    r1 = client.post(
        f"/api/v1/patologias/{pat.id}/validar-sintomas",
        headers={"Authorization": f"Bearer {token}"},
        json={"sintomas_snomed_ids": [cardinal.snomed_id]},
    )
    assert r1.status_code == 200

    # Caso valido 2: 2 sintomas secundarios
    r2 = client.post(
        f"/api/v1/patologias/{pat.id}/validar-sintomas",
        headers={"Authorization": f"Bearer {token}"},
        json={"sintomas_snomed_ids": [sec1.snomed_id, sec2.snomed_id]},
    )
    assert r2.status_code == 200

    # Caso invalido: solo 1 sintoma secundario (sin cardinal)
    r3 = client.post(
        f"/api/v1/patologias/{pat.id}/validar-sintomas",
        headers={"Authorization": f"Bearer {token}"},
        json={"sintomas_snomed_ids": [sec1.snomed_id]},
    )
    assert r3.status_code == 422
    assert r3.get_json()["code"] == "SINTOMAS_INCOMPATIBLES_PATOLOGIA"