"""Tests integrales para Escenario 10: Remuestrear un estudio por falla de calidad (ADR-004)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from src.clients import ClienteServicioError, EmailClient
from src.core.models import (
    Aviso,
    CanalAviso,
    CentroExtraccion,
    EntidadAuditable,
    EstadoEstudio,
    EstadoSampleSet,
    Estudio,
    Medico,
    MotivoDescarte,
    Muestra,
    Paciente,
    Pago,
    Patologia,
    Presupuesto,
    RegistroModificacion,
    Rol,
    SampleSet,
    TipoAccionAuditoria,
    TipoPago,
    Turno,
    Usuario,
)
from src.core.services.seguridad import SCOPE_ACCESO_COMPLETO, emitir_token


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


def _proximo_dia_habil(hora: int = 10, minuto: int = 15) -> datetime:
    """Retorna un datetime futuro en dia habil (lunes a viernes) fuera de feriados comunes."""
    candidato = date.today() + timedelta(days=2)
    while candidato.weekday() >= 5 or (candidato.month, candidato.day) in {
        (1, 1),
        (3, 24),
        (4, 2),
        (5, 1),
        (5, 25),
        (6, 20),
        (7, 9),
        (12, 8),
        (12, 25),
    }:
        candidato += timedelta(days=1)
    return datetime.combine(candidato, time(hora, minuto))


@pytest.fixture
def datos_remuestreo(session):
    """Prepara administrativo, medico, pacientes, SampleSet en viaje a Corea, pago y estudios."""
    centro = CentroExtraccion(
        nombre="Centro Extraccion La Plata",
        direccion="Calle 7 Nro 850",
        provincia="Buenos Aires",
        latitud=-34.9205,
        longitud=-57.9536,
    )
    patologia = Patologia(nombre="Enfermedad de Fabry", descripcion="Patologia lisosomal")

    u_admin = Usuario(
        email="admin.remuestreo@lab.com",
        password_hash="hash",
        rol=Rol.ADMINISTRATIVO,
        nombre="Sofia",
        apellido="Ruiz",
        telefono="11445566",
    )
    u_med = Usuario(
        email="med.remuestreo@hospital.com",
        password_hash="hash",
        rol=Rol.MEDICO,
        nombre="Laura",
        apellido="Mendez",
        telefono="11223344",
    )
    u_pac_1 = Usuario(
        email="pac1.remuestreo@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Martin",
        apellido="Gomez",
        telefono="11998877",
    )
    u_pac_2 = Usuario(
        email="pac2.remuestreo@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Lucia",
        apellido="Fernandez",
        telefono="11665544",
    )
    session.add_all([centro, patologia, u_admin, u_med, u_pac_1, u_pac_2])
    session.flush()

    medico = Medico(usuario_id=u_med.id, matricula="MP-88101")
    session.add(medico)
    session.flush()

    pac_1 = Paciente(
        usuario_id=u_pac_1.id,
        medico_id=medico.id,
        dni="30111222",
        fecha_nacimiento=date(1992, 5, 10),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-1001",
        tipo_sospecha="clinica",
    )
    pac_2 = Paciente(
        usuario_id=u_pac_2.id,
        medico_id=medico.id,
        dni="35999888",
        fecha_nacimiento=date(1995, 8, 20),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-1002",
        tipo_sospecha="clinica",
    )
    session.add_all([pac_1, pac_2])
    session.flush()

    sample_set = SampleSet(
        estado=EstadoSampleSet.EN_VIAJE_COREA,
        cerrado_en=datetime.now() - timedelta(days=3),
        csv_path="storage/sample_sets/lote_7.csv",
        autorizacion_ministerio_pdf_path="storage/sample_sets/auth_7.pdf",
        retiro_fedex_pedido_id="FEDEX-777",
    )
    session.add(sample_set)
    session.flush()

    est_1 = Estudio(
        paciente_id=pac_1.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.EN_VIAJE_COREA,
        ausencias=2,
    )
    est_2 = Estudio(
        paciente_id=pac_2.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.EN_VIAJE_COREA,
        ausencias=0,
    )
    est_bio = Estudio(
        paciente_id=pac_2.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        ausencias=0,
    )
    session.add_all([est_1, est_2, est_bio])
    session.flush()

    presupuesto = Presupuesto(
        estudio_id=est_1.id,
        emitido_por_id=u_admin.id,
        cantidad_genes=5,
        monto_total_usd=Decimal("500.00"),
    )
    session.add(presupuesto)
    session.flush()

    pago = Pago(
        presupuesto_id=presupuesto.id,
        tipo=TipoPago.PARTICULAR,
        monto_usd=Decimal("500.00"),
        anulado=False,
    )
    session.add(pago)

    hace_4_dias = datetime.now() - timedelta(days=4)
    turno_1 = Turno(
        centro_id=centro.id,
        paciente_id=pac_1.id,
        estudio_id=est_1.id,
        inicio=hace_4_dias,
        activo=False,
        asistio=True,
    )
    turno_2 = Turno(
        centro_id=centro.id,
        paciente_id=pac_2.id,
        estudio_id=est_2.id,
        inicio=hace_4_dias,
        activo=False,
        asistio=True,
    )
    session.add_all([turno_1, turno_2])
    session.flush()

    muestra_1 = Muestra(
        estudio_id=est_1.id,
        turno_id=turno_1.id,
        sample_set_id=sample_set.id,
        tomada_en=hace_4_dias,
        llegada_lab_central=hace_4_dias + timedelta(hours=3),
    )
    muestra_2 = Muestra(
        estudio_id=est_2.id,
        turno_id=turno_2.id,
        sample_set_id=sample_set.id,
        tomada_en=hace_4_dias,
        llegada_lab_central=hace_4_dias + timedelta(hours=3),
    )
    muestra_bio = Muestra(
        estudio_id=est_bio.id,
        tomada_en=hace_4_dias - timedelta(days=2),
    )
    session.add_all([muestra_1, muestra_2, muestra_bio])
    session.commit()

    return {
        "centro": centro,
        "u_admin": u_admin,
        "u_med": u_med,
        "u_pac_1": u_pac_1,
        "u_pac_2": u_pac_2,
        "sample_set": sample_set,
        "est_1": est_1,
        "est_2": est_2,
        "est_bio": est_bio,
        "pago": pago,
        "muestra_1": muestra_1,
        "muestra_2": muestra_2,
    }


def test_listar_remuestreables_y_tc01_rollback_desde_corea(app, client, session, datos_remuestreo):
    """TC-01 + listado: descarta muestra vigente por BAJA_CALIDAD preservando SampleSet y auditoria."""
    headers = _auth_header_para(app, datos_remuestreo["u_admin"])
    est_1 = datos_remuestreo["est_1"]
    est_2 = datos_remuestreo["est_2"]
    sample_set = datos_remuestreo["sample_set"]
    muestra_1 = datos_remuestreo["muestra_1"]
    pago = datos_remuestreo["pago"]

    # Listado inicial de estudios remuestreables (filtra por DNI)
    resp_list = client.get("/api/v1/muestras/remuestreables?dni=30111222", headers=headers)
    assert resp_list.status_code == 200
    items = resp_list.get_json()["data"]
    assert len(items) == 1
    assert items[0]["estudio_id"] == est_1.id
    assert items[0]["muestra_vigente"]["sample_set_id"] == sample_set.id

    mock_email = MagicMock(spec=EmailClient)
    app.config["EMAIL_CLIENT"] = mock_email

    resp = client.post(
        f"/api/v1/estudios/{est_1.id}/remuestreo",
        headers=headers,
        json={
            "motivo_descarte": "baja_calidad",
            "observaciones_calidad": "Muestra hemolizada al arribo en Corea segun reporte lote #7",
            "motivo": "Reporte de baja calidad recibido desde Corea; requiere nueva extraccion",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    data = body["data"]
    assert data["estudio_id"] == est_1.id
    assert data["estado_anterior"] == EstadoEstudio.EN_VIAJE_COREA.value
    assert data["estado_nuevo"] == EstadoEstudio.REMUESTREO_REQUERIDO.value
    assert data["muestra_descartada_id"] == muestra_1.id
    assert data["motivo_descarte"] == MotivoDescarte.BAJA_CALIDAD.value
    assert data["sample_set_id"] == sample_set.id

    session.refresh(muestra_1)
    session.refresh(est_1)
    session.refresh(est_2)
    session.refresh(sample_set)
    session.refresh(pago)

    assert muestra_1.motivo_descarte == MotivoDescarte.BAJA_CALIDAD
    assert "hemolizada" in (muestra_1.observaciones_calidad or "")
    assert muestra_1.sample_set_id == sample_set.id
    assert sample_set.estado == EstadoSampleSet.EN_VIAJE_COREA
    assert est_1.estado == EstadoEstudio.REMUESTREO_REQUERIDO
    assert est_1.muestra_vigente is None
    assert est_1.ausencias == 2
    assert pago.anulado is False
    assert est_2.estado == EstadoEstudio.EN_VIAJE_COREA
    assert est_2.muestra_vigente is not None

    # Audito el cambio de estado en registro_modificaciones (ADR-003)
    reg = session.scalar(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
            RegistroModificacion.entidad_id == est_1.id,
        )
    )
    assert reg is not None
    assert reg.accion == TipoAccionAuditoria.CAMBIO_ESTADO
    assert reg.usuario_id == datos_remuestreo["u_admin"].id
    assert reg.cambios["estado"]["anterior"] == EstadoEstudio.EN_VIAJE_COREA.value
    assert reg.cambios["estado"]["nuevo"] == EstadoEstudio.REMUESTREO_REQUERIDO.value
    assert reg.cambios["motivo_descarte"]["nuevo"] == "baja_calidad"

    # Avisos internos APP para Paciente y Medico + mails enviados
    aviso_pac = session.get(Aviso, data["aviso_paciente_id"])
    aviso_med = session.get(Aviso, data["aviso_medico_id"])
    assert aviso_pac is not None and aviso_pac.canal == CanalAviso.APP
    assert aviso_med is not None and aviso_med.canal == CanalAviso.APP
    assert "sin costo adicional" in aviso_pac.mensaje
    assert mock_email.enviar_aviso.call_count == 2


def test_tc02_rechazo_motivo_invalido_volumen_insuficiente(app, client, session, datos_remuestreo):
    """TC-02: Rechaza con 422 MOTIVO_DESCARTE_INVALIDO cualquier motivo no contemplado (ej. volumen_insuficiente)."""
    headers = _auth_header_para(app, datos_remuestreo["u_admin"])
    est_1 = datos_remuestreo["est_1"]
    muestra_1 = datos_remuestreo["muestra_1"]

    resp = client.post(
        f"/api/v1/estudios/{est_1.id}/remuestreo",
        headers=headers,
        json={
            "motivo_descarte": "volumen_insuficiente",
            "motivo": "Intento obsoleto",
        },
    )
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "MOTIVO_DESCARTE_INVALIDO"

    session.refresh(est_1)
    session.refresh(muestra_1)
    assert est_1.estado == EstadoEstudio.EN_VIAJE_COREA
    assert muestra_1.motivo_descarte is None


def test_tc03_ciclo_completo_segunda_extraccion_sin_costo(app, client, session, datos_remuestreo):
    """TC-03: Remuestreo -> Paciente saca 2do turno sin pagar -> Admin registra 2da muestra vigente."""
    headers_admin = _auth_header_para(app, datos_remuestreo["u_admin"])
    headers_pac = _auth_header_para(app, datos_remuestreo["u_pac_1"])
    est_1 = datos_remuestreo["est_1"]
    centro = datos_remuestreo["centro"]
    muestra_1 = datos_remuestreo["muestra_1"]

    # 1. Administrativo solicita remuestreo desde EN_VIAJE_COREA
    r_rem = client.post(
        f"/api/v1/estudios/{est_1.id}/remuestreo",
        headers=headers_admin,
        json={
            "motivo_descarte": "desnaturalizada",
            "motivo": "Muestra desnaturalizada en laboratorio",
        },
    )
    assert r_rem.status_code == 200

    # 2. Paciente saca 2do turno sin pagar de nuevo (Escenario 7)
    horario = _proximo_dia_habil(10, 15)
    r_turno = client.post(
        f"/api/v1/estudios/{est_1.id}/turnos",
        headers=headers_pac,
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
    )
    assert r_turno.status_code == 201
    turno_2_id = r_turno.get_json()["data"]["turno_id"]

    # 3. Administrativo registra la toma de la 2da muestra (Escenario 9)
    r_toma = client.post(
        f"/api/v1/muestras/turnos/{turno_2_id}/toma",
        headers=headers_admin,
        json={},
    )
    assert r_toma.status_code == 201
    muestra_2_id = r_toma.get_json()["data"]["muestra_id"]

    session.refresh(est_1)
    assert est_1.estado == EstadoEstudio.LISTA_PARA_RETIRAR
    assert est_1.muestra_vigente is not None
    assert est_1.muestra_vigente.id == muestra_2_id
    assert est_1.muestra_vigente.id != muestra_1.id
    assert est_1.muestra_vigente.sample_set_id is None


def test_tc04_y_tc05_permisos_y_estados_invalidos(app, client, session, datos_remuestreo):
    """TC-04 + TC-05: Rechaza 403 a no administrativos, 404 inexistente y 409 estado/muestra invalidos."""
    est_1 = datos_remuestreo["est_1"]
    est_bio = datos_remuestreo["est_bio"]
    headers_admin = _auth_header_para(app, datos_remuestreo["u_admin"])
    payload = {"motivo_descarte": "baja_calidad", "motivo": "Reporte Corea"}

    # Sin sesion -> 401
    assert client.post(f"/api/v1/estudios/{est_1.id}/remuestreo", json=payload).status_code == 401

    # Paciente y Medico -> 403
    for u in (datos_remuestreo["u_pac_1"], datos_remuestreo["u_med"]):
        resp_forb = client.post(
            f"/api/v1/estudios/{est_1.id}/remuestreo",
            headers=_auth_header_para(app, u),
            json=payload,
        )
        assert resp_forb.status_code == 403
        assert resp_forb.get_json()["code"] == "ROL_NO_AUTORIZADO"

    # Estudio inexistente -> 404
    assert (
        client.post("/api/v1/estudios/99999/remuestreo", headers=headers_admin, json=payload).status_code
        == 404
    )

    # TC-05: Estudio en bioinformatica -> 409 ESTADO_ESTUDIO_INVALIDO_PARA_REMUESTREO
    resp_bio = client.post(
        f"/api/v1/estudios/{est_bio.id}/remuestreo",
        headers=headers_admin,
        json=payload,
    )
    assert resp_bio.status_code == 409
    assert resp_bio.get_json()["code"] == "ESTADO_ESTUDIO_INVALIDO_PARA_REMUESTREO"

    # Estudio en EN_LAB_CENTRAL sin muestra vigente -> 409 SIN_MUESTRA_VIGENTE
    est_sin_muestra = Estudio(
        paciente_id=datos_remuestreo["est_2"].paciente_id,
        medico_id=est_1.medico_id,
        patologia_sospechada_id=est_1.patologia_sospechada_id,
        estado=EstadoEstudio.EN_LAB_CENTRAL,
    )
    session.add(est_sin_muestra)
    session.commit()

    resp_sin_m = client.post(
        f"/api/v1/estudios/{est_sin_muestra.id}/remuestreo",
        headers=headers_admin,
        json=payload,
    )
    assert resp_sin_m.status_code == 409
    assert resp_sin_m.get_json()["code"] == "SIN_MUESTRA_VIGENTE"


def test_rollback_si_falla_envio_email(app, client, session, datos_remuestreo):
    """Si EmailClient falla, revierte estado, motivo_descarte, auditoria y avisos (502 retryable)."""
    est_1 = datos_remuestreo["est_1"]
    muestra_1 = datos_remuestreo["muestra_1"]
    headers_admin = _auth_header_para(app, datos_remuestreo["u_admin"])

    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.side_effect = ClienteServicioError("API email caida", codigo_http=503)
    app.config["EMAIL_CLIENT"] = mock_email

    resp = client.post(
        f"/api/v1/estudios/{est_1.id}/remuestreo",
        headers=headers_admin,
        json={"motivo_descarte": "baja_calidad", "motivo": "Muestra no apta"},
    )
    assert resp.status_code == 502
    assert resp.get_json()["retryable"] is True

    session.refresh(est_1)
    session.refresh(muestra_1)
    assert est_1.estado == EstadoEstudio.EN_VIAJE_COREA
    assert muestra_1.motivo_descarte is None
    assert (
        session.scalar(
            select(RegistroModificacion).where(
                RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
                RegistroModificacion.entidad_id == est_1.id,
            )
        )
        is None
    )
