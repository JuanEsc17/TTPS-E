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
from src.core.services.seguridad import SCOPE_ACCESO_COMPLETO, emitir_token


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
        "usuario_medico": u_med,
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


def auth_header_para(app, usuario: Usuario) -> dict[str, str]:
    """Genera cabecera Authorization con un Bearer token valido para el usuario."""
    token = emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. FLUJO COMPLETO END-TO-END (Centros -> Disponibilidad -> Solicitar Turno)
# ==============================================================================
def test_flujo_completo_solicitar_turno_extraccion(app, client, session, datos_escenario):
    """
    Recorre el flujo completo del Escenario 7 (TC-01):
    1. Listar centros de extraccion (requiere sesion autenticada).
    2. Consultar horarios disponibles para una fecha habil.
    3. Solicitar un turno en un estudio AUTORIZADO verificando EmailClient y BD.
    4. Confirmar que el horario reservado ya no figura como disponible.
    """
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "aviso-ext-1", "estado": "pendiente"}
    app.config["EMAIL_CLIENT"] = mock_email

    estudio = datos_escenario["estudio"]
    usuario_paciente = datos_escenario["usuario_paciente"]
    headers_pac = auth_header_para(app, usuario_paciente)

    horario = proximo_dia_habil(10, 15)
    fecha_str = horario.strftime("%Y-%m-%d")

    # Paso 1: Listar centros de extraccion
    res_centros = client.get("/api/v1/centros-extraccion", headers=headers_pac)
    assert res_centros.status_code == 200
    centros_data = res_centros.get_json()["data"]
    assert len(centros_data) == 1
    centro_id = centros_data[0]["id"]
    assert centros_data[0]["nombre"] == "Laboratorio Rossi - Sede Belgrano"

    # Paso 2: Consultar disponibilidad (36 slots de 15 min entre 09:00 y 17:45)
    res_disp = client.get(
        f"/api/v1/centros-extraccion/{centro_id}/turnos-disponibles?fecha={fecha_str}",
        headers=headers_pac,
    )
    assert res_disp.status_code == 200
    slots_libres = res_disp.get_json()["data"]["slots_libres"]
    assert len(slots_libres) == 36
    assert horario.isoformat() in slots_libres

    # Paso 3: Solicitar el turno para las 10:15
    res_turno = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro_id, "inicio": horario.isoformat()},
        headers=headers_pac,
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
        "canal_pdf": "app",
        "pdf_url": f"/api/v1/turnos/{data_turno['turno_id']}/consentimiento-pdf",
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
    assert "Orden de extracción" in kwargs_email["mensaje"]
    assert "Consentimiento informado" in kwargs_email["mensaje"]

    # Paso 4: Consultar disponibilidad nuevamente y comprobar que 10:15 ya no esta libre
    res_disp_post = client.get(
        f"/api/v1/centros-extraccion/{centro_id}/turnos-disponibles?fecha={fecha_str}",
        headers=headers_pac,
    )
    assert res_disp_post.status_code == 200
    slots_post = res_disp_post.get_json()["data"]["slots_libres"]
    assert len(slots_post) == 35
    assert horario.isoformat() not in slots_post


# ==============================================================================
# 2. ESTADOS HABILITADOS PARA SACAR TURNO (TC-02, TC-03 y reintento tras ausencia)
# ==============================================================================
def test_solicitar_turno_estudio_creado_con_pago_particular_activo(
    app, client, session, datos_escenario
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

    headers = auth_header_para(app, datos_escenario["usuario_paciente"])
    horario = proximo_dia_habil(11, 0)
    response = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={
            "centro_id": datos_escenario["centro"].id,
            "inicio": f"{horario.strftime('%Y-%m-%dT%H:%M:%S')}Z",
        },
        headers=headers,
    )
    assert response.status_code == 201
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.TURNO_SACADO


def test_solicitar_turno_remuestreo_y_tras_ausencia_previa(
    app, client, session, datos_escenario
):
    """TC-03: Permite reservar en REMUESTREO_REQUERIDO y en TURNO_SACADO con ausencias < 5."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    headers = auth_header_para(app, datos_escenario["usuario_paciente"])

    # Caso A: Remuestreo requerido (sin costo adicional)
    estudio.estado = EstadoEstudio.REMUESTREO_REQUERIDO
    session.commit()

    horario_1 = proximo_dia_habil(12, 30)
    res_1 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario_1.isoformat()},
        headers=headers,
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
        headers=headers,
    )
    assert res_2.status_code == 201
    assert res_2.get_json()["data"]["ausencias_acumuladas"] == 1


# ==============================================================================
# 3. REGLAS DE RECHAZO DE NEGOCIO Y COLISIONES (TC-04, TC-06)
# ==============================================================================
def test_solicitar_turno_colision_mismo_horario_retorna_409(
    app, client, session, datos_escenario
):
    """TC-04: Dos pacientes con estudios autorizados intentan reservar el mismo slot -> 409."""
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

    headers_1 = auth_header_para(app, datos_escenario["usuario_paciente"])
    headers_2 = auth_header_para(app, datos_escenario["usuario_otro"])
    horario = proximo_dia_habil(9, 15)

    # Primer paciente reserva con exito
    res_1 = client.post(
        f"/api/v1/estudios/{estudio_1.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
        headers=headers_1,
    )
    assert res_1.status_code == 201

    # Segundo paciente intenta el mismo horario y centro -> 409 Conflict
    res_2 = client.post(
        f"/api/v1/estudios/{estudio_2.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
        headers=headers_2,
    )
    assert res_2.status_code == 409
    assert "horario" in res_2.get_json()["error"].lower()


@pytest.mark.parametrize(
    ("estado", "ausencias", "con_pago_anulado"),
    [
        (EstadoEstudio.CREADO, 0, False),             # Creado sin pago
        (EstadoEstudio.CREADO, 0, True),              # Creado con pago anulado
        (EstadoEstudio.TURNO_SACADO, 5, False),       # Alcanzo limite de 5 ausencias
        (EstadoEstudio.LISTA_PARA_RETIRAR, 0, False), # Ya tiene muestra tomada
    ],
)
def test_solicitar_turno_estudio_no_habilitado_retorna_409(
    app, client, session, datos_escenario, estado, ausencias, con_pago_anulado
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

    headers = auth_header_para(app, datos_escenario["usuario_paciente"])
    horario = proximo_dia_habil(10, 0)
    response = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": datos_escenario["centro"].id, "inicio": horario.isoformat()},
        headers=headers,
    )
    assert response.status_code == 409
    assert "no se encuentra habilitado" in response.get_json()["error"].lower()


def test_solicitar_turno_ya_posee_turno_activo_retorna_409(
    app, client, datos_escenario
):
    """Un estudio que ya tiene un turno activo pendiente no puede reservar un segundo turno."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    headers = auth_header_para(app, datos_escenario["usuario_paciente"])

    h1 = proximo_dia_habil(10, 0)
    h2 = proximo_dia_habil(11, 0)

    res_1 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": h1.isoformat()},
        headers=headers,
    )
    assert res_1.status_code == 201

    res_2 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": h2.isoformat()},
        headers=headers,
    )
    assert res_2.status_code == 409
    assert "ya posee un turno activo" in res_2.get_json()["error"].lower()


# ==============================================================================
# 4. VALIDACIONES DE HORARIO Y ENTRADA (TC-05 -> 422)
# ==============================================================================
def test_validaciones_horarias_y_formato_retornan_422(
    app, client, datos_escenario
):
    """TC-05: Rechaza horarios en el pasado, fin de semana, feriado, fuera de rango o no multiplos de 15."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    headers = auth_header_para(app, datos_escenario["usuario_paciente"])
    base = proximo_dia_habil()

    # Proximo sabado
    dias_hasta_sabado = (5 - base.weekday()) % 7 or 7
    sabado = (base + timedelta(days=dias_hasta_sabado)).replace(hour=10, minute=0)

    # Feriado nacional inamovible que cae viernes: 25/12/2026 (Navidad)
    feriado_navidad = datetime(2026, 12, 25, 10, 30)

    # Fecha habil mas alla del limite maximo de 4 meses
    from src.core.services.turno_service import TurnoService

    dia_excedido = TurnoService.fecha_maxima_turno() + timedelta(days=1)
    while not TurnoService.es_dia_laborable(dia_excedido):
        dia_excedido += timedelta(days=1)
    fuera_de_rango = datetime.combine(dia_excedido, datetime.min.time()).replace(hour=10, minute=0)

    casos_invalidos = [
        datetime(2020, 1, 6, 10, 0).isoformat(),      # En el pasado
        fuera_de_rango.isoformat(),                    # Mas de 4 meses adelante
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
            headers=headers,
        )
        assert res.status_code == 422

    # Disponibilidad en fin de semana, feriado o mas alla de 4 meses devuelve lista vacia
    res_disp_sab = client.get(
        f"/api/v1/centros-extraccion/{centro.id}/turnos-disponibles?fecha={sabado.strftime('%Y-%m-%d')}",
        headers=headers,
    )
    assert res_disp_sab.status_code == 200
    assert res_disp_sab.get_json()["data"]["slots_libres"] == []

    res_disp_fuera = client.get(
        f"/api/v1/centros-extraccion/{centro.id}/turnos-disponibles?fecha={dia_excedido.isoformat()}",
        headers=headers,
    )
    assert res_disp_fuera.status_code == 200
    assert res_disp_fuera.get_json()["data"]["slots_libres"] == []


# ==============================================================================
# 5. SEGURIDAD: AUTENTICACION (401), ROLES (403), PERMISOS (403) Y 404/502
# ==============================================================================
def test_autenticacion_y_roles_en_endpoints_turnos(
    app, client, session, datos_escenario
):
    """Verifica que los endpoints exijan autenticacion (401) y rol Paciente en la reserva (403)."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    horario = proximo_dia_habil(10, 0)

    # 1. Peticiones sin token retornan 401 NO_AUTENTICADO
    assert client.get("/api/v1/centros-extraccion").status_code == 401
    assert client.get(f"/api/v1/centros-extraccion/{centro.id}/turnos-disponibles?fecha=2026-11-20").status_code == 401
    assert client.post(f"/api/v1/estudios/{estudio.id}/turnos", json={"centro_id": centro.id, "inicio": horario.isoformat()}).status_code == 401

    # 2. Usuario con rol MEDICO intentando reservar turno -> 403 ROL_NO_AUTORIZADO
    headers_medico = auth_header_para(app, datos_escenario["usuario_medico"])
    res_medico = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
        headers=headers_medico,
    )
    assert res_medico.status_code == 403
    assert res_medico.get_json()["code"] == "ROL_NO_AUTORIZADO"


def test_permisos_recursos_inexistentes_y_rollback_email(
    app, client, session, datos_escenario
):
    """Verifica 403 por paciente no titular, 404 por estudio/centro inexistente y 502 con rollback si falla email."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    headers_pac = auth_header_para(app, datos_escenario["usuario_paciente"])
    headers_otro_pac = auth_header_para(app, datos_escenario["usuario_otro"])
    horario = proximo_dia_habil(15, 0)

    # 1. Paciente ajeno al estudio -> 403 Forbidden (no tiene permisos sobre el estudio)
    res_403 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
        headers=headers_otro_pac,
    )
    assert res_403.status_code == 403

    # 2. Estudio o centro inexistente -> 404 Not Found
    res_404_est = client.post(
        "/api/v1/estudios/99999/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
        headers=headers_pac,
    )
    assert res_404_est.status_code == 404

    res_404_cen = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": 99999, "inicio": horario.isoformat()},
        headers=headers_pac,
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
        headers=headers_pac,
    )
    assert res_502.status_code == 502

    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.AUTORIZADO
    assert session.query(Turno).filter_by(estudio_id=estudio.id).count() == 0


def test_listar_mis_estudios_para_turno(app, client, session, datos_escenario):
    """El paciente lista solo sus propios estudios, su habilitacion y su turno activo."""
    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    headers_pac = auth_header_para(app, datos_escenario["usuario_paciente"])
    headers_otro = auth_header_para(app, datos_escenario["usuario_otro"])
    headers_med = auth_header_para(app, datos_escenario["usuario_medico"])

    # Rol no paciente -> 403
    assert client.get("/api/v1/turnos/mis-estudios", headers=headers_med).status_code == 403

    # Otro paciente no ve el estudio ajeno
    res_otro = client.get("/api/v1/turnos/mis-estudios", headers=headers_otro)
    assert res_otro.status_code == 200
    assert res_otro.get_json()["data"] == []

    # Paciente titular ve su estudio habilitado y sin turno activo
    res_antes = client.get("/api/v1/turnos/mis-estudios", headers=headers_pac)
    assert res_antes.status_code == 200
    items = res_antes.get_json()["data"]
    assert len(items) == 1
    assert items[0]["estudio_id"] == estudio.id
    assert items[0]["habilitado_para_turno"] is True
    assert items[0]["turno_activo"] is None

    # Reserva turno y vuelve a consultar -> muestra turno_activo con centro y ya no habilitado
    horario = proximo_dia_habil(10, 30)
    res_post = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
        headers=headers_pac,
    )
    assert res_post.status_code == 201

    res_despues = client.get("/api/v1/turnos/mis-estudios", headers=headers_pac)
    assert res_despues.status_code == 200
    items_despues = res_despues.get_json()["data"]
    assert items_despues[0]["habilitado_para_turno"] is False
    assert items_despues[0]["turno_activo"]["centro"]["id"] == centro.id
    assert items_despues[0]["turno_activo"]["inicio"] == horario.isoformat()


def test_disponibilidad_hoy_filtra_horarios_pasados(app, session, datos_escenario):
    """Para el dia de hoy solo retorna horarios estrictamente posteriores a la hora actual."""
    from src.core.services.turno_service import TurnoService

    centro = datos_escenario["centro"]
    hoy_habil = proximo_dia_habil(12, 20).date()
    ahora_mediodia = datetime.combine(hoy_habil, datetime.min.time()).replace(hour=12, minute=20)

    with app.app_context():
        resultado, error, status = TurnoService.obtener_disponibilidad(
            centro_id=centro.id,
            fecha=hoy_habil,
            ahora=ahora_mediodia,
        )
        assert status == 200
        assert error is None
        slots = resultado["slots_libres"]
        # Desde 12:30 hasta 17:45 inclusive (22 slots de 15 min)
        assert len(slots) == 22
        assert slots[0].endswith("12:30:00")
        assert slots[-1].endswith("17:45:00")
        assert all(datetime.fromisoformat(s) > ahora_mediodia for s in slots)



def test_solicitar_turno_genera_pdf_aviso_app_y_permite_descarga(
    app, client, session, datos_escenario
):
    """Al reservar turno se guarda el PDF en el turno, se emite aviso APP y se puede descargar."""
    from src.core.services import almacenamiento_service

    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    headers_pac = auth_header_para(app, datos_escenario["usuario_paciente"])
    headers_otro = auth_header_para(app, datos_escenario["usuario_otro"])
    headers_med = auth_header_para(app, datos_escenario["usuario_medico"])
    horario = proximo_dia_habil(11, 15)

    res = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": horario.isoformat()},
        headers=headers_pac,
    )
    assert res.status_code == 201
    data = res.get_json()["data"]
    turno_id = data["turno_id"]
    assert data["consentimiento_pdf_url"] == f"/api/v1/turnos/{turno_id}/consentimiento-pdf"
    assert data["documentacion_enviada"]["canal_pdf"] == "app"

    with app.app_context():
        pdf_guardado = almacenamiento_service.leer_bytes(
            f"storage/turnos/orden_consentimiento_turno_{turno_id}.pdf"
        )
        assert pdf_guardado is not None
        assert pdf_guardado.startswith(b"%PDF-")

    aviso_app = (
        session.query(Aviso)
        .filter_by(
            usuario_id=datos_escenario["usuario_paciente"].id,
            canal=CanalAviso.APP,
        )
        .order_by(Aviso.id.desc())
        .first()
    )
    assert aviso_app is not None
    assert aviso_app.enviado is True
    assert f"Turno #{turno_id}" in aviso_app.mensaje
    assert f"Estudio #{estudio.id}" in aviso_app.mensaje

    res_avisos = client.get("/api/avisos", headers=headers_pac)
    assert res_avisos.status_code == 200
    avisos_json = res_avisos.get_json()["avisos"]
    aviso_turno = next((a for a in avisos_json if a["id"] == aviso_app.id), None)
    assert aviso_turno is not None
    assert aviso_turno["turno_id"] == turno_id
    assert aviso_turno["estudio_id"] == estudio.id

    res_mis_turnos = client.get("/api/v1/turnos/mis-turnos", headers=headers_pac)
    assert res_mis_turnos.status_code == 200
    turno_listado = res_mis_turnos.get_json()["data"][0]
    assert turno_listado["consentimiento_pdf_disponible"] is True
    assert turno_listado["consentimiento_pdf_url"] == f"/api/v1/turnos/{turno_id}/consentimiento-pdf"

    res_pdf = client.get(f"/api/v1/turnos/{turno_id}/consentimiento-pdf", headers=headers_pac)
    assert res_pdf.status_code == 200
    assert res_pdf.mimetype == "application/pdf"
    assert f"orden_consentimiento_turno_{turno_id}.pdf" in res_pdf.headers.get(
        "Content-Disposition", ""
    )
    assert res_pdf.data.startswith(b"%PDF-")

    assert (
        client.get(
            f"/api/v1/turnos/{turno_id}/consentimiento-pdf",
            headers=headers_otro,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/turnos/{turno_id}/consentimiento-pdf",
            headers=headers_med,
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/turnos/999999/consentimiento-pdf",
            headers=headers_pac,
        ).status_code
        == 404
    )


def test_consentimiento_pdf_regenera_si_falta_y_limpia_en_rollback(
    app, client, session, datos_escenario
):
    """Regenera el PDF bajo demanda si no esta en disco y lo elimina si falla el alta del turno."""
    from src.core.services import almacenamiento_service

    estudio = datos_escenario["estudio"]
    centro = datos_escenario["centro"]
    headers_pac = auth_header_para(app, datos_escenario["usuario_paciente"])

    # 1. Rollback ante fallo de mail elimina tambien el PDF generado
    class EmailClientFalla:
        def enviar_aviso(self, **kwargs):
            raise ClienteConexionError("Error SMTP simulado")

    app.config["EMAIL_CLIENT"] = EmailClientFalla()
    res_502 = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": proximo_dia_habil(14, 0).isoformat()},
        headers=headers_pac,
    )
    assert res_502.status_code == 502
    assert session.query(Turno).filter_by(estudio_id=estudio.id).count() == 0

    # 2. Alta exitosa, borrado del archivo en storage y regeneracion en la descarga
    app.config["EMAIL_CLIENT"] = EmailClient()
    app.config["EMAIL_CLIENT"].enviar_aviso = MagicMock()
    res_ok = client.post(
        f"/api/v1/estudios/{estudio.id}/turnos",
        json={"centro_id": centro.id, "inicio": proximo_dia_habil(14, 30).isoformat()},
        headers=headers_pac,
    )
    assert res_ok.status_code == 201
    turno_id = res_ok.get_json()["data"]["turno_id"]
    ruta_pdf = f"storage/turnos/orden_consentimiento_turno_{turno_id}.pdf"

    with app.app_context():
        almacenamiento_service.eliminar_archivo(ruta_pdf)
        assert almacenamiento_service.leer_bytes(ruta_pdf) is None

    res_pdf = client.get(f"/api/v1/turnos/{turno_id}/consentimiento-pdf", headers=headers_pac)
    assert res_pdf.status_code == 200
    assert res_pdf.data.startswith(b"%PDF-")

    with app.app_context():
        regenerado = almacenamiento_service.leer_bytes(ruta_pdf)
        assert regenerado is not None
        assert regenerado.startswith(b"%PDF-")
