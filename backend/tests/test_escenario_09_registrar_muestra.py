"""Tests integrales para el registro de toma de muestras por el Administrativo (Escenario 9)."""
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select
from src.core.models import (
    Aviso,
    CanalAviso,
    CentroExtraccion,
    EstadoEstudio,
    Estudio,
    Medico,
    MotivoDescarte,
    Muestra,
    Paciente,
    Patologia,
    Rol,
    Turno,
    Usuario,
)
from src.core.repos.logistica_repo import LogisticaRepo
from src.core.services.ausencia_service import AusenciaService
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


@pytest.fixture
def datos_toma_muestra(session):
    """Prepara centros, medico, pacientes, estudios en Turno sacado y un administrativo."""
    centro_1 = CentroExtraccion(
        nombre="Centro Norte",
        direccion="Av. Santa Fe 3200",
        provincia="Buenos Aires",
        latitud=-34.5885,
        longitud=-58.4105,
    )
    centro_2 = CentroExtraccion(
        nombre="Centro Sur",
        direccion="Av. Mitre 850",
        provincia="Buenos Aires",
        latitud=-34.6611,
        longitud=-58.3647,
    )
    patologia = Patologia(nombre="Pompe", descripcion="Enfermedad de Pompe")

    u_admin = Usuario(
        email="admin.muestras@lab.com",
        password_hash="hash",
        rol=Rol.ADMINISTRATIVO,
        nombre="Sofia",
        apellido="Ruiz",
        telefono="11445566",
    )
    u_med = Usuario(
        email="medico.muestras@hospital.com",
        password_hash="hash",
        rol=Rol.MEDICO,
        nombre="Laura",
        apellido="Mendez",
        telefono="11223344",
    )
    u_pac_1 = Usuario(
        email="paciente1.muestras@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Martin",
        apellido="Gomez",
        telefono="11998877",
    )
    u_pac_2 = Usuario(
        email="paciente2.muestras@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Lucia",
        apellido="Fernandez",
        telefono="11665544",
    )
    session.add_all([centro_1, centro_2, patologia, u_admin, u_med, u_pac_1, u_pac_2])
    session.flush()

    medico = Medico(usuario_id=u_med.id, matricula="MP-90123")
    session.add(medico)
    session.flush()

    pac_1 = Paciente(
        usuario_id=u_pac_1.id,
        medico_id=medico.id,
        dni="30111222",
        fecha_nacimiento=date(1992, 5, 10),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-901",
        tipo_sospecha="Sospecha clinica",
    )
    pac_2 = Paciente(
        usuario_id=u_pac_2.id,
        medico_id=medico.id,
        dni="35999888",
        fecha_nacimiento=date(1996, 8, 20),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-902",
        tipo_sospecha="Sospecha familiar",
    )
    session.add_all([pac_1, pac_2])
    session.flush()

    est_1 = Estudio(
        paciente_id=pac_1.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.TURNO_SACADO,
        ausencias=0,
    )
    est_2 = Estudio(
        paciente_id=pac_2.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.TURNO_SACADO,
        ausencias=0,
    )
    est_creado = Estudio(
        paciente_id=pac_1.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.CREADO,
        ausencias=0,
    )
    session.add_all([est_1, est_2, est_creado])
    session.flush()

    hoy = date.today()
    manana = hoy + timedelta(days=1)

    turno_1 = Turno(
        centro_id=centro_1.id,
        paciente_id=pac_1.id,
        estudio_id=est_1.id,
        inicio=datetime.combine(hoy, time(10, 0)),
        activo=True,
        asistio=None,
    )
    turno_2 = Turno(
        centro_id=centro_2.id,
        paciente_id=pac_2.id,
        estudio_id=est_2.id,
        inicio=datetime.combine(manana, time(11, 15)),
        activo=True,
        asistio=None,
    )
    turno_cancelado = Turno(
        centro_id=centro_1.id,
        paciente_id=pac_1.id,
        estudio_id=est_1.id,
        inicio=datetime.combine(hoy, time(9, 0)),
        activo=False,
        asistio=None,
    )
    session.add_all([turno_1, turno_2, turno_cancelado])
    session.commit()

    return {
        "centro_1": centro_1,
        "centro_2": centro_2,
        "u_admin": u_admin,
        "u_med": u_med,
        "u_pac_1": u_pac_1,
        "pac_1": pac_1,
        "pac_2": pac_2,
        "est_1": est_1,
        "est_2": est_2,
        "est_creado": est_creado,
        "turno_1": turno_1,
        "turno_2": turno_2,
        "turno_cancelado": turno_cancelado,
    }


def test_listar_turnos_pendientes_toma_y_filtros(app, client, datos_toma_muestra):
    """El administrativo ve solo turnos activos en Turno sacado y puede filtrar."""
    headers = _auth_header_para(app, datos_toma_muestra["u_admin"])

    resp = client.get("/api/v1/muestras/pendientes", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert len(data) == 2
    assert {item["turno_id"] for item in data} == {
        datos_toma_muestra["turno_1"].id,
        datos_toma_muestra["turno_2"].id,
    }

    # Filtro por DNI
    resp_dni = client.get("/api/v1/muestras/pendientes?dni=30111222", headers=headers)
    assert resp_dni.status_code == 200
    assert len(resp_dni.get_json()["data"]) == 1
    assert resp_dni.get_json()["data"][0]["paciente_nombre"] == "Martin Gomez"

    # Filtro por centro_id
    c2_id = datos_toma_muestra["centro_2"].id
    resp_centro = client.get(f"/api/v1/muestras/pendientes?centro_id={c2_id}", headers=headers)
    assert resp_centro.status_code == 200
    assert len(resp_centro.get_json()["data"]) == 1
    assert resp_centro.get_json()["data"][0]["turno_id"] == datos_toma_muestra["turno_2"].id

    # Filtro invalido devuelve 422
    resp_err = client.get("/api/v1/muestras/pendientes?fecha=fecha-invalida", headers=headers)
    assert resp_err.status_code == 422


def test_registrar_toma_muestra_exitoso(app, client, session, datos_toma_muestra):
    """Registra muestra, marca asistencia, pasa a Lista para retirar y notifica."""
    headers = _auth_header_para(app, datos_toma_muestra["u_admin"])
    turno = datos_toma_muestra["turno_1"]
    estudio = datos_toma_muestra["est_1"]

    resp = client.post(
        f"/api/v1/muestras/turnos/{turno.id}/toma",
        headers=headers,
        json={},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["ok"] is True
    assert body["data"]["estudio_id"] == estudio.id
    assert body["data"]["turno_id"] == turno.id
    assert body["data"]["asistio"] is True
    assert body["data"]["estado_estudio"] == EstadoEstudio.LISTA_PARA_RETIRAR.value

    session.refresh(turno)
    session.refresh(estudio)
    assert turno.asistio is True
    assert estudio.estado == EstadoEstudio.LISTA_PARA_RETIRAR

    muestra = session.execute(
        select(Muestra).where(Muestra.turno_id == turno.id)
    ).scalar_one()
    assert muestra.tomada_en is not None
    assert muestra.motivo_descarte is None
    assert muestra.mililitros is None  # Sin regla de volumen minimo (ADR-004)

    aviso = session.execute(
        select(Aviso).where(Aviso.usuario_id == datos_toma_muestra["u_pac_1"].id)
    ).scalar_one()
    assert aviso.canal == CanalAviso.APP
    assert "Lista para retirar" in aviso.mensaje


def test_registrar_toma_con_fecha_explicita_e_invalida(app, client, session, datos_toma_muestra):
    """Acepta tomada_en ISO-8601 valido y rechaza formato invalido con 422."""
    headers = _auth_header_para(app, datos_toma_muestra["u_admin"])
    turno = datos_toma_muestra["turno_2"]

    resp_bad = client.post(
        f"/api/v1/muestras/turnos/{turno.id}/toma",
        headers=headers,
        json={"tomada_en": "no-es-fecha"},
    )
    assert resp_bad.status_code == 422

    fecha_toma = "2026-11-18T11:15:00"
    resp_ok = client.post(
        f"/api/v1/muestras/turnos/{turno.id}/toma",
        headers=headers,
        json={"tomada_en": fecha_toma},
    )
    assert resp_ok.status_code == 201
    muestra = session.execute(
        select(Muestra).where(Muestra.turno_id == turno.id)
    ).scalar_one()
    assert muestra.tomada_en == datetime(2026, 11, 18, 11, 15, 0)


def test_rechazo_sin_sesion_y_por_rol_no_autorizado(app, client, datos_toma_muestra):
    """Solo el Administrativo puede listar pendientes y registrar toma de muestra."""
    turno_id = datos_toma_muestra["turno_1"].id

    assert client.get("/api/v1/muestras/pendientes").status_code == 401
    assert client.post(f"/api/v1/muestras/turnos/{turno_id}/toma").status_code == 401

    headers_paciente = _auth_header_para(app, datos_toma_muestra["u_pac_1"])
    headers_medico = _auth_header_para(app, datos_toma_muestra["u_med"])

    assert client.get("/api/v1/muestras/pendientes", headers=headers_paciente).status_code == 403
    assert (
        client.post(f"/api/v1/muestras/turnos/{turno_id}/toma", headers=headers_medico).status_code
        == 403
    )


def test_rechazo_doble_registro_turno_ya_tomado(app, client, session, datos_toma_muestra):
    """No permite registrar dos muestras para el mismo turno."""
    headers = _auth_header_para(app, datos_toma_muestra["u_admin"])
    turno_id = datos_toma_muestra["turno_1"].id

    primera = client.post(f"/api/v1/muestras/turnos/{turno_id}/toma", headers=headers, json={})
    assert primera.status_code == 201

    segunda = client.post(f"/api/v1/muestras/turnos/{turno_id}/toma", headers=headers, json={})
    assert segunda.status_code == 409

    muestras = session.execute(
        select(Muestra).where(Muestra.turno_id == turno_id)
    ).scalars().all()
    assert len(muestras) == 1


def test_rechazo_turno_inexistente_cancelado_ausente_o_estudio_invalido(
    app, client, session, datos_toma_muestra
):
    """Valida errores 404 y 409 ante estados inconsistentes."""
    headers = _auth_header_para(app, datos_toma_muestra["u_admin"])

    # Turno inexistente
    assert client.post("/api/v1/muestras/turnos/99999/toma", headers=headers).status_code == 404

    # Turno cancelado
    t_canc_id = datos_toma_muestra["turno_cancelado"].id
    assert (
        client.post(f"/api/v1/muestras/turnos/{t_canc_id}/toma", headers=headers).status_code
        == 409
    )

    # Turno ya marcado como ausente (Escenario 33)
    turno_2 = datos_toma_muestra["turno_2"]
    turno_2.activo = False
    turno_2.asistio = False
    session.commit()
    assert (
        client.post(f"/api/v1/muestras/turnos/{turno_2.id}/toma", headers=headers).status_code
        == 409
    )

    # Turno activo pero con estudio que no esta en Turno sacado
    turno_creado = Turno(
        centro_id=datos_toma_muestra["centro_1"].id,
        paciente_id=datos_toma_muestra["pac_1"].id,
        estudio_id=datos_toma_muestra["est_creado"].id,
        inicio=datetime.combine(date.today() + timedelta(days=2), time(14, 0)),
        activo=True,
        asistio=None,
    )
    session.add(turno_creado)
    session.commit()
    assert (
        client.post(f"/api/v1/muestras/turnos/{turno_creado.id}/toma", headers=headers).status_code
        == 409
    )


def test_toma_luego_de_remuestreo_requerido(app, client, session, datos_toma_muestra):
    """Tras una muestra descartada y un nuevo turno, registra la 2da muestra vigente."""
    headers = _auth_header_para(app, datos_toma_muestra["u_admin"])
    estudio = datos_toma_muestra["est_1"]
    turno_anterior = datos_toma_muestra["turno_cancelado"]

    muestra_descartada = Muestra(
        estudio_id=estudio.id,
        turno_id=turno_anterior.id,
        tomada_en=datetime.now() - timedelta(days=5),
        motivo_descarte=MotivoDescarte.ADN_INSUFICIENTE,
    )
    session.add(muestra_descartada)
    session.commit()

    resp = client.post(
        f"/api/v1/muestras/turnos/{datos_toma_muestra['turno_1'].id}/toma",
        headers=headers,
    )
    assert resp.status_code == 201

    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.LISTA_PARA_RETIRAR
    assert estudio.muestra_vigente is not None
    assert estudio.muestra_vigente.id == resp.get_json()["data"]["muestra_id"]
    assert estudio.muestra_vigente.id != muestra_descartada.id


def test_integracion_con_ausencias_y_logistica(app, client, session, datos_toma_muestra):
    """La toma registrada evita la ausencia a las 18:00 y habilita la orden del transportista."""
    headers = _auth_header_para(app, datos_toma_muestra["u_admin"])
    turno = datos_toma_muestra["turno_1"]
    estudio = datos_toma_muestra["est_1"]
    centro = datos_toma_muestra["centro_1"]

    # 1. Administrativo registra la toma durante el dia
    resp = client.post(f"/api/v1/muestras/turnos/{turno.id}/toma", headers=headers)
    assert resp.status_code == 201

    # 2. Al cierre de jornada (18:05), AusenciaService NO debe marcar ausencia para turno_1
    resumen = AusenciaService.procesar_turnos_vencidos(
        ahora=datetime.combine(date.today(), time(18, 5))
    )
    assert resumen["total_detectados"] == 0
    session.refresh(estudio)
    assert estudio.ausencias == 0

    # 3. Logistica detecta el centro listo para retirar por el transportista provincial
    centros_listos = LogisticaRepo.listar_centros_con_muestras_listas(centro.provincia)
    assert centro.id in [c.id for c in centros_listos]