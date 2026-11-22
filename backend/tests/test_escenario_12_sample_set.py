"""Tests integrales para Escenario 12: Formar un sample-set de muestras (via llegada transportista)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from src.core.models import (
    Aviso,
    CanalAviso,
    CentroExtraccion,
    EntidadAuditable,
    EstadoEstudio,
    EstadoSampleSet,
    Estudio,
    Medico,
    Muestra,
    OrdenDelDia,
    OrdenDelDiaParada,
    Paciente,
    Patologia,
    RegistroModificacion,
    Rol,
    SampleSet,
    TipoAccionAuditoria,
    Transportista,
    Turno,
    Usuario,
)
from src.core.services.excepciones import ErrorConflicto
from src.core.services.sample_set_service import SampleSetService
from src.core.services.seguridad import SCOPE_ACCESO_COMPLETO, emitir_token


def _auth_header_para(app, usuario: Usuario) -> dict[str, str]:
    token = emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return {"Authorization": f"Bearer {token}"}


def _preparar_actores(session) -> dict:
    """Crea o reutiliza administrativo, medico, centro y transportista base para tests."""
    patologia = session.scalar(select(Patologia).where(Patologia.nombre == "Enfermedad de Fabry"))
    if patologia is None:
        patologia = Patologia(nombre="Enfermedad de Fabry", descripcion="Patologia lisosomal")
        session.add(patologia)

    centro = session.scalar(select(CentroExtraccion).where(CentroExtraccion.nombre == "Centro Lab 12"))
    if centro is None:
        centro = CentroExtraccion(
            nombre="Centro Lab 12",
            direccion="Calle 7 Nro 120",
            provincia="Buenos Aires",
            latitud=-34.92,
            longitud=-57.95,
        )
        session.add(centro)

    u_admin = session.scalar(select(Usuario).where(Usuario.email == "admin.ss12@lab.com"))
    if u_admin is None:
        u_admin = Usuario(
            email="admin.ss12@lab.com",
            password_hash="hash",
            rol=Rol.ADMINISTRATIVO,
            nombre="Sofia",
            apellido="Admin",
            telefono="11445500",
        )
        session.add(u_admin)

    u_med = session.scalar(select(Usuario).where(Usuario.email == "med.ss12@lab.com"))
    if u_med is None:
        u_med = Usuario(
            email="med.ss12@lab.com",
            password_hash="hash",
            rol=Rol.MEDICO,
            nombre="Carlos",
            apellido="Medico",
            telefono="11445501",
        )
        session.add(u_med)

    u_transp = session.scalar(select(Usuario).where(Usuario.email == "transp.ss12@lab.com"))
    if u_transp is None:
        u_transp = Usuario(
            email="transp.ss12@lab.com",
            password_hash="hash",
            rol=Rol.TRANSPORTISTA,
            nombre="Lucas",
            apellido="Transp",
            telefono="11778899",
        )
        session.add(u_transp)
    session.flush()

    medico = session.scalar(select(Medico).where(Medico.usuario_id == u_med.id))
    if medico is None:
        medico = Medico(usuario_id=u_med.id, matricula="MN-12001")
        session.add(medico)

    transp = session.scalar(select(Transportista).where(Transportista.usuario_id == u_transp.id))
    if transp is None:
        transp = Transportista(usuario_id=u_transp.id, provincia="Buenos Aires")
        session.add(transp)
    session.flush()

    return {
        "patologia": patologia,
        "centro": centro,
        "u_admin": u_admin,
        "u_med": u_med,
        "u_transp": u_transp,
        "medico": medico,
        "transp": transp,
    }


def _crear_viaje_retirado(
    session,
    *,
    cantidad: int,
    fecha_orden: date,
    es_pompe_urgente: bool = False,
    mililitros: Decimal | None = None,
    estado_inicial: EstadoEstudio = EstadoEstudio.EN_CAMINO_LAB_CENTRAL,
) -> dict:
    """Crea muestras ya retiradas del centro y su OrdenDelDia lista para confirmar llegada."""
    base = _preparar_actores(session)
    base_idx = session.query(Paciente).count() + 1
    ahora = datetime.now()
    muestras: list[Muestra] = []
    estudios: list[Estudio] = []

    for i in range(cantidad):
        idx = base_idx + i
        u_pac = Usuario(
            email=f"pac.ss12.{idx}@mail.com",
            password_hash="hash",
            rol=Rol.PACIENTE,
            nombre="Paciente",
            apellido=f"Nro{idx}",
            telefono=f"119900{idx:03d}",
        )
        session.add(u_pac)
        session.flush()

        pac = Paciente(
            usuario_id=u_pac.id,
            medico_id=base["medico"].id,
            dni=f"500{idx:05d}",
            fecha_nacimiento=date(2026, 10, 1) if es_pompe_urgente else date(1990, 5, 10),
            diagnostico_presuntivo_id=base["patologia"].id,
            historia_clinica=f"HC-{idx}",
            tipo_sospecha="clinica",
        )
        session.add(pac)
        session.flush()

        est = Estudio(
            paciente_id=pac.id,
            medico_id=base["medico"].id,
            patologia_sospechada_id=base["patologia"].id,
            estado=estado_inicial,
            es_pompe_urgente=es_pompe_urgente,
        )
        session.add(est)
        session.flush()

        turno = Turno(
            centro_id=base["centro"].id,
            paciente_id=pac.id,
            estudio_id=est.id,
            inicio=ahora - timedelta(hours=3),
            activo=False,
            asistio=True,
        )
        session.add(turno)
        session.flush()

        muestra = Muestra(
            estudio_id=est.id,
            turno_id=turno.id,
            mililitros=mililitros,
            tomada_en=ahora - timedelta(hours=2),
        )
        session.add(muestra)
        session.flush()
        muestras.append(muestra)
        estudios.append(est)

    orden = OrdenDelDia(transportista_id=base["transp"].id, fecha=fecha_orden)
    session.add(orden)
    session.flush()
    session.add(
        OrdenDelDiaParada(
            orden_id=orden.id,
            centro_id=base["centro"].id,
            posicion=1,
            retirada_en=ahora - timedelta(minutes=30),
        )
    )
    session.commit()
    return {
        **base,
        "orden": orden,
        "muestras": muestras,
        "estudios": estudios,
    }


def test_tc01_y_tc02_creacion_y_acumulacion_sin_cerrar_y_sin_regla_2ml(app, client, session):
    """TC-01 + TC-02: Llegada de <10 muestras crea SampleSet abierto sin validar ml ni descarte."""
    datos = _crear_viaje_retirado(
        session,
        cantidad=9,
        fecha_orden=date(2026, 11, 17),
        mililitros=Decimal("0.80"),
    )
    headers_transp = _auth_header_para(app, datos["u_transp"])

    resp = client.post(
        f"/api/logistica/ordenes-del-dia/{datos['orden'].id}/llegada-laboratorio-central",
        headers=headers_transp,
        json={},
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert len(data["muestras_recibidas_ids"]) == 9
    assert len(data["sample_sets_afectados_ids"]) == 1

    lotes = session.scalars(select(SampleSet)).all()
    assert len(lotes) == 1
    assert lotes[0].id == data["sample_sets_afectados_ids"][0]
    assert lotes[0].estado == EstadoSampleSet.ABIERTO
    assert lotes[0].cerrado_en is None
    assert len(lotes[0].muestras) == 9

    for est in datos["estudios"]:
        session.refresh(est)
        assert est.estado == EstadoEstudio.EN_LAB_CENTRAL

    regs_ss = session.scalars(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.SAMPLE_SET,
            RegistroModificacion.entidad_id == lotes[0].id,
        )
    ).all()
    assert any(r.accion == TipoAccionAuditoria.CREACION for r in regs_ss)
    assert len([r for r in regs_ss if r.accion == TipoAccionAuditoria.MODIFICACION]) == 9


def test_tc03_cierre_automatico_al_decimo_auditoria_y_aviso_admin(app, client, session):
    """TC-03: Al llegar la 10ma muestra en otro viaje, cierra el lote, pasa a EN_ESPERA_RETIRO y avisa."""
    viaje_1 = _crear_viaje_retirado(session, cantidad=9, fecha_orden=date(2026, 11, 17))
    headers_transp = _auth_header_para(app, viaje_1["u_transp"])
    assert (
        client.post(
            f"/api/logistica/ordenes-del-dia/{viaje_1['orden'].id}/llegada-laboratorio-central",
            headers=headers_transp,
        ).status_code
        == 200
    )

    viaje_2 = _crear_viaje_retirado(session, cantidad=1, fecha_orden=date(2026, 11, 18))
    resp_2 = client.post(
        f"/api/logistica/ordenes-del-dia/{viaje_2['orden'].id}/llegada-laboratorio-central",
        headers=headers_transp,
    )
    assert resp_2.status_code == 200
    ss_id = resp_2.get_json()["data"]["sample_sets_afectados_ids"][0]

    lote = session.get(SampleSet, ss_id)
    assert lote is not None
    assert lote.estado == EstadoSampleSet.CERRADO
    assert lote.cerrado_en is not None
    assert len(lote.muestras) == 10

    for est in [*viaje_1["estudios"], *viaje_2["estudios"]]:
        session.refresh(est)
        assert est.estado == EstadoEstudio.EN_ESPERA_RETIRO

    avisos_admin = session.scalars(
        select(Aviso).where(
            Aviso.usuario_id == viaje_1["u_admin"].id,
            Aviso.canal == CanalAviso.APP,
        )
    ).all()
    assert any(f"SampleSet #{ss_id} cerrado (10/10" in a.mensaje for a in avisos_admin)

    reg_cierre = session.scalar(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.SAMPLE_SET,
            RegistroModificacion.entidad_id == ss_id,
            RegistroModificacion.accion == TipoAccionAuditoria.CAMBIO_ESTADO,
        )
    )
    assert reg_cierre is not None
    assert reg_cierre.cambios["estado"]["nuevo"] == EstadoSampleSet.CERRADO.value

    regs_estudios = session.scalars(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
            RegistroModificacion.accion == TipoAccionAuditoria.CAMBIO_ESTADO,
        )
    ).all()
    assert len(regs_estudios) == 10


def test_tc04_y_tc05_particion_multiples_lotes_e_inmutabilidad(app, client, session):
    """TC-04 + TC-05: 5 muestras sobre lote de 8 cierra #1 en 10 y abre #2 con 3 sin tocar el cerrado."""
    viaje_8 = _crear_viaje_retirado(session, cantidad=8, fecha_orden=date(2026, 11, 17))
    headers_transp = _auth_header_para(app, viaje_8["u_transp"])
    assert (
        client.post(
            f"/api/logistica/ordenes-del-dia/{viaje_8['orden'].id}/llegada-laboratorio-central",
            headers=headers_transp,
        ).status_code
        == 200
    )

    viaje_5 = _crear_viaje_retirado(session, cantidad=5, fecha_orden=date(2026, 11, 18))
    resp_5 = client.post(
        f"/api/logistica/ordenes-del-dia/{viaje_5['orden'].id}/llegada-laboratorio-central",
        headers=headers_transp,
    )
    assert resp_5.status_code == 200
    afectados = resp_5.get_json()["data"]["sample_sets_afectados_ids"]
    assert len(afectados) == 2

    lotes = session.scalars(select(SampleSet).order_by(SampleSet.id.asc())).all()
    assert len(lotes) == 2
    assert lotes[0].estado == EstadoSampleSet.CERRADO
    assert len(lotes[0].muestras) == 10
    assert lotes[1].estado == EstadoSampleSet.ABIERTO
    assert len(lotes[1].muestras) == 3

    for est in viaje_5["estudios"][:2]:
        session.refresh(est)
        assert est.estado == EstadoEstudio.EN_ESPERA_RETIRO
    for est in viaje_5["estudios"][2:]:
        session.refresh(est)
        assert est.estado == EstadoEstudio.EN_LAB_CENTRAL

    # Inmutabilidad: nuevas entregas jamas modifican el lote cerrado #1
    viaje_extra = _crear_viaje_retirado(session, cantidad=1, fecha_orden=date(2026, 11, 19))
    assert (
        client.post(
            f"/api/logistica/ordenes-del-dia/{viaje_extra['orden'].id}/llegada-laboratorio-central",
            headers=headers_transp,
        ).status_code
        == 200
    )
    session.refresh(lotes[0])
    session.refresh(lotes[1])
    assert len(lotes[0].muestras) == 10
    assert len(lotes[1].muestras) == 4


def test_cierre_inmediato_por_pompe_urgente_con_lote_parcial(app, client, session):
    """Pompe urgente aprovecha muestras abiertas y cierra inmediatamente el lote parcial."""
    viaje_3 = _crear_viaje_retirado(
        session,
        cantidad=3,
        fecha_orden=date(2026, 11, 17),
        es_pompe_urgente=False,
    )
    headers_transp = _auth_header_para(app, viaje_3["u_transp"])
    assert (
        client.post(
            f"/api/logistica/ordenes-del-dia/{viaje_3['orden'].id}/llegada-laboratorio-central",
            headers=headers_transp,
        ).status_code
        == 200
    )

    viaje_pompe = _crear_viaje_retirado(
        session,
        cantidad=1,
        fecha_orden=date(2026, 11, 18),
        es_pompe_urgente=True,
    )
    resp = client.post(
        f"/api/logistica/ordenes-del-dia/{viaje_pompe['orden'].id}/llegada-laboratorio-central",
        headers=headers_transp,
    )
    assert resp.status_code == 200
    ss_id = resp.get_json()["data"]["sample_sets_afectados_ids"][0]
    lote = session.get(SampleSet, ss_id)
    assert lote is not None
    assert lote.estado == EstadoSampleSet.CERRADO
    assert lote.es_pompe_urgente is True
    assert len(lote.muestras) == 4

    for est in [*viaje_3["estudios"], *viaje_pompe["estudios"]]:
        session.refresh(est)
        assert est.estado == EstadoEstudio.EN_ESPERA_RETIRO


def test_tc06_estado_invalido_idempotencia_y_consulta_endpoints(app, client, session):
    """TC-06 + consultas: rechaza estudio no EN_LAB_CENTRAL, es idempotente y restringe consulta a admin."""
    viaje_bad = _crear_viaje_retirado(
        session,
        cantidad=1,
        fecha_orden=date(2026, 11, 16),
        estado_inicial=EstadoEstudio.TURNO_SACADO,
    )
    with pytest.raises(ErrorConflicto) as exc_info:
        SampleSetService.armar_sample_set_para_muestras_recibidas([viaje_bad["muestras"][0].id])
    assert exc_info.value.codigo == "MUESTRA_NO_APTA_PARA_SAMPLE_SET"

    viaje_ok = _crear_viaje_retirado(session, cantidad=1, fecha_orden=date(2026, 11, 17))
    resp_ok = client.post(
        f"/api/logistica/ordenes-del-dia/{viaje_ok['orden'].id}/llegada-laboratorio-central",
        headers=_auth_header_para(app, viaje_ok["u_transp"]),
    )
    assert resp_ok.status_code == 200
    ss_id = resp_ok.get_json()["data"]["sample_sets_afectados_ids"][0]
    m_id = viaje_ok["muestras"][0].id

    # Reinvocacion directa sobre muestra ya asignada resulta idempotente
    assert SampleSetService.armar_sample_set_para_muestras_recibidas([m_id]) == [ss_id]
    lote = session.get(SampleSet, ss_id)
    assert lote is not None and len(lote.muestras) == 1

    # Endpoints GET /api/sample-sets y /api/sample-sets/<id>
    headers_admin = _auth_header_para(app, viaje_ok["u_admin"])
    headers_med = _auth_header_para(app, viaje_ok["u_med"])
    headers_transp = _auth_header_para(app, viaje_ok["u_transp"])

    assert client.get("/api/sample-sets", headers=headers_med).status_code == 403
    assert client.get("/api/sample-sets", headers=headers_transp).status_code == 403
    assert client.get("/api/sample-sets?estado=invalido", headers=headers_admin).status_code == 422

    r_list = client.get("/api/sample-sets?estado=abierto", headers=headers_admin)
    assert r_list.status_code == 200
    lotes = r_list.get_json()["sample_sets"]
    assert len(lotes) == 1
    assert lotes[0]["id"] == ss_id
    assert lotes[0]["cantidad_muestras"] == 1
    assert lotes[0]["muestras_ids"] == [m_id]

    r_det = client.get(f"/api/sample-sets/{ss_id}", headers=headers_admin)
    assert r_det.status_code == 200
    assert r_det.get_json()["sample_set"]["muestras"][0]["muestra_id"] == m_id
    assert client.get("/api/sample-sets/99999", headers=headers_admin).status_code == 404
