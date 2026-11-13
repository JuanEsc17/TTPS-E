"""Tests integrales para el flujo de Solicitar un Turno de Extraccion (Escenario 7)."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from src.clients import EmailClient
from src.clients.exceptions import ClienteConexionError
from src.core.models import (
    Aviso,
    CanalAviso,
    CentroExtraccion,
    EstadoEstudio,
    Estudio,
    Medico,
    Paciente,
    Pago,
    Patologia,
    Presupuesto,
    Rol,
    TipoPago,
    Turno,
    Usuario,
)


@pytest.fixture
def datos_escenario(session):
    """Prepara las entidades base: Centro, Medico, Patologia, Paciente titular y otro usuario."""
    centro = CentroExtraccion(
        nombre="Laboratorio Rossi - Sede Belgrano",
        direccion="Av. Cabildo 2040",
        provincia="Buenos Aires",
        latitud=-34.5612,
        longitud=-58.4567,
    )
    patologia = Patologia(nombre="Fabry", descripcion="Enfermedad de Fabry")
    u_med = Usuario(
        email="medico@hospital.com",
        password_hash="hash",
        rol=Rol.MEDICO,
        nombre="Carlos",
        apellido="Gomez",
        telefono="11223344",
    )
    u_pac = Usuario(
        email="paciente@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Juan",
        apellido="Perez",
        telefono="11998877",
    )
    u_otro = Usuario(
        email="otro@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Pedro",
        apellido="Lopez",
        telefono="11002233",
    )
    session.add_all([centro, patologia, u_med, u_pac, u_otro])
    session.flush()

    medico = Medico(usuario_id=u_med.id, matricula="MP-12345")
    session.add(medico)
    session.flush()

    paciente = Paciente(
        usuario_id=u_pac.id,
        medico_id=medico.id,
        dni="30111222",
        fecha_nacimiento=date(1990, 5, 20),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-001",
        tipo_sospecha="Sospecha clinica",
    )
    paciente_otro = Paciente(
        usuario_id=u_otro.id,
        medico_id=medico.id,
        dni="31222333",
        fecha_nacimiento=date(1992, 8, 10),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-002",
        tipo_sospecha="Antecedente familiar",
    )
    session.add_all([paciente, paciente_otro])
    session.flush()

    estudio = Estudio(
        paciente_id=paciente.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.AUTORIZADO,
    )
    session.add(estudio)
    session.commit()

    return {
        "centro": centro,
        "patologia": patologia,
        "medico": medico,
        "usuario_paciente": u_pac,
        "usuario_otro": u_otro,
        "paciente": paciente,
        "paciente_otro": paciente_otro,
        "estudio": estudio,
    }


def proximo_dia_habil(hora: int = 10, minuto: int = 15) -> datetime:
    """Devuelve el proximo dia habil (lunes a viernes) en la hora y minuto indicados."""
    candidato = datetime.now() + timedelta(days=1)
    while candidato.weekday() >= 5:
        candidato += timedelta(days=1)
    return candidato.replace(hour=hora, minute=minuto, second=0, microsecond=0)


# ==============================================================================
# 1. FLUJO COMPLETO END-TO-END (Centros -> Disponibilidad -> Solicitar Turno)
# ==============================================================================
def test_flujo_completo_solicitar_turno_extraccion(app, client, session, datos_escenario):
    """
    Recorre el flujo completo del Escenario 7 (TC-01):
    1. Listar centros de extraccion.
    2. Consultar horarios disponibles para una fecha habil.
    3. Solicitar un turno en un estudio AUTORIZADO verificando EmailClient y BD.
    4. Confirmar que el horario reservado ya no figura como disponible.
    """
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "aviso-ext-1", "estado": "pendiente"}
    app.config["EMAIL_CLIENT"] = mock_email

    estudio = datos_escenario["estudio"]
    usuario_paciente = datos_escenario["usuario_paciente"]
    horario = proximo_dia_habil(10, 15)
    fecha_str = horario.strftime("%Y-%m-%d")

    # Paso 1: Listar centros de extraccion
    res_centros = client.get("/api/v1/centros-extraccion")
    assert res_centros.status_code == 200
    centros_data = res_centros.get_json()["data"]
    assert len(centros_data) == 1
    centro_id = centros_data[0]["id"]
    assert centros_data[0]["nombre"] == "Laboratorio Rossi - Sede Belgrano"

    # Paso 2: Consultar disponibilidad (36 slots de 15 min entre 09:00 y 17:45)
    res_disp = client.get(
        f"/api/v1/centros-extraccion/{centro_id}/turnos-disponibles?fecha={fecha_str}"
    )
    assert res_disp.status_code == 200
    slots_libres = res_disp.get_json()["data"]["slots_libres"]
    assert len(slots_libres) == 36
    assert horario.isoformat() in slots_libres

    # Paso 3: Solicitar el turno para las 10:15
    res_turno = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro_id, "inicio": horario.isoformat()},
        headers={"X-User-Id": str(usuario_paciente.id)},
    )
    assert res_turno.status_code == 201
    data_turno = res_turno.get_json()["data"]
    assert data_turno["estudio_id"] == estudio.id
    assert data_turno["centro_id"] == centro_id
    assert data_turno["estado_estudio"] == EstadoEstudio.TURNO_SACADO.value
    assert data_turno["documentacion_enviada"] == {
        "orden_extraccion": True,
        "consentimiento_informado": True,
        "recordatorio": True,
    }

    # Verificar persistencia en BD (Turno, Estudio y Aviso)
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.TURNO_SACADO

    turno_bd = session.get(Turno, data_turno["turno_id"])
    assert turno_bd is not None
    assert turno_bd.activo is True
    assert turno_bd.asistio is None
    assert turno_bd.inicio == horario

    aviso_bd = session.query(Aviso).filter_by(usuario_id=usuario_paciente.id).first()
    assert aviso_bd is not None
    assert aviso_bd.canal == CanalAviso.MAIL
    assert aviso_bd.enviado is True
    assert "5 ausencias" in aviso_bd.mensaje

    # Verificar llamada a EmailClient
    mock_email.enviar_aviso.assert_called_once()
    _, kwargs_email = mock_email.enviar_aviso.call_args
    assert kwargs_email["destinatarios"] == [usuario_paciente.email]
    assert kwargs_email["referencia"] == f"TURNO-{turno_bd.id}"
    assert "Orden de extraccion" in kwargs_email["mensaje"]
    assert "Consentimiento informado" in kwargs_email["mensaje"]

    # Paso 4: Consultar disponibilidad nuevamente y comprobar que 10:15 ya no esta libre
    res_disp_post = client.get(
        f"/api/v1/centros-extraccion/{centro_id}/turnos-disponibles?fecha={fecha_str}"
    )
    assert res_disp_post.status_code == 200
    slots_post = res_disp_post.get_json()["data"]["slots_libres"]
    assert len(slots_post) == 35
    assert horario.isoformat() not in slots_post


# ==============================================================================
# 2. ESTADOS HABILITADOS PARA SACAR TURNO (TC-02, TC-03 y reintento tras ausencia)
# ==============================================================================
def test_solicitar_turno_estudio_creado_con_pago_particular_activo(
    client, session, datos_escenario
):
    """TC-02: Estudio en CREADO con pago particular vigente (anulado=False) puede sacar turno."""
    estudio = datos_escenario["estudio"]
    estudio.estado = EstadoEstudio.CREADO
    session.flush()

    presupuesto = Presupuesto(
        estudio_id=estudio.id,
        emitido_por_id=datos_escenario["usuario_paciente"].id,
        cantidad_genes=5,
        monto_total_usd=Decimal("1200.00"),
    )
    session.add(presupuesto)
    session.flush()

    pago = Pago(
        presupuesto_id=presupuesto.id,
        tipo=TipoPago.PARTICULAR,
        monto_usd=Decimal("1200.00"),
        anulado=False,
    )
    session.add(pago)
    session.commit()

    horario = proximo_dia_habil(11, 0)
    response = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={
            "centro_id": datos_escenario["centro"].id,
            "inicio": f"{horario.strftime('%Y-%m-%dT%H:%M:%S')}Z",
        },
    )
    assert response.status_code == 201
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.TURNO_SACADO


def test_solicitar_turno_remuestreo_y_tras_ausencia_previa(
    client, session, datos_escenario
):
    """TC-03: Permite reservar en REMUESTREO_REQUERIDO y en TURNO_SACADO con ausencias < 5."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]

    # Caso A: Remuestreo requerido (sin costo adicional)
    estudio.estado = EstadoEstudio.REMUESTREO_REQUERIDO
    session.commit()

    horario_1 = proximo_dia_habil(12, 30)
    res_1 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario_1.isoformat()},
    )
    assert res_1.status_code == 201

    # Simulamos que el paciente falto a ese turno (activo=False, asistio=False, ausencias=1)
    turno_1 = session.get(Turno, res_1.get_json()["data"]["turno_id"])
    turno_1.activo = False
    turno_1.asistio = False
    estudio.ausencias = 1
    session.commit()

    # Caso B: Reintento tras ausencia con ausencias < 5
    horario_2 = proximo_dia_habil(14, 45)
    res_2 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario_2.isoformat()},
    )
    assert res_2.status_code == 201
    assert res_2.get_json()["data"]["ausencias_acumuladas"] == 1


# ==============================================================================
# 3. REGLAS DE RECHAZO DE NEGOCIO Y COLISIONES (TC-04, TC-06)
# ==============================================================================
def test_solicitar_turno_colision_mismo_horario_retorna_409(
    client, session, datos_escenario
):
    """TC-04: Dos estudios que intentan reservar el mismo centro y horario reciben 409."""
    centro = datos_escenario["centro"]
    estudio_1 = datos_escenario["estudio"]

    estudio_2 = Estudio(
        paciente_id=datos_escenario["paciente_otro"].id,
        medico_id=datos_escenario["medico"].id,
        patologia_sospechada_id=datos_escenario["patologia"].id,
        estado=EstadoEstudio.AUTORIZADO,
    )
    session.add(estudio_2)
    session.commit()

    horario = proximo_dia_habil(9, 15)

    # Primer paciente reserva con exito
    res_1 = client.post(
        f"/api/v1/estudios/{estudio_1.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
    )
    assert res_1.status_code == 201

    # Segundo paciente intenta el mismo horario y centro -> 409 Conflict
    res_2 = client.post(
        f"/api/v1/estudios/{estudio_2.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
    )
    assert res_2.status_code == 409
    assert "horario" in res_2.get_json()["error"].lower()


@pytest.mark.parametrize(
    ("estado", "ausencias", "con_pago_anulado"),
    [
        (EstadoEstudio.CREADO, 0, False),        # Creado sin pago
        (EstadoEstudio.CREADO, 0, True),         # Creado con pago anulado
        (EstadoEstudio.TURNO_SACADO, 5, False),  # Alcanzo limite de 5 ausencias
    ],
)
def test_solicitar_turno_estudio_no_habilitado_retorna_409(
    client, session, datos_escenario, estado, ausencias, con_pago_anulado
):
    """TC-06: Estudios impagos, con pago anulado o con 5 ausencias retornan 409."""
    estudio = datos_escenario["estudio"]
    estudio.estado = estado
    estudio.ausencias = ausencias
    session.flush()

    if con_pago_anulado:
        presupuesto = Presupuesto(
            estudio_id=estudio.id,
            emitido_por_id=datos_escenario["usuario_paciente"].id,
            cantidad_genes=3,
            monto_total_usd=Decimal("900.00"),
        )
        session.add(presupuesto)
        session.flush()
        session.add(
            Pago(
                presupuesto_id=presupuesto.id,
                tipo=TipoPago.PARTICULAR,
                monto_usd=Decimal("900.00"),
                anulado=True,
            )
        )
    session.commit()

    horario = proximo_dia_habil(10, 0)
    response = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": datos_escenario["centro"].id, "inicio": horario.isoformat()},
    )
    assert response.status_code == 409
    assert "no se encuentra habilitado" in response.get_json()["error"].lower()


def test_solicitar_turno_ya_posee_turno_activo_retorna_409(
    client, datos_escenario
):
    """Un estudio que ya tiene un turno activo pendiente no puede reservar un segundo turno."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]

    h1 = proximo_dia_habil(10, 0)
    h2 = proximo_dia_habil(11, 0)

    res_1 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": h1.isoformat()},
    )
    assert res_1.status_code == 201

    res_2 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": h2.isoformat()},
    )
    assert res_2.status_code == 409
    assert "ya posee un turno activo" in res_2.get_json()["error"].lower()


# ==============================================================================
# 4. VALIDACIONES DE HORARIO Y ENTRADA (TC-05 -> 422)
# ==============================================================================
def test_validaciones_horarias_y_formato_retornan_422(
    client, datos_escenario
):
    """TC-05: Rechaza horarios en el pasado, fin de semana, feriado, fuera de rango o no multiplos de 15."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    base = proximo_dia_habil()

    # Proximo sabado
    dias_hasta_sabado = (5 - base.weekday()) % 7 or 7
    sabado = (base + timedelta(days=dias_hasta_sabado)).replace(hour=10, minute=0)

    # Feriado nacional inamovible que cae viernes: 25/12/2026 (Navidad)
    feriado_navidad = datetime(2026, 12, 25, 10, 30)

    casos_invalidos = [
        datetime(2020, 1, 6, 10, 0).isoformat(),      # En el pasado
        sabado.isoformat(),                            # Fin de semana
        feriado_navidad.isoformat(),                   # Feriado nacional
        base.replace(hour=8, minute=45).isoformat(),   # Antes de las 09:00
        base.replace(hour=18, minute=0).isoformat(),   # Despues de las 17:45
        base.replace(hour=10, minute=7).isoformat(),   # Minuto no multiplo de 15
        "fecha-invalida",                              # Formato ISO invalido
    ]

    for inicio_invalido in casos_invalidos:
        res = client.post(
            f"/api/v1/estudios/{estudio.id}/turnos",
            json={"centro_id": centro.id, "inicio": inicio_invalido},
        )
        assert res.status_code == 422

    # Disponibilidad en fin de semana o feriado devuelve lista vacia
    res_disp_sab = client.get(
        f"/api/v1/centros-extraccion/{centro.id}/turnos-disponibles?fecha={sabado.strftime('%Y-%m-%d')}"
    )
    assert res_disp_sab.status_code == 200
    assert res_disp_sab.get_json()["data"]["slots_libres"] == []


# ==============================================================================
# 5. PERMISOS (403), RECURSOS INEXISTENTES (404) Y FALLO DE EMAIL (502)
# ==============================================================================
def test_permisos_recursos_inexistentes_y_rollback_email(
    app, client, session, datos_escenario
):
    """Verifica 403 por usuario no titular, 404 por estudio/centro inexistente y 502 con rollback si falla email."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    horario = proximo_dia_habil(15, 0)

    # 1. Usuario ajeno al estudio -> 403 Forbidden
    res_403 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
        headers={"X-User-Id": str(datos_escenario["usuario_otro"].id)},
    )
    assert res_403.status_code == 403

    # 2. Estudio o centro inexistente -> 404 Not Found
    res_404_est = client.post(
        "/api/v1/estudios/99999/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
    )
    assert res_404_est.status_code == 404

    res_404_cen = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": 99999, "inicio": horario.isoformat()},
    )
    assert res_404_cen.status_code == 404

    # 3. Falla en EmailClient -> 502 Bad Gateway y rollback completo
    class EmailClientFalla:
        def enviar_aviso(self, **kwargs):
            raise ClienteConexionError("Error de conexion con servicio de correo")

    app.config["EMAIL_CLIENT"] = EmailClientFalla()
    res_502 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
    )
    assert res_502.status_code == 502

    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.AUTORIZADO
    assert session.query(Turno).filter_by(estudio_id=estudio.id).count() == 0
