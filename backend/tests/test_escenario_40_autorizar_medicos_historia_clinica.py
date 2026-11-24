"""Tests de aceptacion, seguridad API e integracion para Escenario 40: Autorizar medicos a historia clinica."""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from src.core.models import (
    Analisis,
    AnalisisGen,
    Aviso,
    CanalAviso,
    ConclusionDiagnostica,
    DatosCrudos,
    EntidadAuditable,
    Especialidad,
    EstadoEstudio,
    Estudio,
    EstudioGen,
    Familiar,
    Gen,
    Medico,
    MedicoEspecialidad,
    OrigenGen,
    Paciente,
    PacienteMedicoAutorizado,
    PacienteSintoma,
    Patologia,
    PatologiaSintoma,
    RegistroModificacion,
    Resultado,
    Rol,
    Sintoma,
    TipoAccionAuditoria,
    TipoAnalisis,
    Usuario,
)
from src.core.repos import auditoria_repo
from src.core.services import paciente_service
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)


def _headers_para(app, usuario: Usuario) -> dict[str, str]:
    token = emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return {"Authorization": f"Bearer {token}"}


def _crear_medico(
    session,
    *,
    email: str,
    nombre: str,
    apellido: str,
    matricula: str,
    especialidades: list[Especialidad],
    rol: Rol = Rol.MEDICO,
) -> tuple[Usuario, Medico]:
    usuario = Usuario(
        email=email,
        password_hash=hashear_password("Medico123!"),
        rol=rol,
        nombre=nombre,
        apellido=apellido,
        telefono="+5492214000001",
        debe_cambiar_password=False,
    )
    session.add(usuario)
    session.flush()
    medico = Medico(usuario_id=usuario.id, matricula=matricula)
    session.add(medico)
    session.flush()
    for esp in especialidades:
        session.add(MedicoEspecialidad(medico_id=medico.id, especialidad_id=esp.id))
    session.flush()
    return usuario, medico


def _crear_paciente(
    session,
    *,
    email: str,
    nombre: str,
    apellido: str,
    dni: str,
    medico_alta: Medico,
    patologia: Patologia,
    sintoma: Sintoma,
    historia_clinica: str,
    sembrar_autorizacion: bool = True,
    debe_cambiar_password: bool = False,
) -> tuple[Usuario, Paciente]:
    usuario = Usuario(
        email=email,
        password_hash=hashear_password("Paciente123!"),
        rol=Rol.PACIENTE,
        nombre=nombre,
        apellido=apellido,
        telefono="2215550000",
        debe_cambiar_password=debe_cambiar_password,
    )
    session.add(usuario)
    session.flush()
    paciente = Paciente(
        usuario_id=usuario.id,
        medico_id=medico_alta.id,
        dni=dni,
        fecha_nacimiento=date(1994, 6, 15),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica=historia_clinica,
        tipo_sospecha="clinica",
        familiograma_pdf_path="storage/familiogramas/demo.svg",
    )
    session.add(paciente)
    session.flush()
    session.add(PacienteSintoma(paciente_id=paciente.id, sintoma_id=sintoma.id))
    session.add(
        Familiar(
            paciente_id=paciente.id,
            parentesco="madre",
            nombre="Marta Lopez",
            diagnostico_previo="Fabry",
        )
    )
    if sembrar_autorizacion:
        session.add(
            PacienteMedicoAutorizado(
                paciente_id=paciente.id,
                medico_id=medico_alta.id,
                otorgada_por_usuario_id=medico_alta.usuario_id,
                activa=True,
                otorgada_en=datetime.now(UTC).replace(tzinfo=None),
            )
        )
    session.flush()
    return usuario, paciente


@pytest.fixture
def entorno_e40(app, session):
    """Prepara 4 medicos (incluyendo un gerente medico), 2 pacientes y roles auxiliares."""
    esp_gen = Especialidad(nombre="Genetica Medica")
    esp_hem = Especialidad(nombre="Hematologia")
    esp_neu = Especialidad(nombre="Neurologia")
    pat = Patologia(nombre="Fabry", descripcion="Enfermedad de Fabry")
    sintoma = Sintoma(snomed_id="225566008", descripcion="Acroparestesia")
    session.add_all([esp_gen, esp_hem, esp_neu, pat, sintoma])
    session.flush()
    session.add(PatologiaSintoma(patologia_id=pat.id, sintoma_id=sintoma.id, es_cardinal=True))

    u_m1, m1 = _crear_medico(
        session,
        email="dr.uno@hospital.org",
        nombre="Carlos",
        apellido="Alvarez",
        matricula="MP-1001",
        especialidades=[esp_gen],
    )
    u_m2, m2 = _crear_medico(
        session,
        email="dra.dos@hospital.org",
        nombre="Lucia",
        apellido="Benitez",
        matricula="MP-2002",
        especialidades=[esp_hem, esp_gen],
    )
    u_m3, m3 = _crear_medico(
        session,
        email="dr.tres@hospital.org",
        nombre="Martin",
        apellido="Castro",
        matricula="MP-3003",
        especialidades=[esp_neu],
    )
    u_m4, m4 = _crear_medico(
        session,
        email="dra.cuatro@hospital.org",
        nombre="Elena",
        apellido="Diaz",
        matricula="MP-4004",
        especialidades=[esp_gen],
        rol=Rol.GERENTE_MEDICO,
    )

    u_p1, p1 = _crear_paciente(
        session,
        email="p1@example.com",
        nombre="Sofia",
        apellido="Gomez",
        dni="40111222",
        medico_alta=m1,
        patologia=pat,
        sintoma=sintoma,
        historia_clinica="Dolor neuropatico distal desde la adolescencia e hipohidrosis.",
    )
    u_p2, p2 = _crear_paciente(
        session,
        email="p2@example.com",
        nombre="Diego",
        apellido="Morales",
        dni="40333444",
        medico_alta=m3,
        patologia=pat,
        sintoma=sintoma,
        historia_clinica="Historia clinica confidencial del paciente 2.",
    )

    u_admin = Usuario(
        email="admin.e40@lab.org",
        password_hash=hashear_password("Admin123!"),
        rol=Rol.ADMINISTRATIVO,
        nombre="Nadia",
        apellido="Silva",
        telefono="2214009900",
    )
    u_bio = Usuario(
        email="bio.e40@lab.org",
        password_hash=hashear_password("Bio12345!"),
        rol=Rol.BIOINFORMATICO,
        nombre="Ariadna",
        apellido="Guarino",
        telefono="2214009901",
    )
    session.add_all([u_admin, u_bio])
    session.commit()

    return {
        "esp_gen": esp_gen,
        "esp_hem": esp_hem,
        "esp_neu": esp_neu,
        "patologia": pat,
        "sintoma": sintoma,
        "u_m1": u_m1,
        "m1": m1,
        "u_m2": u_m2,
        "m2": m2,
        "u_m3": u_m3,
        "m3": m3,
        "u_m4": u_m4,
        "m4": m4,
        "u_p1": u_p1,
        "p1": p1,
        "u_p2": u_p2,
        "p2": p2,
        "u_admin": u_admin,
        "u_bio": u_bio,
    }


def test_tc01_autorizacion_multiple_simultanea_auditoria_avisos_y_consulta(
    app, client, session, entorno_e40, caplog
):
    """TC-01: Paciente autoriza a medico_2 y medico_3; ambos reciben aviso y acceden a historia clinica."""
    caplog.set_level(logging.INFO)
    p1 = entorno_e40["p1"]
    m1, m2, m3 = entorno_e40["m1"], entorno_e40["m2"], entorno_e40["m3"]
    hdr_p1 = _headers_para(app, entorno_e40["u_p1"])

    # STEP 1: Directorio muestra solo a m1 autorizado inicialmente
    resp_dir = client.get("/api/v1/medicos", headers=hdr_p1)
    assert resp_dir.status_code == 200
    assert resp_dir.headers["Cache-Control"] == "private, no-store"
    assert resp_dir.headers["X-Content-Type-Options"] == "nosniff"
    dir_data = resp_dir.get_json()["data"]
    assert dir_data["medicos_autorizados_activos_ids"] == [m1.id]
    por_id = {m["medico_id"]: m for m in dir_data["medicos"]}
    assert por_id[m1.id]["autorizado"] is True
    assert por_id[m2.id]["autorizado"] is False

    # STEP 2: Autorizacion multiple
    resp_post = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": [m2.id, m3.id], "motivo": "Interconsulta hematologica"},
    )
    assert resp_post.status_code == 201
    post_data = resp_post.get_json()["data"]
    assert post_data["nuevos_autorizados_ids"] == [m2.id, m3.id]
    assert post_data["ya_autorizados_ids"] == []
    assert post_data["medicos_autorizados_activos_ids"] == sorted([m1.id, m2.id, m3.id])

    # DB: filas activas en pacientes_medicos_autorizados
    activas = session.scalars(
        select(PacienteMedicoAutorizado).where(
            PacienteMedicoAutorizado.paciente_id == p1.id,
            PacienteMedicoAutorizado.activa.is_(True),
        )
    ).all()
    assert sorted(a.medico_id for a in activas) == sorted([m1.id, m2.id, m3.id])
    for aut in activas:
        if aut.medico_id in (m2.id, m3.id):
            assert aut.otorgada_por_usuario_id == entorno_e40["u_p1"].id
            assert aut.revocada_en is None

    # DB: 1 registro en registro_modificaciones con medicos_autorizados_ids
    registros = session.scalars(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.PACIENTE,
            RegistroModificacion.entidad_id == p1.id,
        )
    ).all()
    assert len(registros) == 1
    assert registros[0].accion == TipoAccionAuditoria.MODIFICACION
    assert registros[0].usuario_id == entorno_e40["u_p1"].id
    assert registros[0].origen == "usuario"
    assert registros[0].motivo == "Interconsulta hematologica"
    assert registros[0].cambios == {
        "medicos_autorizados_ids": {
            "anterior": [m1.id],
            "nuevo": sorted([m1.id, m2.id, m3.id]),
        }
    }

    # DB: ambos medicos recién autorizados reciben Aviso (m1 no recibe aviso duplicado)
    avisos_m2 = session.scalars(
        select(Aviso).where(Aviso.usuario_id == entorno_e40["u_m2"].id, Aviso.canal == CanalAviso.APP)
    ).all()
    avisos_m3 = session.scalars(
        select(Aviso).where(Aviso.usuario_id == entorno_e40["u_m3"].id, Aviso.canal == CanalAviso.APP)
    ).all()
    avisos_m1 = session.scalars(
        select(Aviso).where(Aviso.usuario_id == entorno_e40["u_m1"].id, Aviso.canal == CanalAviso.APP)
    ).all()
    assert len(avisos_m2) == 1 and "Sofia Gomez" in avisos_m2[0].mensaje
    assert len(avisos_m3) == 1 and "Sofia Gomez" in avisos_m3[0].mensaje
    assert avisos_m1 == []

    # STEP 4: Ambos medicos consultan la historia clinica y ven al paciente en su listado
    for u_med in (entorno_e40["u_m2"], entorno_e40["u_m3"]):
        hdr_med = _headers_para(app, u_med)
        resp_hc = client.get(f"/api/v1/pacientes/{p1.id}/historia-clinica", headers=hdr_med)
        assert resp_hc.status_code == 200
        assert resp_hc.headers["Cache-Control"] == "private, no-store"
        hc = resp_hc.get_json()["data"]
        assert hc["paciente_id"] == p1.id
        assert hc["historia_clinica"] == p1.historia_clinica
        assert hc["diagnostico_presuntivo"]["nombre"] == "Fabry"
        assert hc["tipo_sospecha"] == "clinica"
        assert len(hc["sintomas"]) == 1
        assert len(hc["familiares"]) == 1
        assert hc["familiograma_pdf_path"] == "storage/familiogramas/demo.svg"
        assert sorted(m["medico_id"] for m in hc["medicos_autorizados"]) == sorted(
            [m1.id, m2.id, m3.id]
        )

        resp_lista = client.get("/api/v1/pacientes", headers=hdr_med)
        assert resp_lista.status_code == 200
        ids_pac = [item["paciente_id"] for item in resp_lista.get_json()["data"]]
        assert p1.id in ids_pac

    # Listado propio del paciente
    resp_propio = client.get(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
    )
    assert resp_propio.status_code == 200
    assert resp_propio.get_json()["data"]["medicos_autorizados_activos_ids"] == sorted(
        [m1.id, m2.id, m3.id]
    )

    assert "STEP 1 directorio_medicos_consultado" in caplog.text
    assert "STEP 2 medicos_autorizados" in caplog.text
    assert "STEP 4 historia_clinica_consultada" in caplog.text


def test_tc02_idempotencia_ante_medico_ya_autorizado(app, client, session, entorno_e40):
    """TC-02: Reenviar un medico ya autorizado retorna 200 OK sin duplicar filas, avisos ni auditoria."""
    p1 = entorno_e40["p1"]
    m2, m3 = entorno_e40["m2"], entorno_e40["m3"]
    hdr_p1 = _headers_para(app, entorno_e40["u_p1"])

    resp1 = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": [m2.id, m2.id]},
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": [m2.id]},
    )
    assert resp2.status_code == 200
    data2 = resp2.get_json()["data"]
    assert data2["nuevos_autorizados_ids"] == []
    assert data2["ya_autorizados_ids"] == [m2.id]

    filas_m2 = session.scalars(
        select(PacienteMedicoAutorizado).where(
            PacienteMedicoAutorizado.paciente_id == p1.id,
            PacienteMedicoAutorizado.medico_id == m2.id,
        )
    ).all()
    assert len(filas_m2) == 1
    assert len(session.scalars(select(RegistroModificacion)).all()) == 1
    assert (
        len(
            session.scalars(
                select(Aviso).where(Aviso.usuario_id == entorno_e40["u_m2"].id)
            ).all()
        )
        == 1
    )

    # Mezcla de ya autorizado (m2) + nuevo (m3): solo inserta/avisa a m3
    resp3 = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": [m2.id, m3.id]},
    )
    assert resp3.status_code == 201
    data3 = resp3.get_json()["data"]
    assert data3["nuevos_autorizados_ids"] == [m3.id]
    assert data3["ya_autorizados_ids"] == [m2.id]


def test_tc03_revocacion_logica_auditoria_y_bloqueo_inmediato(
    app, client, session, entorno_e40, caplog
):
    """TC-03: Revocar pasa activa=False con revocada_en, audita, avisa y bloquea acceso inmediato."""
    caplog.set_level(logging.INFO)
    p1 = entorno_e40["p1"]
    m1, m2 = entorno_e40["m1"], entorno_e40["m2"]
    hdr_p1 = _headers_para(app, entorno_e40["u_p1"])
    hdr_m2 = _headers_para(app, entorno_e40["u_m2"])
    hdr_m1 = _headers_para(app, entorno_e40["u_m1"])

    assert (
        client.post(
            "/api/v1/pacientes/mi-perfil/medicos-autorizados",
            headers=hdr_p1,
            json={"medicos_ids": [m2.id]},
        ).status_code
        == 201
    )
    assert client.get(f"/api/v1/pacientes/{p1.id}/historia-clinica", headers=hdr_m2).status_code == 200

    # Revoca a m2 con motivo por JSON
    resp_del = client.delete(
        f"/api/v1/pacientes/mi-perfil/medicos-autorizados/{m2.id}",
        headers=hdr_p1,
        json={"motivo": "Fin de interconsulta"},
    )
    assert resp_del.status_code == 200
    del_data = resp_del.get_json()["data"]
    assert del_data["autorizacion_revocada"]["activa"] is False
    assert del_data["autorizacion_revocada"]["revocada_en"] is not None
    assert del_data["medicos_autorizados_activos_ids"] == [m1.id]

    fila_m2 = session.scalar(
        select(PacienteMedicoAutorizado).where(
            PacienteMedicoAutorizado.paciente_id == p1.id,
            PacienteMedicoAutorizado.medico_id == m2.id,
        )
    )
    assert fila_m2 is not None
    assert fila_m2.activa is False
    assert fila_m2.revocada_en is not None

    # Auditoria refleja la revocacion
    ult_reg = session.scalars(
        select(RegistroModificacion)
        .where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.PACIENTE,
            RegistroModificacion.entidad_id == p1.id,
        )
        .order_by(RegistroModificacion.id.desc())
    ).first()
    assert ult_reg is not None
    assert ult_reg.motivo == "Fin de interconsulta"
    assert ult_reg.cambios == {
        "medicos_autorizados_ids": {
            "anterior": sorted([m1.id, m2.id]),
            "nuevo": [m1.id],
        }
    }

    # Medico 2 recibe aviso de revocacion y queda bloqueado de inmediato
    avisos_m2 = session.scalars(
        select(Aviso)
        .where(Aviso.usuario_id == entorno_e40["u_m2"].id)
        .order_by(Aviso.id.desc())
    ).all()
    assert len(avisos_m2) == 2
    assert "revoco" in avisos_m2[0].mensaje.lower()

    resp_bloqueado = client.get(f"/api/v1/pacientes/{p1.id}/historia-clinica", headers=hdr_m2)
    assert resp_bloqueado.status_code == 403
    assert resp_bloqueado.get_json()["code"] == "HISTORIA_CLINICA_NO_AUTORIZADA"

    # Tambien desaparece de su listado de pacientes y familiares
    resp_pac_m2 = client.get("/api/v1/pacientes", headers=hdr_m2)
    assert p1.id not in [item["paciente_id"] for item in resp_pac_m2.get_json()["data"]]
    resp_fam_m2 = client.get(f"/api/v1/pacientes/{p1.id}/familiares", headers=hdr_m2)
    assert resp_fam_m2.status_code == 403

    # Reintentar revocar retorna 404 AUTORIZACION_NO_ACTIVA
    resp_del_2 = client.delete(
        f"/api/v1/pacientes/mi-perfil/medicos-autorizados/{m2.id}",
        headers=hdr_p1,
    )
    assert resp_del_2.status_code == 404
    assert resp_del_2.get_json()["code"] == "AUTORIZACION_NO_ACTIVA"

    # Autonomia del paciente: puede revocar incluso al medico de alta (m1) sin activar fallback
    resp_del_m1 = client.delete(
        f"/api/v1/pacientes/mi-perfil/medicos-autorizados/{m1.id}?motivo=Cambio+de+medico",
        headers=hdr_p1,
    )
    assert resp_del_m1.status_code == 200
    assert resp_del_m1.get_json()["data"]["medicos_autorizados_activos_ids"] == []
    resp_m1_bloqueado = client.get(f"/api/v1/pacientes/{p1.id}/historia-clinica", headers=hdr_m1)
    assert resp_m1_bloqueado.status_code == 403
    assert "STEP 3 autorizacion_revocada" in caplog.text


def test_tc04_reautorizacion_historica_y_indice_unico_parcial(app, client, session, entorno_e40):
    """TC-04: Re-autorizar crea nueva fila activa preservando la fila revocada; indice parcial impide duplicados activos."""
    p1 = entorno_e40["p1"]
    m2 = entorno_e40["m2"]
    hdr_p1 = _headers_para(app, entorno_e40["u_p1"])
    hdr_m2 = _headers_para(app, entorno_e40["u_m2"])

    assert (
        client.post(
            "/api/v1/pacientes/mi-perfil/medicos-autorizados",
            headers=hdr_p1,
            json={"medicos_ids": [m2.id]},
        ).status_code
        == 201
    )
    assert (
        client.delete(
            f"/api/v1/pacientes/mi-perfil/medicos-autorizados/{m2.id}",
            headers=hdr_p1,
        ).status_code
        == 200
    )

    resp_reaut = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": [m2.id], "motivo": "Nueva consulta"},
    )
    assert resp_reaut.status_code == 201

    filas = session.scalars(
        select(PacienteMedicoAutorizado)
        .where(
            PacienteMedicoAutorizado.paciente_id == p1.id,
            PacienteMedicoAutorizado.medico_id == m2.id,
        )
        .order_by(PacienteMedicoAutorizado.id.asc())
    ).all()
    assert len(filas) == 2
    assert filas[0].activa is False and filas[0].revocada_en is not None
    assert filas[1].activa is True and filas[1].revocada_en is None

    assert client.get(f"/api/v1/pacientes/{p1.id}/historia-clinica", headers=hdr_m2).status_code == 200

    # El indice unico parcial uq_paciente_medico_activo impide una segunda fila activa para el mismo par
    session.add(
        PacienteMedicoAutorizado(
            paciente_id=p1.id,
            medico_id=m2.id,
            otorgada_por_usuario_id=entorno_e40["u_p1"].id,
            activa=True,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_tc05_medico_no_autorizado_gerente_y_paciente_inexistente(app, client, entorno_e40):
    """TC-05: Medico/gerente sin autorizacion recibe 403; paciente inexistente recibe 404."""
    p1 = entorno_e40["p1"]
    m4 = entorno_e40["m4"]
    hdr_m4 = _headers_para(app, entorno_e40["u_m4"])
    hdr_p1 = _headers_para(app, entorno_e40["u_p1"])

    resp_403 = client.get(f"/api/v1/pacientes/{p1.id}/historia-clinica", headers=hdr_m4)
    assert resp_403.status_code == 403
    assert resp_403.get_json()["code"] == "HISTORIA_CLINICA_NO_AUTORIZADA"

    resp_404 = client.get("/api/v1/pacientes/999999/historia-clinica", headers=hdr_m4)
    assert resp_404.status_code == 404
    assert resp_404.get_json()["code"] == "PACIENTE_NO_ENCONTRADO"

    # Cuando el paciente autoriza al GERENTE_MEDICO (m4), puede consultar la historia clinica
    assert (
        client.post(
            "/api/v1/pacientes/mi-perfil/medicos-autorizados",
            headers=hdr_p1,
            json={"medicos_ids": [m4.id]},
        ).status_code
        == 201
    )
    resp_ok = client.get(f"/api/v1/pacientes/{p1.id}/historia-clinica", headers=hdr_m4)
    assert resp_ok.status_code == 200


def test_tc06_propiedad_del_perfil_aislamiento_entre_pacientes(app, client, session, entorno_e40):
    """TC-06 (IDOR / BOLA): Paciente P2 solo opera sobre su propio perfil derivado del JWT."""
    p1, p2 = entorno_e40["p1"], entorno_e40["p2"]
    m1, m2 = entorno_e40["m1"], entorno_e40["m2"]
    hdr_p2 = _headers_para(app, entorno_e40["u_p2"])

    # P2 intenta inyectar paciente_id de P1 en el body (mass assignment)
    resp_post = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p2,
        json={"paciente_id": p1.id, "medicos_ids": [m2.id]},
    )
    assert resp_post.status_code == 201
    assert resp_post.get_json()["data"]["paciente_id"] == p2.id

    # P1 sigue teniendo unicamente a m1 autorizado
    activas_p1 = session.scalars(
        select(PacienteMedicoAutorizado).where(
            PacienteMedicoAutorizado.paciente_id == p1.id,
            PacienteMedicoAutorizado.activa.is_(True),
        )
    ).all()
    assert [a.medico_id for a in activas_p1] == [m1.id]

    # P2 intenta revocar al medico m1 (autorizado en P1, no en P2)
    resp_del = client.delete(
        f"/api/v1/pacientes/mi-perfil/medicos-autorizados/{m1.id}",
        headers=hdr_p2,
    )
    assert resp_del.status_code == 404
    assert resp_del.get_json()["code"] == "AUTORIZACION_NO_ACTIVA"

    # Autorizacion de m1 sobre P1 permanece intacta
    assert (
        client.get(
            f"/api/v1/pacientes/{p1.id}/historia-clinica",
            headers=_headers_para(app, entorno_e40["u_m1"]),
        ).status_code
        == 200
    )


def test_directorio_filtros_privacidad_y_seguridad_sqli(app, client, session, entorno_e40):
    """Valida filtros q/especialidad_id, minimizacion de datos privados y seguridad ante SQLi."""
    hdr_p1 = _headers_para(app, entorno_e40["u_p1"])
    esp_hem = entorno_e40["esp_hem"]
    m2 = entorno_e40["m2"]

    # Filtro por especialidad
    resp_esp = client.get(f"/api/v1/medicos?especialidad_id={esp_hem.id}", headers=hdr_p1)
    assert resp_esp.status_code == 200
    meds_hem = resp_esp.get_json()["data"]["medicos"]
    assert [m["medico_id"] for m in meds_hem] == [m2.id]

    # Filtro por texto (nombre completo, matricula y especialidad)
    for query in ("Lucia Benitez", "MP-2002", "hemato"):
        resp_q = client.get(f"/api/v1/medicos?q={query}", headers=hdr_p1)
        assert resp_q.status_code == 200
        assert [m["medico_id"] for m in resp_q.get_json()["data"]["medicos"]] == [m2.id]

    # Privacidad: nunca expone email, telefono, password_hash ni usuario_id
    resp_all = client.get("/api/v1/medicos", headers=hdr_p1)
    campos_sensibles = {"email", "telefono", "password_hash", "usuario_id"}
    for med in resp_all.get_json()["data"]["medicos"]:
        assert campos_sensibles.isdisjoint(med.keys())

    # SQL injection y caracteres comodines literales en q
    for payload_sqli in ("'; DROP TABLE medicos; --", "%", "_"):
        resp_sqli = client.get("/api/v1/medicos", query_string={"q": payload_sqli}, headers=hdr_p1)
        assert resp_sqli.status_code == 200
        assert resp_sqli.get_json()["data"]["medicos"] == []
    assert len(session.scalars(select(Medico)).all()) == 4

    # Parametro especialidad_id invalido
    for invalido in ("abc", "0", "-3"):
        resp_bad = client.get(f"/api/v1/medicos?especialidad_id={invalido}", headers=hdr_p1)
        assert resp_bad.status_code == 400
        assert resp_bad.get_json()["code"] == "DATOS_INVALIDOS"


def test_validaciones_payload_y_rollback_medico_inexistente(app, client, session, entorno_e40):
    """Lista vacia -> 422 LISTA_MEDICOS_VACIA; medico inexistente -> 404 MEDICO_NO_ENCONTRADO con rollback."""
    p1 = entorno_e40["p1"]
    m1, m2 = entorno_e40["m1"], entorno_e40["m2"]
    hdr_p1 = _headers_para(app, entorno_e40["u_p1"])

    resp_vacia = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": []},
    )
    assert resp_vacia.status_code == 422
    assert resp_vacia.get_json()["code"] == "LISTA_MEDICOS_VACIA"

    resp_invalido = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": [True]},
    )
    assert resp_invalido.status_code == 400
    assert resp_invalido.get_json()["code"] == "DATOS_INVALIDOS"

    resp_neg = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": [-1]},
    )
    assert resp_neg.status_code == 422

    # Un ID valido + uno inexistente: falla todo con 404 y no autoriza parcialmente a m2
    resp_404 = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": [m2.id, 999999]},
    )
    assert resp_404.status_code == 404
    assert resp_404.get_json()["code"] == "MEDICO_NO_ENCONTRADO"

    activas = session.scalars(
        select(PacienteMedicoAutorizado).where(
            PacienteMedicoAutorizado.paciente_id == p1.id,
            PacienteMedicoAutorizado.activa.is_(True),
        )
    ).all()
    assert [a.medico_id for a in activas] == [m1.id]
    assert session.scalars(select(RegistroModificacion)).all() == []
    assert session.scalars(select(Aviso)).all() == []


def test_autenticacion_y_rbac_todos_los_endpoints(app, client, session, entorno_e40):
    """Verifica 401 sin token, 403 con password inicial pendiente y 403 por rol en los 5 endpoints."""
    p1 = entorno_e40["p1"]
    m2 = entorno_e40["m2"]

    # Sin autenticacion -> 401
    assert client.get("/api/v1/medicos").status_code == 401
    assert client.get("/api/v1/pacientes/mi-perfil/medicos-autorizados").status_code == 401
    assert client.post("/api/v1/pacientes/mi-perfil/medicos-autorizados", json={"medicos_ids": [m2.id]}).status_code == 401
    assert client.delete(f"/api/v1/pacientes/mi-perfil/medicos-autorizados/{m2.id}").status_code == 401
    assert client.get(f"/api/v1/pacientes/{p1.id}/historia-clinica").status_code == 401

    # Roles no-paciente rechazados en endpoints del portal de paciente
    for usuario_no_pac in (entorno_e40["u_m1"], entorno_e40["u_admin"], entorno_e40["u_bio"]):
        hdr = _headers_para(app, usuario_no_pac)
        assert client.get("/api/v1/medicos", headers=hdr).status_code == 403
        assert client.get("/api/v1/pacientes/mi-perfil/medicos-autorizados", headers=hdr).status_code == 403
        assert (
            client.post(
                "/api/v1/pacientes/mi-perfil/medicos-autorizados",
                headers=hdr,
                json={"medicos_ids": [m2.id]},
            ).status_code
            == 403
        )
        assert (
            client.delete(
                f"/api/v1/pacientes/mi-perfil/medicos-autorizados/{m2.id}",
                headers=hdr,
            ).status_code
            == 403
        )

    # Roles no-medico rechazados en consulta de historia clinica
    for usuario_no_med in (entorno_e40["u_p1"], entorno_e40["u_admin"], entorno_e40["u_bio"]):
        hdr = _headers_para(app, usuario_no_med)
        assert client.get(f"/api/v1/pacientes/{p1.id}/historia-clinica", headers=hdr).status_code == 403

    # Paciente que aun no cambio contrasena inicial -> 403 DEBE_CAMBIAR_PASSWORD_INICIAL
    u_pend, _ = _crear_paciente(
        session,
        email="pendiente@example.com",
        nombre="Tomas",
        apellido="Vega",
        dni="40999888",
        medico_alta=entorno_e40["m1"],
        patologia=entorno_e40["patologia"],
        sintoma=entorno_e40["sintoma"],
        historia_clinica="Pendiente de primer ingreso.",
        debe_cambiar_password=True,
    )
    session.commit()
    resp_pend = client.get("/api/v1/medicos", headers=_headers_para(app, u_pend))
    assert resp_pend.status_code == 403
    assert resp_pend.get_json()["code"] == "DEBE_CAMBIAR_PASSWORD_INICIAL"


def test_atomicidad_rollback_si_falla_auditoria(app, client, session, entorno_e40, monkeypatch):
    """Si falla la escritura en registro_modificaciones, hace rollback completo de autorizacion y aviso."""
    p1 = entorno_e40["p1"]
    m1, m2 = entorno_e40["m1"], entorno_e40["m2"]
    hdr_p1 = _headers_para(app, entorno_e40["u_p1"])

    def _fallar_auditoria(**kwargs):
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr(auditoria_repo, "registrar_modificacion", _fallar_auditoria)

    resp_post = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=hdr_p1,
        json={"medicos_ids": [m2.id]},
    )
    assert resp_post.status_code == 500
    assert resp_post.get_json()["retryable"] is True

    activas = session.scalars(
        select(PacienteMedicoAutorizado).where(
            PacienteMedicoAutorizado.paciente_id == p1.id,
            PacienteMedicoAutorizado.activa.is_(True),
        )
    ).all()
    assert [a.medico_id for a in activas] == [m1.id]
    assert session.scalars(select(Aviso)).all() == []

    # Tambien verifica rollback al fallar auditoria durante revocacion
    resp_del = client.delete(
        f"/api/v1/pacientes/mi-perfil/medicos-autorizados/{m1.id}",
        headers=hdr_p1,
    )
    assert resp_del.status_code == 500
    activas_post_del = session.scalars(
        select(PacienteMedicoAutorizado).where(
            PacienteMedicoAutorizado.paciente_id == p1.id,
            PacienteMedicoAutorizado.activa.is_(True),
        )
    ).all()
    assert [a.medico_id for a in activas_post_del] == [m1.id]


def test_alta_paciente_siembra_autorizacion_inicial_y_compatibilidad_legacy(
    app, client, session, entorno_e40, monkeypatch
):
    """Verifica siembra automatica en Esc. 01/19 y compatibilidad transitoria para pacientes pre-migracion."""
    m1, m2 = entorno_e40["m1"], entorno_e40["m2"]
    pat, sintoma = entorno_e40["patologia"], entorno_e40["sintoma"]
    monkeypatch.setattr(
        paciente_service,
        "EmailClient",
        type("_FakeMail", (), {"__init__": lambda *a, **k: None, "enviar_aviso": lambda *a, **k: {"ok": True}}),
    )

    resp_alta = client.post(
        "/api/v1/pacientes",
        headers=_headers_para(app, entorno_e40["u_m1"]),
        json={
            "dni": "41555666",
            "nombre": "Valeria",
            "apellido": "Rios",
            "telefono": "2215557788",
            "email": "valeria.rios@example.com",
            "fecha_nacimiento": "1997-08-20",
            "diagnostico_presuntivo_id": pat.id,
            "historia_clinica": "Historia inicial sembrada desde alta.",
            "tipo_sospecha": "clinica",
            "sintomas_snomed_ids": [sintoma.snomed_id],
            "sin_informacion_familiar": True,
            "familiares": [],
        },
    )
    assert resp_alta.status_code == 201
    nuevo_id = resp_alta.get_json()["data"]["paciente_id"]

    aut_inicial = session.scalars(
        select(PacienteMedicoAutorizado).where(PacienteMedicoAutorizado.paciente_id == nuevo_id)
    ).all()
    assert len(aut_inicial) == 1
    assert aut_inicial[0].medico_id == m1.id
    assert aut_inicial[0].activa is True

    reg_alta = session.scalar(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.PACIENTE,
            RegistroModificacion.entidad_id == nuevo_id,
            RegistroModificacion.accion == TipoAccionAuditoria.CREACION,
        )
    )
    assert reg_alta is not None
    assert "password_hash" not in reg_alta.cambios
    assert reg_alta.cambios["medicos_autorizados_ids"] == {"anterior": [], "nuevo": [m1.id]}

    # Paciente legacy (sin filas en pacientes_medicos_autorizados)
    u_leg, p_leg = _crear_paciente(
        session,
        email="legacy@example.com",
        nombre="Raul",
        apellido="Paz",
        dni="30123456",
        medico_alta=m1,
        patologia=pat,
        sintoma=sintoma,
        historia_clinica="Historia previa a la migracion.",
        sembrar_autorizacion=False,
    )
    session.commit()

    # Compatibilidad en lectura: m1 accede, m2 recibe 403
    assert (
        client.get(
            f"/api/v1/pacientes/{p_leg.id}/historia-clinica",
            headers=_headers_para(app, entorno_e40["u_m1"]),
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/pacientes/{p_leg.id}/historia-clinica",
            headers=_headers_para(app, entorno_e40["u_m2"]),
        ).status_code
        == 403
    )

    # Al autorizar a m2, se materializa m1 y ambos quedan activos sin perder a m1
    resp_leg_aut = client.post(
        "/api/v1/pacientes/mi-perfil/medicos-autorizados",
        headers=_headers_para(app, u_leg),
        json={"medicos_ids": [m2.id]},
    )
    assert resp_leg_aut.status_code == 201
    assert resp_leg_aut.get_json()["data"]["medicos_autorizados_activos_ids"] == sorted(
        [m1.id, m2.id]
    )


def test_handoff_medico_autorizado_accede_a_resultado_y_pierde_acceso_al_revocar(
    app, client, session, entorno_e40, tmp_path
):
    """Handoff E40 -> E37/E17: Medico autorizado ve estudio/resultado del paciente y al revocarlo recibe 403."""
    app.config["STORAGE_DIR"] = str(tmp_path)
    p1 = entorno_e40["p1"]
    m1, m2 = entorno_e40["m1"], entorno_e40["m2"]
    pat = entorno_e40["patologia"]
    hdr_p1 = _headers_para(app, entorno_e40["u_p1"])
    hdr_m2 = _headers_para(app, entorno_e40["u_m2"])

    gen = Gen(simbolo="GLA", nombre="Alpha-galactosidase A")
    session.add(gen)
    session.flush()
    estudio = Estudio(
        paciente_id=p1.id,
        medico_id=m1.id,
        patologia_sospechada_id=pat.id,
        estado=EstadoEstudio.RESULTADO_CARGADO,
    )
    session.add(estudio)
    session.flush()
    session.add(EstudioGen(estudio_id=estudio.id, gen_id=gen.id, origen=OrigenGen.PATOLOGIA))
    session.add(
        DatosCrudos(
            estudio_id=estudio.id,
            cargado_por_id=entorno_e40["u_admin"].id,
            archivo_path=f"storage/datos_crudos/estudio_{estudio.id}.txt",
        )
    )
    analisis = Analisis(
        estudio_id=estudio.id,
        tipo=TipoAnalisis.INICIAL,
        bioinformatico_id=entorno_e40["u_bio"].id,
    )
    session.add(analisis)
    session.flush()
    session.add(AnalisisGen(analisis_id=analisis.id, gen_id=gen.id))
    session.add(
        Resultado(
            analisis_id=analisis.id,
            positivo=False,
            diagnostico=ConclusionDiagnostica.NEGATIVO,
            pdf_path=f"storage/resultados/resultado_analisis_{analisis.id}.pdf",
            generado_en=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    session.commit()

    # Sin autorizacion, m2 no ve el resultado
    assert client.get(f"/api/estudios/{estudio.id}/resultado", headers=hdr_m2).status_code == 403

    # Tras autorizacion de historia clinica, m2 ve el estudio en mis-estudios y accede al resultado
    assert (
        client.post(
            "/api/v1/pacientes/mi-perfil/medicos-autorizados",
            headers=hdr_p1,
            json={"medicos_ids": [m2.id]},
        ).status_code
        == 201
    )
    resp_estudios = client.get("/api/estudios/mis-estudios", headers=hdr_m2)
    assert resp_estudios.status_code == 200
    assert estudio.id in [e["estudio_id"] for e in resp_estudios.get_json()["estudios"]]

    resp_res = client.get(f"/api/estudios/{estudio.id}/resultado", headers=hdr_m2)
    assert resp_res.status_code == 200

    # Tras revocacion, m2 vuelve a recibir 403 en el resultado
    assert (
        client.delete(
            f"/api/v1/pacientes/mi-perfil/medicos-autorizados/{m2.id}",
            headers=hdr_p1,
        ).status_code
        == 200
    )
    assert client.get(f"/api/estudios/{estudio.id}/resultado", headers=hdr_m2).status_code == 403
