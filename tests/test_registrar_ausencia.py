"""Tests integrales para el flujo automatico de Ausentarse a un Turno (Escenario 33)."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from src.clients import EmailClient
from src.clients.exceptions import ClienteConexionError
from src.core.models import (
    Aviso,
    CentroExtraccion,
    EstadoEstudio,
    Estudio,
    Medico,
    Muestra,
    Paciente,
    Pago,
    Patologia,
    Presupuesto,
    Rol,
    TipoPago,
    Turno,
    Usuario,
)
from src.core.services.ausencia_service import AusenciaService
from src.core.services.seguridad import SCOPE_ACCESO_COMPLETO, emitir_token


def _proximo_dia_habil_10am() -> datetime:
    """Devuelve la fecha del proximo dia habil (lunes a viernes) a las 10:00."""
    fecha = (datetime.now() + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    while fecha.weekday() >= 5:
        fecha += timedelta(days=1)
    return fecha


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


@pytest.fixture
def datos_ausencia(session):
    """Prepara Centro, Medico, Patologia, Paciente, usuarios administrativos y Estudio con turno vencido."""
    centro = CentroExtraccion(
        nombre="Laboratorio Central - Sede Norte",
        direccion="Av. Santa Fe 3200",
        provincia="Buenos Aires",
        latitud=-34.5885,
        longitud=-58.4105,
    )
    patologia = Patologia(nombre="Pompe", descripcion="Enfermedad de Pompe")
    u_med = Usuario(
        email="medico.aus@hospital.com",
        password_hash="hash",
        rol=Rol.MEDICO,
        nombre="Laura",
        apellido="Mendez",
        telefono="11223344",
    )
    u_pac = Usuario(
        email="paciente.aus@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Martin",
        apellido="Gomez",
        telefono="11998877",
    )
    u_admin = Usuario(
        email="admin.aus@lab.com",
        password_hash="hash",
        rol=Rol.ADMINISTRATIVO,
        nombre="Sofia",
        apellido="Ruiz",
        telefono="11445566",
    )
    u_admin_gral = Usuario(
        email="admingral.aus@lab.com",
        password_hash="hash",
        rol=Rol.ADMIN_GENERAL,
        nombre="Diego",
        apellido="Torres",
        telefono="11778899",
    )
    session.add_all([centro, patologia, u_med, u_pac, u_admin, u_admin_gral])
    session.flush()

    medico = Medico(usuario_id=u_med.id, matricula="MP-77881")
    session.add(medico)
    session.flush()

    paciente = Paciente(
        usuario_id=u_pac.id,
        medico_id=medico.id,
        dni="33445566",
        fecha_nacimiento=date(1991, 4, 15),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-3301",
        tipo_sospecha="Sospecha clinica",
    )
    session.add(paciente)
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

    presupuesto = Presupuesto(
        estudio_id=estudio.id,
        emitido_por_id=u_admin.id,
        cantidad_genes=12,
        monto_total_usd=Decimal("150.00"),
    )
    session.add(presupuesto)
    session.flush()

    pago = Pago(
        presupuesto_id=presupuesto.id,
        tipo=TipoPago.PARTICULAR,
        monto_usd=Decimal("150.00"),
        anulado=False,
    )
    session.add(pago)
    session.flush()

    turno = Turno(
        centro_id=centro.id,
        paciente_id=paciente.id,
        estudio_id=estudio.id,
        inicio=datetime.now() - timedelta(minutes=20),
        activo=True,
        asistio=None,
    )
    session.add(turno)
    session.commit()

    return {
        "centro": centro,
        "patologia": patologia,
        "medico": medico,
        "paciente": paciente,
        "usuario_paciente": u_pac,
        "usuario_administrativo": u_admin,
        "usuario_admin_general": u_admin_gral,
        "estudio": estudio,
        "presupuesto": presupuesto,
        "pago": pago,
        "turno": turno,
    }


def test_primera_ausencia_notifica_por_mail_y_habilita_nuevo_turno(
    app, client, session, datos_ausencia
):
    """TC-01: Primera ausencia (0->1) conserva pago, notifica solo por EmailClient y habilita re-agendar."""
    mock_email = MagicMock(spec=EmailClient)
    turno = datos_ausencia["turno"]
    estudio = datos_ausencia["estudio"]
    pago = datos_ausencia["pago"]

    resumen = AusenciaService.procesar_turnos_vencidos(ahora=datetime.now(), email_client=mock_email)
    assert resumen["total_detectados"] == 1
    assert resumen["total_procesados"] == 1
    assert resumen["errores"] == []

    data = resumen["procesados"][0]
    assert data["turno_id"] == turno.id
    assert data["ausencias_acumuladas"] == 1
    assert data["pago_perdido"] is False
    assert data["pago_anulado_id"] is None
    assert data["estado_estudio"] == EstadoEstudio.TURNO_SACADO.value
    assert data["puede_sacar_nuevo_turno"] is True
    assert data["requiere_nuevo_pago"] is False

    session.refresh(turno)
    session.refresh(estudio)
    session.refresh(pago)
    assert turno.asistio is False
    assert turno.activo is False
    assert estudio.ausencias == 1
    assert estudio.estado == EstadoEstudio.TURNO_SACADO
    assert pago.anulado is False

    # Notificacion exclusiva por EmailClient, sin crear filas en avisos
    mock_email.enviar_aviso.assert_called_once()
    kwargs = mock_email.enviar_aviso.call_args.kwargs
    assert kwargs["destinatarios"] == [datos_ausencia["usuario_paciente"].email]
    assert kwargs["idempotency_key"] == f"ausencia-turno-{turno.id}"
    assert session.query(Aviso).count() == 0

    # El paciente puede sacar un nuevo turno sin volver a pagar
    nuevo_inicio = _proximo_dia_habil_10am().isoformat()
    res_nuevo = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": datos_ausencia["centro"].id, "inicio": nuevo_inicio},
        headers=_auth_header_para(app, datos_ausencia["usuario_paciente"]),
    )
    assert res_nuevo.status_code == 201


def test_cuarta_ausencia_mantiene_pago_y_estudio_listo_para_quinto_turno(
    app, session, datos_ausencia
):
    """TC-02: Cuarta ausencia (3->4) conserva pago vigente y deja estudio en TURNO_SACADO."""
    estudio = datos_ausencia["estudio"]
    pago = datos_ausencia["pago"]
    estudio.ausencias = 3
    session.commit()

    mock_email = MagicMock(spec=EmailClient)
    resumen = AusenciaService.procesar_turnos_vencidos(ahora=datetime.now(), email_client=mock_email)
    assert resumen["total_procesados"] == 1

    data = resumen["procesados"][0]
    assert data["ausencias_acumuladas"] == 4
    assert data["pago_perdido"] is False
    assert data["estado_estudio"] == EstadoEstudio.TURNO_SACADO.value
    assert data["puede_sacar_nuevo_turno"] is True
    assert data["requiere_nuevo_pago"] is False

    session.refresh(estudio)
    session.refresh(pago)
    assert estudio.ausencias == 4
    assert pago.anulado is False
    mock_email.enviar_aviso.assert_called_once()


def test_quinta_ausencia_anula_pago_y_vuelve_estudio_a_creado(
    app, session, datos_ausencia
):
    """TC-03: Quinta ausencia (4->5) anula el pago activo, vuelve a CREADO y notifica por mail."""
    estudio = datos_ausencia["estudio"]
    pago = datos_ausencia["pago"]
    turno = datos_ausencia["turno"]
    estudio.ausencias = 4
    session.commit()

    mock_email = MagicMock(spec=EmailClient)
    resumen = AusenciaService.procesar_turnos_vencidos(ahora=datetime.now(), email_client=mock_email)
    assert resumen["total_procesados"] == 1

    data = resumen["procesados"][0]
    assert data["ausencias_acumuladas"] == 5
    assert data["pago_perdido"] is True
    assert data["pago_anulado_id"] == pago.id
    assert data["estado_estudio"] == EstadoEstudio.CREADO.value
    assert data["puede_sacar_nuevo_turno"] is False
    assert data["requiere_nuevo_pago"] is True

    session.refresh(turno)
    session.refresh(estudio)
    session.refresh(pago)
    assert turno.asistio is False
    assert turno.activo is False
    assert estudio.ausencias == 5
    assert estudio.estado == EstadoEstudio.CREADO
    assert pago.anulado is True

    mock_email.enviar_aviso.assert_called_once()
    assert "pago anterior fue anulado" in mock_email.enviar_aviso.call_args.kwargs["mensaje"].lower()


def test_quinta_ausencia_obra_social_sin_pago_vuelve_a_creado_y_bloquea_turno(
    app, client, session, datos_ausencia
):
    """TC-04: Quinta ausencia sin Pago (obra social) pasa a CREADO e impide sacar otro turno (409)."""
    estudio = datos_ausencia["estudio"]
    pago = datos_ausencia["pago"]
    session.delete(pago)
    estudio.ausencias = 4
    session.commit()

    mock_email = MagicMock(spec=EmailClient)
    resumen = AusenciaService.procesar_turnos_vencidos(ahora=datetime.now(), email_client=mock_email)
    assert resumen["total_procesados"] == 1
    data = resumen["procesados"][0]
    assert data["ausencias_acumuladas"] == 5
    assert data["pago_perdido"] is False
    assert data["pago_anulado_id"] is None
    assert data["estado_estudio"] == EstadoEstudio.CREADO.value
    assert data["requiere_nuevo_pago"] is True

    # Intentar sacar nuevo turno estando en CREADO debe rechazarse con 409 Conflict
    nuevo_inicio = _proximo_dia_habil_10am().isoformat()
    res_bloqueo = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": datos_ausencia["centro"].id, "inicio": nuevo_inicio},
        headers=_auth_header_para(app, datos_ausencia["usuario_paciente"]),
    )
    assert res_bloqueo.status_code == 409


def test_no_registra_ausencia_si_existe_muestra_o_estudio_avanzo(
    app, session, datos_ausencia
):
    """TC-05: No marca ausente ni incrementa ausencias si ya tiene Muestra o estado avanzado."""
    turno = datos_ausencia["turno"]
    estudio = datos_ausencia["estudio"]
    session.add(Muestra(estudio_id=estudio.id, turno_id=turno.id))
    estudio.estado = EstadoEstudio.LISTA_PARA_RETIRAR
    session.commit()

    resumen = AusenciaService.procesar_turnos_vencidos(ahora=datetime.now())
    assert resumen["total_detectados"] == 0
    assert resumen["total_procesados"] == 0

    _, _, status = AusenciaService.registrar_ausencia(turno.id, ahora=datetime.now())
    assert status == 409

    session.refresh(estudio)
    assert estudio.ausencias == 0


def test_idempotencia_ventana_15_min_y_aislamiento_por_turno_ante_fallo_de_mail(
    app, session, datos_ausencia
):
    """TC-06: Ignora turnos < 15 min, es idempotente y aisla el rollback ante fallo de EmailClient."""
    ahora = datetime.now().replace(second=0, microsecond=0)
    turno_vencido = datos_ausencia["turno"]
    estudio = datos_ausencia["estudio"]

    # Caso 1: Turno aun dentro de los 15 minutos -> no se detecta ni procesa
    turno_vencido.inicio = ahora - timedelta(minutes=10)
    session.commit()
    assert AusenciaService.procesar_turnos_vencidos(ahora=ahora)["total_detectados"] == 0
    _, _, status_422 = AusenciaService.registrar_ausencia(turno_vencido.id, ahora=ahora)
    assert status_422 == 422

    # Caso 2: Exactamente al cumplirse los 15 min -> si falla EmailClient, revierte solo ese turno
    turno_vencido.inicio = ahora - timedelta(minutes=15)

    estudio_ok = Estudio(
        paciente_id=datos_ausencia["paciente"].id,
        medico_id=datos_ausencia["medico"].id,
        patologia_sospechada_id=datos_ausencia["patologia"].id,
        estado=EstadoEstudio.TURNO_SACADO,
        ausencias=0,
    )
    session.add(estudio_ok)
    session.flush()
    turno_ok = Turno(
        centro_id=datos_ausencia["centro"].id,
        paciente_id=datos_ausencia["paciente"].id,
        estudio_id=estudio_ok.id,
        inicio=ahora - timedelta(minutes=25),
        activo=True,
        asistio=None,
    )
    session.add(turno_ok)
    session.commit()

    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.side_effect = [
        {"id": "mail-ok", "estado": "pendiente"},
        ClienteConexionError("Timeout API Mail"),
    ]
    resumen_fallo = AusenciaService.procesar_turnos_vencidos(ahora=ahora, email_client=mock_email)
    assert resumen_fallo["total_detectados"] == 2
    assert resumen_fallo["total_procesados"] == 1
    assert len(resumen_fallo["errores"]) == 1
    assert resumen_fallo["errores"][0]["turno_id"] == turno_vencido.id
    assert resumen_fallo["errores"][0]["status"] == 502

    session.refresh(turno_ok)
    session.refresh(turno_vencido)
    session.refresh(estudio)
    assert turno_ok.asistio is False
    assert turno_vencido.activo is True
    assert turno_vencido.asistio is None
    assert estudio.ausencias == 0

    # Caso 3: Al recuperarse EmailClient, reprocesa turno_vencido y una 2da corrida no duplica
    mock_email_ok = MagicMock(spec=EmailClient)
    resumen_reintento = AusenciaService.procesar_turnos_vencidos(
        ahora=ahora, email_client=mock_email_ok
    )
    assert resumen_reintento["total_detectados"] == 1
    assert resumen_reintento["total_procesados"] == 1

    resumen_idempotente = AusenciaService.procesar_turnos_vencidos(
        ahora=ahora, email_client=mock_email_ok
    )
    assert resumen_idempotente["total_detectados"] == 0
    session.refresh(estudio)
    assert estudio.ausencias == 1


def test_cli_procesar_ausencias_y_bloqueo_endpoint_manual(
    app, client, session, datos_ausencia
):
    """TC-07: CLI automatico procesa vencidos y no existe endpoint HTTP manual para admin."""
    turno = datos_ausencia["turno"]
    estudio = datos_ausencia["estudio"]

    for usuario in (
        datos_ausencia["usuario_administrativo"],
        datos_ausencia["usuario_admin_general"],
    ):
        res_http = client.post(
            f"/api/v1/turnos/{turno.id}/registrar-ausencia",
            headers=_auth_header_para(app, usuario),
        )
        assert res_http.status_code == 404

    mock_email = MagicMock(spec=EmailClient)
    app.config["EMAIL_CLIENT"] = mock_email

    runner = app.test_cli_runner()
    resultado_cli = runner.invoke(args=["procesar-ausencias"])
    assert resultado_cli.exit_code == 0
    assert "Procesados: 1" in resultado_cli.output

    session.refresh(turno)
    session.refresh(estudio)
    assert turno.asistio is False
    assert turno.activo is False
    assert estudio.ausencias == 1
    mock_email.enviar_aviso.assert_called_once()
