"""Tests integrales para el flujo de Cancelar un Turno de Extraccion (Escenario 8)."""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from src.core.models import (
    Autorizacion,
    Aviso,
    CanalAviso,
    CentroExtraccion,
    EstadoEstudio,
    Estudio,
    Medico,
    MotivoDescarte,
    Muestra,
    Paciente,
    Pago,
    Patologia,
    Presupuesto,
    ResultadoAutorizacion,
    Rol,
    TipoPago,
    Turno,
    Usuario,
)
from src.core.services.seguridad import SCOPE_ACCESO_COMPLETO, emitir_token


@pytest.fixture
def datos_cancelacion(session):
    """Prepara Centro, Medico, Patologia, Paciente titular, otro paciente y Estudio con turno activo."""
    centro = CentroExtraccion(
        nombre="Laboratorio Rossi - Sede Belgrano",
        direccion="Av. Cabildo 2040",
        provincia="Buenos Aires",
        latitud=-34.5612,
        longitud=-58.4567,
    )
    patologia = Patologia(nombre="Fabry", descripcion="Enfermedad de Fabry")
    u_med = Usuario(
        email="medico.canc@hospital.com",
        password_hash="hash",
        rol=Rol.MEDICO,
        nombre="Carlos",
        apellido="Gomez",
        telefono="11223344",
    )
    u_pac = Usuario(
        email="paciente.canc@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Juan",
        apellido="Perez",
        telefono="11998877",
    )
    u_otro = Usuario(
        email="otro.canc@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Pedro",
        apellido="Lopez",
        telefono="11002233",
    )
    session.add_all([centro, patologia, u_med, u_pac, u_otro])
    session.flush()

    medico = Medico(usuario_id=u_med.id, matricula="MP-99881")
    session.add(medico)
    session.flush()

    paciente = Paciente(
        usuario_id=u_pac.id,
        medico_id=medico.id,
        dni="30111999",
        fecha_nacimiento=date(1990, 5, 20),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-801",
        tipo_sospecha="Sospecha clinica",
    )
    paciente_otro = Paciente(
        usuario_id=u_otro.id,
        medico_id=medico.id,
        dni="31222888",
        fecha_nacimiento=date(1992, 8, 10),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-802",
        tipo_sospecha="Antecedente familiar",
    )
    session.add_all([paciente, paciente_otro])
    session.flush()

    estudio = Estudio(
        paciente_id=paciente.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.TURNO_SACADO,
        ausencias=0,
    )
    session.add(estudio)
    session.flush()

    autorizacion = Autorizacion(
        estudio_id=estudio.id,
        resultado=ResultadoAutorizacion.AUTORIZADA,
    )
    inicio = _proximo_dia_habil(10, 15)
    turno = Turno(
        centro_id=centro.id,
        paciente_id=paciente.id,
        estudio_id=estudio.id,
        inicio=inicio,
        activo=True,
        asistio=None,
    )
    session.add_all([autorizacion, turno])
    session.commit()

    return {
        "centro": centro,
        "patologia": patologia,
        "medico": medico,
        "usuario_medico": u_med,
        "usuario_paciente": u_pac,
        "usuario_otro": u_otro,
        "paciente": paciente,
        "paciente_otro": paciente_otro,
        "estudio": estudio,
        "autorizacion": autorizacion,
        "turno": turno,
        "inicio": inicio,
    }


def _proximo_dia_habil(hora: int = 10, minuto: int = 15) -> datetime:
    """Devuelve el proximo dia habil (lunes a viernes, no feriado) en la hora y minuto indicados."""
    feriados_fijos = {(1, 1), (3, 24), (4, 2), (5, 1), (5, 25), (6, 20), (7, 9), (12, 8), (12, 25)}
    candidato = datetime.now() + timedelta(days=1)
    while candidato.weekday() >= 5 or (candidato.month, candidato.day) in feriados_fijos:
        candidato += timedelta(days=1)
    return candidato.replace(hour=hora, minute=minuto, second=0, microsecond=0)


def _auth_header_para(app, usuario: Usuario) -> dict[str, str]:
    """Genera cabecera Authorization con un Bearer token valido para el usuario."""
    token = emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return {"Authorization": f"Bearer {token}"}


def test_cancelar_turno_paciente_titular_obra_social(app, client, session, datos_cancelacion):
    """TC-01: Paciente titular cancela su turno activo de un estudio autorizado por obra social."""
    turno = datos_cancelacion["turno"]
    estudio = datos_cancelacion["estudio"]
    usuario_paciente = datos_cancelacion["usuario_paciente"]
    headers = _auth_header_para(app, usuario_paciente)

    res = client.post(f"/api/v1/turnos/{turno.id}/cancelar", json={}, headers=headers)
    assert res.status_code == 200

    body = res.get_json()
    assert body["ok"] is True
    data = body["data"]
    assert data == {
        "turno_id": turno.id,
        "estudio_id": estudio.id,
        "centro_id": datos_cancelacion["centro"].id,
        "inicio": datos_cancelacion["inicio"].isoformat(),
        "activo": False,
        "estado_estudio": EstadoEstudio.AUTORIZADO.value,
        "ausencias": 0,
        "puede_sacar_nuevo_turno": True,
    }

    session.refresh(turno)
    session.refresh(estudio)
    assert turno.activo is False
    assert turno.asistio is None
    assert estudio.estado == EstadoEstudio.AUTORIZADO
    assert estudio.ausencias == 0

    aviso = session.query(Aviso).filter_by(usuario_id=usuario_paciente.id).first()
    assert aviso is not None
    assert aviso.canal == CanalAviso.APP
    assert aviso.enviado is True
    assert "cancelado" in aviso.mensaje.lower()


def test_cancelar_turno_libera_slot_y_permite_sacar_nuevo_turno(
    app, client, session, datos_cancelacion
):
    """TC-02: Cancelar libera el slot y permite volver a reservar exactamente el mismo horario."""
    turno = datos_cancelacion["turno"]
    estudio = datos_cancelacion["estudio"]
    centro = datos_cancelacion["centro"]
    inicio = datos_cancelacion["inicio"]
    headers = _auth_header_para(app, datos_cancelacion["usuario_paciente"])

    res_cancel = client.post(f"/api/v1/turnos/{turno.id}/cancelar", headers=headers)
    assert res_cancel.status_code == 200

    fecha_str = inicio.strftime("%Y-%m-%d")
    res_disp = client.get(
        f"/api/v1/centros-extraccion/{centro.id}/turnos-disponibles?fecha={fecha_str}",
        headers=headers,
    )
    assert res_disp.status_code == 200
    assert inicio.isoformat() in res_disp.get_json()["data"]["slots_libres"]

    res_nuevo = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": inicio.isoformat()},
        headers=headers,
    )
    assert res_nuevo.status_code == 201
    nuevo_turno_id = res_nuevo.get_json()["data"]["turno_id"]
    assert nuevo_turno_id != turno.id

    nuevo_turno = session.get(Turno, nuevo_turno_id)
    assert nuevo_turno is not None
    assert nuevo_turno.activo is True
    assert nuevo_turno.inicio == inicio


def test_cancelar_turno_estudio_en_remuestreo_vuelve_a_remuestreo_requerido(
    app, client, session, datos_cancelacion
):
    """TC-03: Si el estudio proviene de una muestra descartada sin muestra vigente, vuelve a REMUESTREO_REQUERIDO."""
    estudio = datos_cancelacion["estudio"]
    turno = datos_cancelacion["turno"]
    muestra_descartada = Muestra(
        estudio_id=estudio.id,
        motivo_descarte=MotivoDescarte.ADN_INSUFICIENTE,
    )
    session.add(muestra_descartada)
    session.commit()

    headers = _auth_header_para(app, datos_cancelacion["usuario_paciente"])
    res = client.post(f"/api/v1/turnos/{turno.id}/cancelar", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["data"]["estado_estudio"] == EstadoEstudio.REMUESTREO_REQUERIDO.value

    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO


def test_cancelar_turno_estudio_pago_particular_vuelve_a_creado(
    app, client, session, datos_cancelacion
):
    """Estudio sin autorizacion y con pago particular vigente retorna a CREADO y sigue habilitado para reservar."""
    estudio = datos_cancelacion["estudio"]
    turno = datos_cancelacion["turno"]
    session.delete(datos_cancelacion["autorizacion"])
    presupuesto = Presupuesto(
        estudio_id=estudio.id,
        emitido_por_id=datos_cancelacion["usuario_paciente"].id,
        cantidad_genes=4,
        monto_total_usd=Decimal("950.00"),
    )
    session.add(presupuesto)
    session.flush()
    pago = Pago(
        presupuesto_id=presupuesto.id,
        tipo=TipoPago.PARTICULAR,
        monto_usd=Decimal("950.00"),
        anulado=False,
    )
    session.add(pago)
    session.commit()

    headers = _auth_header_para(app, datos_cancelacion["usuario_paciente"])
    res = client.post(f"/api/v1/turnos/{turno.id}/cancelar", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["data"]["estado_estudio"] == EstadoEstudio.CREADO.value

    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.CREADO

    nuevo_horario = _proximo_dia_habil(11, 30)
    res_nuevo = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": datos_cancelacion["centro"].id, "inicio": nuevo_horario.isoformat()},
        headers=headers,
    )
    assert res_nuevo.status_code == 201


def test_medico_no_puede_cancelar_turno(app, client, session, datos_cancelacion):
    """TC-04: El medico no puede cancelar un turno (403 Forbidden)."""
    turno = datos_cancelacion["turno"]
    estudio = datos_cancelacion["estudio"]
    headers_med = _auth_header_para(app, datos_cancelacion["usuario_medico"])

    res = client.post(f"/api/v1/turnos/{turno.id}/cancelar", headers=headers_med)
    assert res.status_code == 403
    assert res.get_json()["ok"] is False

    session.refresh(turno)
    session.refresh(estudio)
    assert turno.activo is True
    assert estudio.estado == EstadoEstudio.TURNO_SACADO


def test_otro_paciente_no_puede_cancelar_turno_ajeno(app, client, session, datos_cancelacion):
    """TC-05: Otro paciente autenticado no puede cancelar el turno de otro paciente (403 Forbidden)."""
    turno = datos_cancelacion["turno"]
    headers_otro = _auth_header_para(app, datos_cancelacion["usuario_otro"])

    res = client.post(f"/api/v1/turnos/{turno.id}/cancelar", headers=headers_otro)
    assert res.status_code == 403
    assert res.get_json()["ok"] is False

    session.refresh(turno)
    assert turno.activo is True


def test_cancelar_turno_inexistente_y_sin_autenticacion(app, client, datos_cancelacion):
    """Verifica 401 sin sesion y 404 cuando el turno_id no existe."""
    turno = datos_cancelacion["turno"]
    res_401 = client.post(f"/api/v1/turnos/{turno.id}/cancelar")
    assert res_401.status_code == 401

    headers_pac = _auth_header_para(app, datos_cancelacion["usuario_paciente"])
    res_404 = client.post("/api/v1/turnos/999999/cancelar", headers=headers_pac)
    assert res_404.status_code == 404
    assert res_404.get_json()["ok"] is False


def test_cancelar_turno_ya_cancelado_o_procesado_retorna_409(
    app, client, session, datos_cancelacion
):
    """TC-06: No permite cancelar si turno.activo=False, turno.asistio no es None o ya tiene Muestra."""
    turno = datos_cancelacion["turno"]
    estudio = datos_cancelacion["estudio"]
    headers_pac = _auth_header_para(app, datos_cancelacion["usuario_paciente"])

    # Caso A: Turno ya cancelado
    turno.activo = False
    session.commit()
    res_inactivo = client.post(f"/api/v1/turnos/{turno.id}/cancelar", headers=headers_pac)
    assert res_inactivo.status_code == 409

    # Caso B: Turno ya marcado con asistencia
    turno.activo = True
    turno.asistio = True
    session.commit()
    res_asistio = client.post(f"/api/v1/turnos/{turno.id}/cancelar", headers=headers_pac)
    assert res_asistio.status_code == 409

    # Caso C: Muestra asociada al turno / estudio ya avanzo
    turno.asistio = None
    muestra = Muestra(estudio_id=estudio.id, turno_id=turno.id)
    session.add(muestra)
    session.commit()
    res_muestra = client.post(f"/api/v1/turnos/{turno.id}/cancelar", headers=headers_pac)
    assert res_muestra.status_code == 409


def test_listar_mis_turnos_historial_y_estados(app, client, session, datos_cancelacion):
    """El paciente ve su historial completo de turnos (Confirmado, Cancelado, Ausente) con permisos."""
    turno_actual = datos_cancelacion["turno"]
    estudio = datos_cancelacion["estudio"]
    centro = datos_cancelacion["centro"]
    headers_pac = _auth_header_para(app, datos_cancelacion["usuario_paciente"])
    headers_otro = _auth_header_para(app, datos_cancelacion["usuario_otro"])
    headers_med = _auth_header_para(app, datos_cancelacion["usuario_medico"])

    # Rol no paciente -> 403; otro paciente -> lista vacia
    assert client.get("/api/v1/turnos/mis-turnos", headers=headers_med).status_code == 403
    res_otro = client.get("/api/v1/turnos/mis-turnos", headers=headers_otro)
    assert res_otro.status_code == 200
    assert res_otro.get_json()["data"] == []

    # Agregamos un turno previo marcado como ausente en el historial
    turno_ausente = Turno(
        centro_id=centro.id,
        paciente_id=datos_cancelacion["paciente"].id,
        estudio_id=estudio.id,
        inicio=datos_cancelacion["inicio"] - timedelta(days=3),
        activo=False,
        asistio=False,
    )
    session.add(turno_ausente)
    session.commit()

    # Antes de cancelar el turno activo
    res_antes = client.get("/api/v1/turnos/mis-turnos", headers=headers_pac)
    assert res_antes.status_code == 200
    items = res_antes.get_json()["data"]
    assert len(items) == 2
    assert items[0]["turno_id"] == turno_actual.id
    assert items[0]["estado_turno"] == "Confirmado"
    assert items[0]["puede_cancelar"] is True
    assert items[0]["centro"]["nombre"] == centro.nombre

    assert items[1]["turno_id"] == turno_ausente.id
    assert items[1]["estado_turno"] == "Ausente"
    assert items[1]["puede_cancelar"] is False

    # Cancelar turno actual y verificar que pasa a Cancelado en el historial
    assert client.post(f"/api/v1/turnos/{turno_actual.id}/cancelar", headers=headers_pac).status_code == 200
    res_despues = client.get("/api/v1/turnos/mis-turnos", headers=headers_pac)
    items_despues = res_despues.get_json()["data"]
    assert items_despues[0]["estado_turno"] == "Cancelado"
    assert items_despues[0]["puede_cancelar"] is False
