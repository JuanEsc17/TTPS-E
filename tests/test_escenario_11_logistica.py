"""Tests integrales para Escenario 11: Transportar muestras al laboratorio central."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from src.clients import OptimizacionClient
from src.clients.exceptions import ClienteServicioError
from src.core.models import (
    CentroExtraccion,
    EstadoEstudio,
    Estudio,
    Medico,
    Muestra,
    OrdenDelDia,
    Paciente,
    Patologia,
    PosicionTransporte,
    Rol,
    Transportista,
    Turno,
    Usuario,
)
from src.core.services import logistica_service as logistica_service_mod
from src.core.services.seguridad import SCOPE_ACCESO_COMPLETO, emitir_token


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


def _fijar_fecha_hoy(monkeypatch, fecha_fija: date) -> None:
    """Fija date.today() dentro de logistica_service para tests deterministicos."""

    class _FakeDate(date):
        @classmethod
        def today(cls) -> date:
            return fecha_fija

    monkeypatch.setattr(logistica_service_mod, "date", _FakeDate)


@pytest.fixture
def datos_logistica(session):
    """Prepara transportistas, centros, pacientes, estudios y muestras listas para retirar."""
    patologia = Patologia(nombre="Fabry", descripcion="Enfermedad de Fabry")
    centro_lejano = CentroExtraccion(
        nombre="Centro Norte",
        direccion="Av. Cabildo 2000",
        provincia="Buenos Aires",
        latitud=-34.5500,
        longitud=-58.4600,
    )
    centro_cercano = CentroExtraccion(
        nombre="Centro La Plata",
        direccion="Calle 7 Nro 850",
        provincia="Buenos Aires",
        latitud=-34.9152,
        longitud=-57.9479,
    )
    centro_otra_prov = CentroExtraccion(
        nombre="Centro Cordoba",
        direccion="Av. Colon 500",
        provincia="Cordoba",
        latitud=-31.4167,
        longitud=-64.1833,
    )

    u_transp_ba = Usuario(
        email="transp.ba@lab.com",
        password_hash="hash",
        rol=Rol.TRANSPORTISTA,
        nombre="Lucas",
        apellido="Vega",
        telefono="11223344",
    )
    u_transp_cba = Usuario(
        email="transp.cba@lab.com",
        password_hash="hash",
        rol=Rol.TRANSPORTISTA,
        nombre="Mario",
        apellido="Diaz",
        telefono="351112233",
    )
    u_med = Usuario(
        email="med.log@lab.com",
        password_hash="hash",
        rol=Rol.MEDICO,
        nombre="Ana",
        apellido="Lopez",
        telefono="11556677",
    )
    u_pac1 = Usuario(
        email="pac1.log@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Juan",
        apellido="Perez",
        telefono="11998801",
    )
    u_pac2 = Usuario(
        email="pac2.log@gmail.com",
        password_hash="hash",
        rol=Rol.PACIENTE,
        nombre="Maria",
        apellido="Gomez",
        telefono="11998802",
    )
    session.add_all(
        [
            patologia,
            centro_lejano,
            centro_cercano,
            centro_otra_prov,
            u_transp_ba,
            u_transp_cba,
            u_med,
            u_pac1,
            u_pac2,
        ]
    )
    session.flush()

    transp_ba = Transportista(usuario_id=u_transp_ba.id, provincia="Buenos Aires")
    transp_cba = Transportista(usuario_id=u_transp_cba.id, provincia="Cordoba")
    medico = Medico(usuario_id=u_med.id, matricula="MP-5511")
    session.add_all([transp_ba, transp_cba, medico])
    session.flush()

    pac1 = Paciente(
        usuario_id=u_pac1.id,
        medico_id=medico.id,
        dni="30111001",
        fecha_nacimiento=date(1990, 1, 10),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-1101",
        tipo_sospecha="Clinica",
    )
    pac2 = Paciente(
        usuario_id=u_pac2.id,
        medico_id=medico.id,
        dni="30111002",
        fecha_nacimiento=date(1992, 3, 15),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="HC-1102",
        tipo_sospecha="Clinica",
    )
    session.add_all([pac1, pac2])
    session.flush()

    est1 = Estudio(
        paciente_id=pac1.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.LISTA_PARA_RETIRAR,
    )
    est2 = Estudio(
        paciente_id=pac2.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.LISTA_PARA_RETIRAR,
    )
    session.add_all([est1, est2])
    session.flush()

    ahora = datetime.now() - timedelta(hours=2)
    turno1 = Turno(
        centro_id=centro_lejano.id,
        paciente_id=pac1.id,
        estudio_id=est1.id,
        inicio=ahora,
        activo=False,
        asistio=True,
    )
    turno2 = Turno(
        centro_id=centro_cercano.id,
        paciente_id=pac2.id,
        estudio_id=est2.id,
        inicio=ahora,
        activo=False,
        asistio=True,
    )
    session.add_all([turno1, turno2])
    session.flush()

    muestra1 = Muestra(estudio_id=est1.id, turno_id=turno1.id, tomada_en=ahora)
    muestra2 = Muestra(estudio_id=est2.id, turno_id=turno2.id, tomada_en=ahora)
    session.add_all([muestra1, muestra2])
    session.commit()

    return {
        "centro_lejano": centro_lejano,
        "centro_cercano": centro_cercano,
        "centro_otra_prov": centro_otra_prov,
        "usuario_transp_ba": u_transp_ba,
        "usuario_transp_cba": u_transp_cba,
        "usuario_paciente": u_pac1,
        "transp_ba": transp_ba,
        "transp_cba": transp_cba,
        "est1": est1,
        "est2": est2,
        "muestra1": muestra1,
        "muestra2": muestra2,
    }


def test_generacion_orden_del_dia_habil_con_optimizacion(
    app, client, session, monkeypatch, datos_logistica
):
    """TC-01: En dia habil genera OrdenDelDia con el orden devuelto por OptimizacionClient."""
    _fijar_fecha_hoy(monkeypatch, date(2026, 11, 17))  # Martes habil
    c_lejano = datos_logistica["centro_lejano"]
    c_cercano = datos_logistica["centro_cercano"]

    mock_opt = MagicMock(spec=OptimizacionClient)
    mock_opt.optimizar_recorrido.return_value = [
        {"lat": -34.9214, "lon": -57.9544},
        {"lat": c_cercano.latitud, "lon": c_cercano.longitud},
        {"lat": c_lejano.latitud, "lon": c_lejano.longitud},
        {"lat": -34.9214, "lon": -57.9544},
    ]
    app.config["OPTIMIZACION_CLIENT"] = mock_opt

    resp = client.get(
        "/api/logistica/ordenes-del-dia/hoy",
        headers=_auth_header_para(app, datos_logistica["usuario_transp_ba"]),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["orden_id"] is not None
    assert [p["centro_id"] for p in data["paradas"]] == [c_cercano.id, c_lejano.id]
    assert [p["posicion"] for p in data["paradas"]] == [1, 2]
    mock_opt.optimizar_recorrido.assert_called_once()


def test_no_genera_orden_del_dia_en_fin_de_semana(
    app, client, session, monkeypatch, datos_logistica
):
    """TC-02: Rechaza con 400 si hoy es fin de semana y no persiste OrdenDelDia."""
    _fijar_fecha_hoy(monkeypatch, date(2026, 11, 14))  # Sabado

    resp = client.get(
        "/api/logistica/ordenes-del-dia/hoy",
        headers=_auth_header_para(app, datos_logistica["usuario_transp_ba"]),
    )
    assert resp.status_code == 400
    assert "DIA_NO_HABIL_SIN_ORDEN_DEL_DIA" in resp.get_json()["error"]
    assert session.query(OrdenDelDia).count() == 0


def test_inmutabilidad_orden_del_dia_y_sin_mutacion_manual(
    app, client, session, monkeypatch, datos_logistica
):
    """TC-03: Consultar nuevamente devuelve la misma orden sin recalcular ni permitir editarla."""
    _fijar_fecha_hoy(monkeypatch, date(2026, 11, 17))
    c_lejano = datos_logistica["centro_lejano"]
    c_cercano = datos_logistica["centro_cercano"]

    mock_opt = MagicMock(spec=OptimizacionClient)
    mock_opt.optimizar_recorrido.return_value = [
        {"lat": -34.9214, "lon": -57.9544},
        {"lat": c_lejano.latitud, "lon": c_lejano.longitud},
        {"lat": c_cercano.latitud, "lon": c_cercano.longitud},
        {"lat": -34.9214, "lon": -57.9544},
    ]
    app.config["OPTIMIZACION_CLIENT"] = mock_opt
    headers = _auth_header_para(app, datos_logistica["usuario_transp_ba"])

    r1 = client.get("/api/logistica/ordenes-del-dia/hoy", headers=headers)
    r2 = client.get("/api/logistica/ordenes-del-dia/hoy", headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.get_json()["data"] == r2.get_json()["data"]
    assert mock_opt.optimizar_recorrido.call_count == 1

    orden_id = r1.get_json()["data"]["orden_id"]
    assert client.put(f"/api/logistica/ordenes-del-dia/{orden_id}", headers=headers).status_code == 404


def test_fallback_local_ante_fallo_api_optimizacion(
    app, client, session, monkeypatch, datos_logistica
):
    """TC-04: Si OptimizacionClient falla 3 veces, ordena localmente por cercania al Lab Central."""
    _fijar_fecha_hoy(monkeypatch, date(2026, 11, 17))
    mock_opt = MagicMock(spec=OptimizacionClient)
    mock_opt.optimizar_recorrido.side_effect = ClienteServicioError("OSRM caido", codigo_http=503)
    app.config["OPTIMIZACION_CLIENT"] = mock_opt

    resp = client.get(
        "/api/logistica/ordenes-del-dia/hoy",
        headers=_auth_header_para(app, datos_logistica["usuario_transp_ba"]),
    )
    assert resp.status_code == 200
    assert mock_opt.optimizar_recorrido.call_count == 3
    paradas = resp.get_json()["data"]["paradas"]
    # centro_cercano (La Plata) esta mas cerca del Lab Central que centro_lejano
    assert [p["centro_id"] for p in paradas] == [
        datos_logistica["centro_cercano"].id,
        datos_logistica["centro_lejano"].id,
    ]


def test_marcar_recogida_en_centro_y_rechazo_duplicado(
    app, client, session, monkeypatch, datos_logistica
):
    """TC-05: Recoger en parada cambia estudios a EN_CAMINO_LAB_CENTRAL y rechaza doble recogida (409)."""
    _fijar_fecha_hoy(monkeypatch, date(2026, 11, 17))
    mock_opt = MagicMock(spec=OptimizacionClient)
    mock_opt.optimizar_recorrido.side_effect = ClienteServicioError("offline", codigo_http=503)
    app.config["OPTIMIZACION_CLIENT"] = mock_opt
    headers = _auth_header_para(app, datos_logistica["usuario_transp_ba"])

    orden_data = client.get("/api/logistica/ordenes-del-dia/hoy", headers=headers).get_json()["data"]
    orden_id = orden_data["orden_id"]
    parada_cercana = orden_data["paradas"][0]

    resp_rec = client.post(
        f"/api/logistica/ordenes-del-dia/{orden_id}/paradas/{parada_cercana['parada_id']}/recoger",
        headers=headers,
    )
    assert resp_rec.status_code == 200
    data_rec = resp_rec.get_json()["data"]
    assert data_rec["estudios_en_camino_ids"] == [datos_logistica["est2"].id]

    session.refresh(datos_logistica["est2"])
    session.refresh(datos_logistica["est1"])
    assert datos_logistica["est2"].estado == EstadoEstudio.EN_CAMINO_LAB_CENTRAL
    assert datos_logistica["est1"].estado == EstadoEstudio.LISTA_PARA_RETIRAR
    assert session.query(PosicionTransporte).filter_by(orden_id=orden_id).count() == 1

    # Doble recogida sobre la misma parada -> 409 Conflict
    resp_dup = client.post(
        f"/api/logistica/ordenes-del-dia/{orden_id}/paradas/{parada_cercana['parada_id']}/recoger",
        headers=headers,
    )
    assert resp_dup.status_code == 409
    assert "PARADA_YA_RETIRADA" in resp_dup.get_json()["error"]


def test_rechazo_recogida_por_transportista_otra_provincia_y_paciente(
    app, client, session, monkeypatch, datos_logistica
):
    """TC-06: Transportista ajeno o paciente recibe 403 Forbidden sin cambios en BD."""
    _fijar_fecha_hoy(monkeypatch, date(2026, 11, 17))
    mock_opt = MagicMock(spec=OptimizacionClient)
    mock_opt.optimizar_recorrido.side_effect = ClienteServicioError("offline", codigo_http=503)
    app.config["OPTIMIZACION_CLIENT"] = mock_opt

    headers_ba = _auth_header_para(app, datos_logistica["usuario_transp_ba"])
    orden_data = client.get("/api/logistica/ordenes-del-dia/hoy", headers=headers_ba).get_json()["data"]
    orden_id = orden_data["orden_id"]
    parada_id = orden_data["paradas"][0]["parada_id"]

    # Transportista de Cordoba intenta operar orden de Buenos Aires -> 403
    resp_cba = client.post(
        f"/api/logistica/ordenes-del-dia/{orden_id}/paradas/{parada_id}/recoger",
        headers=_auth_header_para(app, datos_logistica["usuario_transp_cba"]),
    )
    assert resp_cba.status_code == 403

    # Paciente intenta acceder -> 403
    resp_pac = client.get(
        "/api/logistica/ordenes-del-dia/hoy",
        headers=_auth_header_para(app, datos_logistica["usuario_paciente"]),
    )
    assert resp_pac.status_code == 403

    session.refresh(datos_logistica["est2"])
    assert datos_logistica["est2"].estado == EstadoEstudio.LISTA_PARA_RETIRAR


def test_llegada_laboratorio_central_actualiza_muestras_y_estudios(
    app, client, session, monkeypatch, datos_logistica
):
    """TC-07: Llegada al lab central sella muestras, mililitros y pasa estudios a EN_LAB_CENTRAL."""
    _fijar_fecha_hoy(monkeypatch, date(2026, 11, 17))
    mock_opt = MagicMock(spec=OptimizacionClient)
    mock_opt.optimizar_recorrido.side_effect = ClienteServicioError("offline", codigo_http=503)
    app.config["OPTIMIZACION_CLIENT"] = mock_opt
    headers = _auth_header_para(app, datos_logistica["usuario_transp_ba"])

    orden_data = client.get("/api/logistica/ordenes-del-dia/hoy", headers=headers).get_json()["data"]
    orden_id = orden_data["orden_id"]
    for p in orden_data["paradas"]:
        assert (
            client.post(
                f"/api/logistica/ordenes-del-dia/{orden_id}/paradas/{p['parada_id']}/recoger",
                headers=headers,
            ).status_code
            == 200
        )

    m1 = datos_logistica["muestra1"]
    m2 = datos_logistica["muestra2"]
    resp_llegada = client.post(
        f"/api/logistica/ordenes-del-dia/{orden_id}/llegada-laboratorio-central",
        json={
            "mililitros_por_muestra": [
                {"muestra_id": m1.id, "mililitros": 4.5},
                {"muestra_id": m2.id, "mililitros": 3.0},
            ]
        },
        headers=headers,
    )
    assert resp_llegada.status_code == 200
    data_lleg = resp_llegada.get_json()["data"]
    assert set(data_lleg["muestras_recibidas_ids"]) == {m1.id, m2.id}
    assert set(data_lleg["estudios_en_lab_central_ids"]) == {
        datos_logistica["est1"].id,
        datos_logistica["est2"].id,
    }

    session.refresh(m1)
    session.refresh(m2)
    session.refresh(datos_logistica["est1"])
    session.refresh(datos_logistica["est2"])
    assert m1.llegada_lab_central is not None
    assert m1.mililitros == Decimal("4.50")
    assert m2.mililitros == Decimal("3.00")
    assert datos_logistica["est1"].estado == EstadoEstudio.EN_LAB_CENTRAL
    assert datos_logistica["est2"].estado == EstadoEstudio.EN_LAB_CENTRAL

    # Segunda llegada cuando ya se entregaron todas las paradas retiradas -> 409
    resp_dup = client.post(
        f"/api/logistica/ordenes-del-dia/{orden_id}/llegada-laboratorio-central",
        headers=headers,
    )
    assert resp_dup.status_code == 409
    assert "LLEGADA_YA_REGISTRADA" in resp_dup.get_json()["error"]


def test_rechazo_llegada_sin_paradas_recogidas(
    app, client, session, monkeypatch, datos_logistica
):
    """TC-08: Rechaza llegada al laboratorio central (409 SIN_MUESTRAS_EN_CAMINO) si no recogio ninguna parada."""
    _fijar_fecha_hoy(monkeypatch, date(2026, 11, 17))
    mock_opt = MagicMock(spec=OptimizacionClient)
    mock_opt.optimizar_recorrido.side_effect = ClienteServicioError("offline", codigo_http=503)
    app.config["OPTIMIZACION_CLIENT"] = mock_opt
    headers = _auth_header_para(app, datos_logistica["usuario_transp_ba"])

    orden_data = client.get("/api/logistica/ordenes-del-dia/hoy", headers=headers).get_json()["data"]
    orden_id = orden_data["orden_id"]

    resp = client.post(
        f"/api/logistica/ordenes-del-dia/{orden_id}/llegada-laboratorio-central",
        headers=headers,
    )
    assert resp.status_code == 409
    assert "SIN_MUESTRAS_EN_CAMINO" in resp.get_json()["error"]
