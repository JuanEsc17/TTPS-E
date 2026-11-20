"""Tests de aceptacion para Escenario 23: Gestionar una patologia."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from src.clients.exceptions import ClienteConexionError
from src.core.database import db
from src.core.models import Patologia, PatologiaSintoma, Rol, Usuario
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)

PAYLOAD_FABRY = {
    "nombre": "Enfermedad de Fabry",
    "descripcion": "Trastorno lisosomal ligado al cromosoma X.",
    "sintoma_cardinal": {"snomed_id": "279079003", "descripcion": "Acroparestesia"},
    "sintomas_secundarios": [
        {"snomed_id": "79890006", "descripcion": "Angioqueratoma"},
        {"snomed_id": "52553005", "descripcion": "Hipohidrosis"},
        {"snomed_id": "55822004", "descripcion": "Hipertrofia ventricular izquierda"},
    ],
}


def _token_para_rol(app, session, rol: Rol, email: str) -> str:
    usuario = Usuario(
        email=email,
        password_hash=hashear_password("Clave1234"),
        rol=rol,
        nombre="Test",
        apellido="Usuario",
        telefono="1144556677",
        debe_cambiar_password=False,
    )
    session.add(usuario)
    session.commit()
    return emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )


class _ApigenFakeOk:
    def __init__(self, genes=None):
        self.genes = genes or ["GLA"]

    def obtener_genes_por_patologia(self, patologia: str):
        return self.genes


def test_tc01_alta_patologia_exitosa(app, client, session, monkeypatch):
    monkeypatch.setattr("src.core.services.patologia_service.ApigenClient", lambda: _ApigenFakeOk(["GLA"]))
    token = _token_para_rol(app, session, Rol.GERENTE_MEDICO, "gerente1@lab.org")

    resp = client.post(
        "/api/v1/patologias",
        headers={"Authorization": f"Bearer {token}"},
        json=PAYLOAD_FABRY,
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["nombre"] == "Enfermedad de Fabry"
    assert data["sintoma_cardinal"]["snomed_id"] == "279079003"
    assert data["sintoma_cardinal"]["es_cardinal"] is True
    assert len(data["sintomas_secundarios"]) == 3
    assert data["genes_sincronizados"] is True
    assert [g["simbolo"] for g in data["genes"]] == ["GLA"]

    filas = session.scalars(
        select(PatologiaSintoma).where(PatologiaSintoma.patologia_id == data["patologia_id"])
    ).all()
    assert sum(1 for f in filas if f.es_cardinal) == 1
    assert sum(1 for f in filas if not f.es_cardinal) == 3

    listado = client.get("/api/v1/patologias", headers={"Authorization": f"Bearer {token}"})
    assert listado.status_code == 200
    assert len(listado.get_json()["data"]) == 1


def test_tc02_modificar_patologia_reemplaza_cardinal_y_secundarios_atomico(app, client, session, monkeypatch):
    monkeypatch.setattr("src.core.services.patologia_service.ApigenClient", lambda: _ApigenFakeOk(["GLA"]))
    token = _token_para_rol(app, session, Rol.GERENTE_MEDICO, "gerente2@lab.org")

    alta = client.post("/api/v1/patologias", headers={"Authorization": f"Bearer {token}"}, json=PAYLOAD_FABRY)
    patologia_id = alta.get_json()["data"]["patologia_id"]

    resp = client.put(
        f"/api/v1/patologias/{patologia_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "nombre": "Enfermedad de Fabry Clasica",
            "descripcion": "Actualizada",
            "sintoma_cardinal": {"snomed_id": "79890006", "descripcion": "Angioqueratoma"},
            "sintomas_secundarios": [
                {"snomed_id": "279079003", "descripcion": "Acroparestesia"},
                {"snomed_id": "386661006", "descripcion": "Fiebre"},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["nombre"] == "Enfermedad de Fabry Clasica"
    assert data["sintoma_cardinal"]["snomed_id"] == "79890006"
    assert [s["snomed_id"] for s in data["sintomas_secundarios"]] == ["279079003", "386661006"]


@pytest.mark.parametrize("rol", [Rol.MEDICO, Rol.ADMINISTRATIVO, Rol.PACIENTE])
def test_tc03_acceso_denegado_si_no_es_gerente_medico(app, client, session, rol):
    token = _token_para_rol(app, session, rol, f"{rol.value}@lab.org")

    resp = client.post(
        "/api/v1/patologias",
        headers={"Authorization": f"Bearer {token}"},
        json=PAYLOAD_FABRY,
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "SOLO_GERENTE_MEDICO"


def test_tc04_rechaza_cardinal_repetido_en_secundarios(app, client, session):
    token = _token_para_rol(app, session, Rol.GERENTE_MEDICO, "gerente4@lab.org")
    payload = {
        **PAYLOAD_FABRY,
        "sintomas_secundarios": [
            {"snomed_id": "279079003", "descripcion": "Acroparestesia"},
            {"snomed_id": "52553005", "descripcion": "Hipohidrosis"},
        ],
    }

    resp = client.post("/api/v1/patologias", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "ESTRUCTURA_PATOLOGIA_INVALIDA"


@pytest.mark.parametrize(
    "mutacion",
    [
        {"sintoma_cardinal": None},
        {"sintomas_secundarios": [{"snomed_id": "79890006", "descripcion": "Angioqueratoma"}]},
        {"nombre": "   "},
    ],
)
def test_tc05_rechaza_sin_cardinal_o_menos_de_dos_secundarios(app, client, session, mutacion):
    token = _token_para_rol(app, session, Rol.GERENTE_MEDICO, "gerente5@lab.org")
    resp = client.post(
        "/api/v1/patologias",
        headers={"Authorization": f"Bearer {token}"},
        json={**PAYLOAD_FABRY, **mutacion},
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "ESTRUCTURA_PATOLOGIA_INVALIDA"


def test_tc06_nombre_patologia_duplicado_retorna_409(app, client, session, monkeypatch):
    monkeypatch.setattr("src.core.services.patologia_service.ApigenClient", lambda: _ApigenFakeOk(["GLA"]))
    token = _token_para_rol(app, session, Rol.GERENTE_MEDICO, "gerente6@lab.org")

    assert client.post("/api/v1/patologias", headers={"Authorization": f"Bearer {token}"}, json=PAYLOAD_FABRY).status_code == 201
    duplicada = client.post(
        "/api/v1/patologias",
        headers={"Authorization": f"Bearer {token}"},
        json={**PAYLOAD_FABRY, "nombre": "enfermedad de fabry"},
    )
    assert duplicada.status_code == 409
    assert duplicada.get_json()["code"] == "PATOLOGIA_NOMBRE_DUPLICADO"


def test_tc07_modificar_patologia_inexistente_retorna_404(app, client, session):
    token = _token_para_rol(app, session, Rol.GERENTE_MEDICO, "gerente7@lab.org")
    resp = client.put("/api/v1/patologias/9999", headers={"Authorization": f"Bearer {token}"}, json=PAYLOAD_FABRY)
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "PATOLOGIA_NO_ENCONTRADA"


def test_tc08_resiliencia_si_apigen_falla_conserva_patologia(app, client, session, monkeypatch):
    class _ApigenCaido:
        def __init__(self):
            self.intentos = 0

        def obtener_genes_por_patologia(self, patologia: str):
            self.intentos += 1
            raise ClienteConexionError("Timeout Apigen")

    fake = _ApigenCaido()
    monkeypatch.setattr("src.core.services.patologia_service.ApigenClient", lambda: fake)
    monkeypatch.setattr("src.core.services.patologia_service.time.sleep", lambda _s: None)
    token = _token_para_rol(app, session, Rol.GERENTE_MEDICO, "gerente8@lab.org")

    resp = client.post("/api/v1/patologias", headers={"Authorization": f"Bearer {token}"}, json=PAYLOAD_FABRY)
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert fake.intentos == 3
    assert data["genes_sincronizados"] is False
    assert session.scalar(select(Patologia).where(Patologia.id == data["patologia_id"])) is not None


def test_busqueda_sintomas_snomed_y_validacion_query(app, client, session, monkeypatch):
    class _SnomedFake:
        def buscar_sintomas(self, texto: str, limite: int = 10):
            return [{"sctid": "279079003", "termino_preferido": "Acroparestesia", "estrategia": "lexica"}]

    monkeypatch.setattr("src.core.services.patologia_service.SnomedClient", lambda: _SnomedFake())
    token = _token_para_rol(app, session, Rol.GERENTE_MEDICO, "gerente9@lab.org")

    assert client.get("/api/v1/sintomas/snomed?q=ac", headers={"Authorization": f"Bearer {token}"}).status_code == 400
    ok = client.get("/api/v1/sintomas/snomed?q=acro", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert ok.get_json()["data"] == [{"snomed_id": "279079003", "descripcion": "Acroparestesia"}]


def test_abort_cleanup_rollback_ante_fallo_bd(app, client, session, monkeypatch):
    token = _token_para_rol(app, session, Rol.GERENTE_MEDICO, "gerente10@lab.org")

    def _fallar_commit():
        raise SQLAlchemyError("Error de conexion simulado")

    monkeypatch.setattr(db.session, "commit", _fallar_commit)
    resp = client.post("/api/v1/patologias", headers={"Authorization": f"Bearer {token}"}, json=PAYLOAD_FABRY)
    monkeypatch.undo()

    assert resp.status_code == 503
    assert resp.get_json()["code"] == "DB_ERROR"
    assert session.scalars(select(Patologia)).all() == []
