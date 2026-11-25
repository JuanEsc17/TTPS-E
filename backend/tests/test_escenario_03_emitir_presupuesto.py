"""Tests del Escenario 3: Emitir un presupuesto.

Spec: docs/specs/escenario-03-emitir-un-presupuesto.md (v1.1)
Endpoint: POST /api/v1/estudios/{estudio_id}/presupuesto
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from src.clients import ClienteServicioError, EmailClient
from src.clients.obra_social_client import ObraSocialClient
from src.core.models import (
    Autorizacion,
    Aviso,
    CanalAviso,
    EntidadAuditable,
    EstadoEstudio,
    Estudio,
    EstudioGen,
    Gen,
    Medico,
    ObraSocial,
    OrigenGen,
    Paciente,
    Patologia,
    Presupuesto,
    RegistroModificacion,
    ResultadoAutorizacion,
    Rol,
    TipoAccionAuditoria,
    Usuario,
)
from src.core.models.reglas import calcular_precio
from src.core.services.seguridad import SCOPE_ACCESO_COMPLETO, emitir_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_header_para(app, usuario: Usuario) -> dict[str, str]:
    """Genera cabecera Authorization con Bearer token valido para el usuario."""
    token = emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return {"Authorization": f"Bearer {token}"}


def _url(estudio_id: int) -> str:
    return f"/api/v1/estudios/{estudio_id}/presupuesto"


def _asociar_genes(session, estudio: Estudio, genes: list[Gen]) -> None:
    """Asocia genes al estudio rotando los tres origenes (supuesto A1: todos cuentan)."""
    origenes = [OrigenGen.PATOLOGIA, OrigenGen.MANUAL, OrigenGen.HALLAZGO_SECUNDARIO]
    for i, gen in enumerate(genes):
        session.add(EstudioGen(estudio_id=estudio.id, gen_id=gen.id, origen=origenes[i % 3]))


def _contar(session, modelo, *condiciones) -> int:
    return session.scalar(select(func.count()).select_from(modelo).where(*condiciones))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mocks_clientes(app):
    """Evita llamadas HTTP reales: mockea mail y API de obras sociales."""
    mock_email = MagicMock(spec=EmailClient)
    mock_os = MagicMock(spec=ObraSocialClient)
    mock_os.listar_obras_sociales.return_value = {
        "datos": [{"id": "os-1", "nombre": "OSDE", "rnos": "115404", "porcentaje_cobertura": 80}],
        "total": 1,
    }
    mock_os.crear_solicitud.return_value = {"id": "sol-981", "estado": "pendiente"}
    app.config["EMAIL_CLIENT"] = mock_email
    app.config["OBRA_SOCIAL_CLIENT"] = mock_os
    return {"email": mock_email, "obra_social": mock_os}


@pytest.fixture
def datos_presupuesto(session):
    """Administrativo, medico, paciente, obra social, genes y estudios en distintos casos."""
    patologia = Patologia(nombre="Enfermedad de Pompe", descripcion="Glucogenosis tipo II")
    obra_social = ObraSocial(nombre="OSDE", rnos="115404", porcentaje_cobertura=Decimal("80.00"))

    u_admin = Usuario(
        email="admin.presupuesto@lab.com", password_hash="hash", rol=Rol.ADMINISTRATIVO,
        nombre="Sofia", apellido="Ruiz", telefono="11445566",
    )
    u_med = Usuario(
        email="med.presupuesto@hospital.com", password_hash="hash", rol=Rol.MEDICO,
        nombre="Laura", apellido="Mendez", telefono="11223344",
    )
    u_pac = Usuario(
        email="pac.presupuesto@gmail.com", password_hash="hash", rol=Rol.PACIENTE,
        nombre="Martin", apellido="Gomez", telefono="11998877",
    )
    genes = [
        Gen(simbolo=s, nombre=f"Gen {s}")
        for s in ("GAA", "BRCA1", "BRCA2", "TP53", "CFTR", "MLH1", "MSH2", "APC")
    ]
    session.add_all([patologia, obra_social, u_admin, u_med, u_pac, *genes])
    session.flush()

    medico = Medico(usuario_id=u_med.id, matricula="MP-30303")
    session.add(medico)
    session.flush()

    paciente = Paciente(
        usuario_id=u_pac.id,
        medico_id=medico.id,
        dni="30111333",
        fecha_nacimiento=date(1990, 3, 15),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-3001",
        tipo_sospecha="clinica",
    )
    session.add(paciente)
    session.flush()

    def _estudio(estado=EstadoEstudio.CREADO, obra_social_id=None) -> Estudio:
        est = Estudio(
            paciente_id=paciente.id,
            medico_id=medico.id,
            patologia_sospechada_id=patologia.id,
            estado=estado,
            obra_social_id=obra_social_id,
        )
        session.add(est)
        session.flush()
        return est

    est_4_genes = _estudio()
    est_5_genes = _estudio()
    est_8_genes = _estudio()
    est_os_6_genes = _estudio(obra_social_id=obra_social.id)
    est_sin_genes = _estudio()
    est_otro_estado = _estudio(estado=EstadoEstudio.PENDIENTE_AUTORIZACION)

    _asociar_genes(session, est_4_genes, genes[:4])
    _asociar_genes(session, est_5_genes, genes[:5])
    _asociar_genes(session, est_8_genes, genes[:8])
    _asociar_genes(session, est_os_6_genes, genes[:6])
    _asociar_genes(session, est_otro_estado, genes[:3])
    session.commit()

    return {
        "u_admin": u_admin,
        "u_med": u_med,
        "u_pac": u_pac,
        "obra_social": obra_social,
        "est_4_genes": est_4_genes,
        "est_5_genes": est_5_genes,
        "est_8_genes": est_8_genes,
        "est_os_6_genes": est_os_6_genes,
        "est_sin_genes": est_sin_genes,
        "est_otro_estado": est_otro_estado,
    }


# ---------------------------------------------------------------------------
# Regla de dominio
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("cantidad_genes", "esperado"),
    [(1, Decimal("500")), (5, Decimal("500")), (6, Decimal("530")), (8, Decimal("590"))],
)
def test_calcular_precio(cantidad_genes, esperado):
    """500 USD hasta 5 genes + 30 USD por cada gen adicional."""
    assert calcular_precio(cantidad_genes) == esperado


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_tc01_particular_hasta_5_genes(app, client, session, datos_presupuesto, mocks_clientes):
    """TC-01: estudio particular con 4 genes -> 500 USD y permanece en Creado."""
    est = datos_presupuesto["est_4_genes"]
    u_admin = datos_presupuesto["u_admin"]

    resp = client.post(_url(est.id), headers=_auth_header_para(app, u_admin), json={})

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["ok"] is True
    data = body["data"]
    assert data["estudio_id"] == est.id
    assert data["emitido_por_id"] == u_admin.id
    assert data["cantidad_genes"] == 4
    assert data["precio_base_usd"] == "500.00"
    assert data["genes_adicionales"] == 0
    assert data["costo_adicional_usd"] == "0.00"
    assert data["monto_total_usd"] == "500.00"
    assert data["estado_estudio"] == EstadoEstudio.CREADO.value

    presupuesto = session.scalar(select(Presupuesto).where(Presupuesto.estudio_id == est.id))
    assert presupuesto is not None
    assert presupuesto.id == data["presupuesto_id"]
    assert presupuesto.emitido_por_id == u_admin.id
    assert presupuesto.cantidad_genes == 4
    assert presupuesto.monto_total_usd == Decimal("500.00")

    session.refresh(est)
    assert est.estado == EstadoEstudio.CREADO
    assert _contar(session, Autorizacion, Autorizacion.estudio_id == est.id) == 0
    mocks_clientes["obra_social"].crear_solicitud.assert_not_called()

    # Aviso al paciente (APP) + correo electronico
    avisos = session.scalars(
        select(Aviso).where(Aviso.usuario_id == datos_presupuesto["u_pac"].id)
    ).all()
    assert any(a.canal == CanalAviso.APP for a in avisos)
    assert mocks_clientes["email"].enviar_aviso.called


def test_tc02_exactamente_5_genes(app, client, session, datos_presupuesto):
    """TC-02: estudio con 5 genes -> 500 USD."""
    est = datos_presupuesto["est_5_genes"]

    resp = client.post(
        _url(est.id), headers=_auth_header_para(app, datos_presupuesto["u_admin"]), json={}
    )

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["cantidad_genes"] == 5
    assert data["genes_adicionales"] == 0
    assert data["monto_total_usd"] == "500.00"
    presupuesto = session.scalar(select(Presupuesto).where(Presupuesto.estudio_id == est.id))
    assert presupuesto.monto_total_usd == Decimal("500.00")


def test_tc03_mas_de_5_genes(app, client, session, datos_presupuesto):
    """TC-03: 8 genes (de los 3 origenes) -> 500 + 3 * 30 = 590 USD."""
    est = datos_presupuesto["est_8_genes"]

    resp = client.post(
        _url(est.id), headers=_auth_header_para(app, datos_presupuesto["u_admin"]), json={}
    )

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["cantidad_genes"] == 8
    assert data["precio_base_usd"] == "500.00"
    assert data["genes_adicionales"] == 3
    assert data["costo_adicional_usd"] == "90.00"
    assert data["monto_total_usd"] == "590.00"
    presupuesto = session.scalar(select(Presupuesto).where(Presupuesto.estudio_id == est.id))
    assert presupuesto.cantidad_genes == 8
    assert presupuesto.monto_total_usd == Decimal("590.00")


def test_tc04_obra_social_pasa_a_pendiente_autorizacion(
    app, client, session, datos_presupuesto, mocks_clientes
):
    """TC-04: estudio con obra social y 6 genes -> 530 USD, Pendiente de autorizacion."""
    est = datos_presupuesto["est_os_6_genes"]
    u_admin = datos_presupuesto["u_admin"]

    resp = client.post(_url(est.id), headers=_auth_header_para(app, u_admin), json={})

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["cantidad_genes"] == 6
    assert data["genes_adicionales"] == 1
    assert data["costo_adicional_usd"] == "30.00"
    assert data["monto_total_usd"] == "530.00"
    assert data["estado_estudio"] == EstadoEstudio.PENDIENTE_AUTORIZACION.value
    assert data["porcentaje_cobertura_obra_social"] == "80.00"

    session.refresh(est)
    assert est.estado == EstadoEstudio.PENDIENTE_AUTORIZACION

    autorizacion = session.scalar(select(Autorizacion).where(Autorizacion.estudio_id == est.id))
    assert autorizacion is not None
    assert autorizacion.resultado == ResultadoAutorizacion.PENDIENTE
    assert autorizacion.solicitud_externa_id == "sol-981"
    mocks_clientes["obra_social"].crear_solicitud.assert_called_once()

    # Auditoria del cambio de estado en registro_modificaciones
    reg = session.scalar(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
            RegistroModificacion.entidad_id == est.id,
        )
    )
    assert reg is not None
    assert reg.accion == TipoAccionAuditoria.CAMBIO_ESTADO
    assert reg.usuario_id == u_admin.id
    assert reg.cambios["estado"]["anterior"] == EstadoEstudio.CREADO.value
    assert reg.cambios["estado"]["nuevo"] == EstadoEstudio.PENDIENTE_AUTORIZACION.value


def test_obra_social_informada_en_payload(app, client, session, datos_presupuesto):
    """Supuesto A2: el obra_social_id del body hace que el estudio se tramite por obra social."""
    est = datos_presupuesto["est_4_genes"]
    obra_social = datos_presupuesto["obra_social"]

    resp = client.post(
        _url(est.id),
        headers=_auth_header_para(app, datos_presupuesto["u_admin"]),
        json={"obra_social_id": obra_social.id},
    )

    assert resp.status_code == 201
    assert resp.get_json()["data"]["estado_estudio"] == EstadoEstudio.PENDIENTE_AUTORIZACION.value
    session.refresh(est)
    assert est.obra_social_id == obra_social.id
    assert est.estado == EstadoEstudio.PENDIENTE_AUTORIZACION
    assert _contar(session, Autorizacion, Autorizacion.estudio_id == est.id) == 1


def test_tc07_api_obras_sociales_caida_usa_copia_local(
    app, client, session, datos_presupuesto, mocks_clientes
):
    """TC-07 (STEP 2 fallback): si la API de obras sociales falla se usa la copia local y no se aborta."""
    est = datos_presupuesto["est_os_6_genes"]
    obra_social = datos_presupuesto["obra_social"]
    obra_social.porcentaje_cobertura = Decimal("70.00")
    session.commit()

    error = ClienteServicioError("API de obras sociales caida", codigo_http=503)
    mocks_clientes["obra_social"].listar_obras_sociales.side_effect = error
    mocks_clientes["obra_social"].crear_solicitud.side_effect = error

    resp = client.post(
        _url(est.id), headers=_auth_header_para(app, datos_presupuesto["u_admin"]), json={}
    )

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["monto_total_usd"] == "530.00"
    assert data["porcentaje_cobertura_obra_social"] == "70.00"
    assert data["estado_estudio"] == EstadoEstudio.PENDIENTE_AUTORIZACION.value

    autorizacion = session.scalar(select(Autorizacion).where(Autorizacion.estudio_id == est.id))
    assert autorizacion is not None
    assert autorizacion.resultado == ResultadoAutorizacion.PENDIENTE
    assert autorizacion.solicitud_externa_id is None


# ---------------------------------------------------------------------------
# Fallos
# ---------------------------------------------------------------------------

def test_tc05_presupuesto_duplicado(app, client, session, datos_presupuesto):
    """TC-05: segundo presupuesto para el mismo estudio -> 409 PRESUPUESTO_YA_EMITIDO."""
    est = datos_presupuesto["est_8_genes"]
    headers = _auth_header_para(app, datos_presupuesto["u_admin"])

    assert client.post(_url(est.id), headers=headers, json={}).status_code == 201
    resp = client.post(_url(est.id), headers=headers, json={})

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["ok"] is False
    assert body["code"] == "PRESUPUESTO_YA_EMITIDO"
    assert body["retryable"] is False

    presupuestos = session.scalars(select(Presupuesto).where(Presupuesto.estudio_id == est.id)).all()
    assert len(presupuestos) == 1
    assert presupuestos[0].monto_total_usd == Decimal("590.00")


def test_tc06_rol_no_administrativo(app, client, session, datos_presupuesto):
    """TC-06: medico o paciente -> 403 FORBIDDEN_ROLE; sin sesion -> 401."""
    est = datos_presupuesto["est_4_genes"]

    assert client.post(_url(est.id), json={}).status_code == 401

    for usuario in (datos_presupuesto["u_med"], datos_presupuesto["u_pac"]):
        resp = client.post(_url(est.id), headers=_auth_header_para(app, usuario), json={})
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "FORBIDDEN_ROLE"

    assert _contar(session, Presupuesto, Presupuesto.estudio_id == est.id) == 0


def test_estudio_inexistente(app, client, datos_presupuesto):
    """STEP 1: estudio_id inexistente -> 404 ESTUDIO_NO_ENCONTRADO."""
    resp = client.post(
        _url(99999), headers=_auth_header_para(app, datos_presupuesto["u_admin"]), json={}
    )
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "ESTUDIO_NO_ENCONTRADO"


def test_estado_invalido(app, client, session, datos_presupuesto):
    """STEP 1: estudio que no esta en Creado -> 409 ESTADO_ESTUDIO_INVALIDO."""
    est = datos_presupuesto["est_otro_estado"]

    resp = client.post(
        _url(est.id), headers=_auth_header_para(app, datos_presupuesto["u_admin"]), json={}
    )

    assert resp.status_code == 409
    assert resp.get_json()["code"] == "ESTADO_ESTUDIO_INVALIDO"
    assert _contar(session, Presupuesto, Presupuesto.estudio_id == est.id) == 0


def test_estudio_sin_genes(app, client, session, datos_presupuesto):
    """STEP 1: estudio sin genes asociados -> 422 ESTUDIO_SIN_GENES."""
    est = datos_presupuesto["est_sin_genes"]

    resp = client.post(
        _url(est.id), headers=_auth_header_para(app, datos_presupuesto["u_admin"]), json={}
    )

    assert resp.status_code == 422
    assert resp.get_json()["code"] == "ESTUDIO_SIN_GENES"
    assert _contar(session, Presupuesto, Presupuesto.estudio_id == est.id) == 0


def test_tc09_rollback_si_falla_la_base(app, client, session, datos_presupuesto, monkeypatch):
    """TC-09 (ABORT_CLEANUP): si falla el commit no queda presupuesto, autorizacion, aviso ni cambio de estado."""
    est = datos_presupuesto["est_os_6_genes"]
    u_pac = datos_presupuesto["u_pac"]

    def _commit_fallido(self):
        raise SQLAlchemyError("Base de datos no disponible")

    monkeypatch.setattr(Session, "commit", _commit_fallido)
    resp = client.post(
        _url(est.id), headers=_auth_header_para(app, datos_presupuesto["u_admin"]), json={}
    )
    monkeypatch.undo()

    assert resp.status_code in (500, 503)
    assert resp.get_json()["retryable"] is True

    session.expire_all()
    assert session.get(Estudio, est.id).estado == EstadoEstudio.CREADO
    assert _contar(session, Presupuesto, Presupuesto.estudio_id == est.id) == 0
    assert _contar(session, Autorizacion, Autorizacion.estudio_id == est.id) == 0
    assert _contar(session, Aviso, Aviso.usuario_id == u_pac.id) == 0

def test_tc08_fallo_de_mail_aborta_presupuesto(app, client, session, datos_presupuesto, mocks_clientes):
    """TC-08: si la API de mail falla se revierte todo (502 ERROR_ENVIO_EMAIL, retryable)."""
    est = datos_presupuesto["est_os_6_genes"]
    u_pac = datos_presupuesto["u_pac"]
    mocks_clientes["email"].enviar_aviso.side_effect = ClienteServicioError(
        "API de mail caida", codigo_http=503
    )

    resp = client.post(
        _url(est.id), headers=_auth_header_para(app, datos_presupuesto["u_admin"]), json={}
    )

    assert resp.status_code == 502
    body = resp.get_json()
    assert body["code"] == "ERROR_ENVIO_EMAIL"
    assert body["retryable"] is True

    session.expire_all()
    assert session.get(Estudio, est.id).estado == EstadoEstudio.CREADO
    assert _contar(session, Presupuesto, Presupuesto.estudio_id == est.id) == 0
    assert _contar(session, Autorizacion, Autorizacion.estudio_id == est.id) == 0
    assert _contar(session, Aviso, Aviso.usuario_id == u_pac.id) == 0

# ---------------------------------------------------------------------------
# STEP 0: bandeja de pendientes
# ---------------------------------------------------------------------------

URL_PENDIENTES = "/api/v1/presupuestos/pendientes"


def test_tc10_listar_pendientes(app, client, datos_presupuesto):
    """TC-10: solo estudios en Creado sin presupuesto, con desglose estimado."""
    resp = client.get(URL_PENDIENTES, headers=_auth_header_para(app, datos_presupuesto["u_admin"]))

    assert resp.status_code == 200
    items = {item["estudio_id"]: item for item in resp.get_json()["data"]}

    esperados = {
        datos_presupuesto[k].id
        for k in ("est_4_genes", "est_5_genes", "est_8_genes", "est_os_6_genes", "est_sin_genes")
    }
    assert set(items) == esperados
    assert datos_presupuesto["est_otro_estado"].id not in items

    item_8 = items[datos_presupuesto["est_8_genes"].id]
    assert item_8["estado_estudio"] == EstadoEstudio.CREADO.value
    assert item_8["paciente_dni"] == "30111333"
    assert item_8["cantidad_genes"] == 8
    assert item_8["precio_base_usd"] == "500.00"
    assert item_8["genes_adicionales"] == 3
    assert item_8["costo_adicional_usd"] == "90.00"
    assert item_8["monto_estimado_usd"] == "590.00"
    assert item_8["obra_social"] is None

    item_os = items[datos_presupuesto["est_os_6_genes"].id]
    assert item_os["obra_social"]["nombre"] == "OSDE"
    assert item_os["obra_social"]["porcentaje_cobertura"] == "80.00"

    assert items[datos_presupuesto["est_sin_genes"].id]["monto_estimado_usd"] is None


def test_tc11_estudio_presupuestado_sale_de_la_bandeja(app, client, datos_presupuesto):
    """TC-11: tras emitir el presupuesto el estudio deja de figurar como pendiente."""
    headers = _auth_header_para(app, datos_presupuesto["u_admin"])
    est = datos_presupuesto["est_4_genes"]

    assert client.post(_url(est.id), headers=headers, json={}).status_code == 201
    resp = client.get(URL_PENDIENTES, headers=headers)

    ids = {item["estudio_id"] for item in resp.get_json()["data"]}
    assert est.id not in ids


def test_tc12_filtro_dni_y_permisos(app, client, datos_presupuesto):
    """TC-12: filtro por DNI, DNI invalido y acceso solo para administrativos."""
    headers = _auth_header_para(app, datos_presupuesto["u_admin"])

    assert len(client.get(f"{URL_PENDIENTES}?dni=30111", headers=headers).get_json()["data"]) == 5
    assert client.get(f"{URL_PENDIENTES}?dni=99999999", headers=headers).get_json()["data"] == []

    resp_invalido = client.get(f"{URL_PENDIENTES}?dni=abc", headers=headers)
    assert resp_invalido.status_code == 422
    assert resp_invalido.get_json()["code"] == "DNI_INVALIDO"

    resp_medico = client.get(URL_PENDIENTES, headers=_auth_header_para(app, datos_presupuesto["u_med"]))
    assert resp_medico.status_code == 403
    assert resp_medico.get_json()["code"] == "FORBIDDEN_ROLE"