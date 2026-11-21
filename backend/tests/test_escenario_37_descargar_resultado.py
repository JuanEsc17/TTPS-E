"""Tests de aceptacion y seguridad API para Escenario 37: Descargar el resultado de un estudio."""
from __future__ import annotations

import logging
import re
import zlib
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from src.clients import EmailClient
from src.clients.exceptions import ClienteServicioError
from src.core.models import (
    Analisis,
    AnalisisGen,
    Aviso,
    CanalAviso,
    ClasificacionVariante,
    ConclusionDiagnostica,
    DatosCrudos,
    EstadoEstudio,
    Estudio,
    EstudioGen,
    Gen,
    Medico,
    OrigenGen,
    Paciente,
    Patologia,
    Resultado,
    Rol,
    TipoAnalisis,
    Usuario,
    Variante,
)
from src.core.repos import bioinformatica_repo
from src.core.services import resultado_service
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)


def _extraer_texto_pdf(pdf_bytes: bytes) -> str:
    """Extrae texto legible de streams FlateDecode de un PDF generado con fpdf2 usando stdlib."""
    partes: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, flags=re.DOTALL):
        crudo = match.group(1)
        try:
            descomprimido = zlib.decompress(crudo)
        except zlib.error:
            descomprimido = crudo
        texto = descomprimido.decode("latin-1", errors="ignore")
        texto = texto.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
        partes.append(texto)
    return "\n".join(partes)


def _headers_para(app, usuario: Usuario) -> dict[str, str]:
    token = emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def datos_escenario_37(app, session, tmp_path):
    """Prepara actores, patologia Fabry, genes GLA/BRCA1, estudio listo para cargar y variantes."""
    app.config["STORAGE_DIR"] = str(tmp_path)

    u_bio = Usuario(
        email="bio.e37@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.BIOINFORMATICO,
        nombre="Ariadna",
        apellido="Guarino",
        telefono="1144003701",
    )
    u_medico = Usuario(
        email="medico.e37@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.MEDICO,
        nombre="Juan",
        apellido="Escudero",
        telefono="1144003702",
    )
    u_medico_otro = Usuario(
        email="medico.otro.e37@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.MEDICO,
        nombre="Clara",
        apellido="Mendez",
        telefono="1144003703",
    )
    u_paciente = Usuario(
        email="paciente.e37@gmail.com",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.PACIENTE,
        nombre="Sofia",
        apellido="Perez",
        telefono="1144003704",
    )
    u_paciente_otro = Usuario(
        email="paciente.otro.e37@gmail.com",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.PACIENTE,
        nombre="Lucas",
        apellido="Gomez",
        telefono="1144003705",
    )
    u_admin = Usuario(
        email="admin.e37@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.ADMINISTRATIVO,
        nombre="Laura",
        apellido="Diaz",
        telefono="1144003706",
    )
    session.add_all([u_bio, u_medico, u_medico_otro, u_paciente, u_paciente_otro, u_admin])
    session.flush()

    patologia = Patologia(nombre="Fabry", descripcion="Enfermedad lisosomal ligada al X")
    gen_gla = Gen(simbolo="GLA", nombre="Galactosidasa alfa", es_hallazgo_secundario=False)
    gen_brca1 = Gen(simbolo="BRCA1", nombre="BRCA1 DNA repair", es_hallazgo_secundario=True)
    session.add_all([patologia, gen_gla, gen_brca1])
    session.flush()

    medico = Medico(usuario_id=u_medico.id, matricula="MN-37001")
    medico_otro = Medico(usuario_id=u_medico_otro.id, matricula="MN-37002")
    session.add_all([medico, medico_otro])
    session.flush()

    paciente = Paciente(
        usuario_id=u_paciente.id,
        medico_id=medico.id,
        dni="40373737",
        fecha_nacimiento=date(1994, 8, 20),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="Sospecha clinica de Fabry",
        tipo_sospecha="clinica",
    )
    paciente_otro = Paciente(
        usuario_id=u_paciente_otro.id,
        medico_id=medico_otro.id,
        dni="40989898",
        fecha_nacimiento=date(1991, 3, 10),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="Otro paciente",
        tipo_sospecha="clinica",
    )
    session.add_all([paciente, paciente_otro])
    session.flush()

    estudio = Estudio(
        paciente_id=paciente.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.EN_ANALISIS_BIOINFORMATICO,
        es_pompe_urgente=False,
    )
    session.add(estudio)
    session.flush()

    session.add_all(
        [
            EstudioGen(estudio_id=estudio.id, gen_id=gen_gla.id, origen=OrigenGen.PATOLOGIA),
            EstudioGen(
                estudio_id=estudio.id,
                gen_id=gen_brca1.id,
                origen=OrigenGen.HALLAZGO_SECUNDARIO,
            ),
        ]
    )
    session.add(
        DatosCrudos(
            estudio_id=estudio.id,
            cargado_por_id=u_admin.id,
            archivo_path=f"storage/datos_crudos/estudio_{estudio.id}.txt",
        )
    )

    analisis = Analisis(
        estudio_id=estudio.id,
        tipo=TipoAnalisis.INICIAL,
        bioinformatico_id=u_bio.id,
    )
    session.add(analisis)
    session.flush()
    session.add_all(
        [
            AnalisisGen(analisis_id=analisis.id, gen_id=gen_gla.id),
            AnalisisGen(analisis_id=analisis.id, gen_id=gen_brca1.id),
        ]
    )

    v_pat = Variante(
        gen_id=gen_gla.id,
        notacion="c.644A>G",
        clinvar_id="VCV000010730",
        clasificacion=ClasificacionVariante.PATOGENICA,
    )
    v_ben = Variante(
        gen_id=gen_gla.id,
        notacion="c.937G>T",
        clinvar_id="VCV000010765",
        clasificacion=ClasificacionVariante.BENIGNA,
    )
    v_vus = Variante(
        gen_id=gen_brca1.id,
        notacion="c.5123C>T",
        clinvar_id="VCV000559900",
        clasificacion=ClasificacionVariante.VUS,
    )
    session.add_all([v_pat, v_ben, v_vus])
    session.commit()

    return {
        "u_bio": u_bio,
        "u_medico": u_medico,
        "u_medico_otro": u_medico_otro,
        "u_paciente": u_paciente,
        "u_paciente_otro": u_paciente_otro,
        "u_admin": u_admin,
        "medico": medico,
        "paciente": paciente,
        "patologia": patologia,
        "gen_gla": gen_gla,
        "gen_brca1": gen_brca1,
        "estudio": estudio,
        "analisis": analisis,
        "v_pat": v_pat,
        "v_ben": v_ben,
        "v_vus": v_vus,
        "tmp_path": tmp_path,
    }


def _cargar_resultado(app, client, datos, variantes_ids: list[int]):
    return client.post(
        f"/api/bioinformatica/estudios/{datos['estudio'].id}/analisis",
        headers=_headers_para(app, datos["u_bio"]),
        json={"variantes_ids": variantes_ids},
    )


def test_tc01_notificacion_avisos_app_y_mail_al_cargar_resultado(
    app, client, session, datos_escenario_37, monkeypatch
):
    """TC-01: Al pasar a RESULTADO_CARGADO crea avisos APP y MAIL para paciente y medico."""
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "mail-37-1", "estado": "enviado"}
    app.config["EMAIL_CLIENT"] = mock_email

    resp = _cargar_resultado(app, client, datos_escenario_37, [datos_escenario_37["v_pat"].id])
    assert resp.status_code == 200

    for usuario in (datos_escenario_37["u_paciente"], datos_escenario_37["u_medico"]):
        avisos = session.scalars(select(Aviso).where(Aviso.usuario_id == usuario.id)).all()
        assert {a.canal for a in avisos} == {CanalAviso.APP, CanalAviso.MAIL}
        assert all(a.enviado is True and a.enviado_en is not None for a in avisos)
        assert all(a.leido is False for a in avisos)

    # Error transitorio SMTP no revierte RESULTADO_CARGADO y preserva APP enviado
    monkeypatch.setattr(resultado_service.time, "sleep", lambda _s: None)
    mock_email.enviar_aviso.side_effect = ClienteServicioError("SMTP caido", codigo_http=503)
    estudio_2 = Estudio(
        paciente_id=datos_escenario_37["paciente"].id,
        medico_id=datos_escenario_37["medico"].id,
        patologia_sospechada_id=datos_escenario_37["patologia"].id,
        estado=EstadoEstudio.EN_ANALISIS_BIOINFORMATICO,
    )
    session.add(estudio_2)
    session.flush()
    analisis_2 = Analisis(
        estudio_id=estudio_2.id,
        tipo=TipoAnalisis.INICIAL,
        bioinformatico_id=datos_escenario_37["u_bio"].id,
    )
    session.add(analisis_2)
    session.flush()
    session.add(AnalisisGen(analisis_id=analisis_2.id, gen_id=datos_escenario_37["gen_gla"].id))
    session.commit()

    r2 = client.post(
        f"/api/bioinformatica/estudios/{estudio_2.id}/analisis",
        headers=_headers_para(app, datos_escenario_37["u_bio"]),
        json={"variantes_ids": [datos_escenario_37["v_ben"].id]},
    )
    assert r2.status_code == 200
    session.refresh(estudio_2)
    assert estudio_2.estado == EstadoEstudio.RESULTADO_CARGADO
    avisos_e2_mail = session.scalars(
        select(Aviso).where(
            Aviso.canal == CanalAviso.MAIL,
            Aviso.mensaje.contains(f"estudio #{estudio_2.id} "),
        )
    ).all()
    assert len(avisos_e2_mail) == 2
    assert all(a.enviado is False for a in avisos_e2_mail)


def test_tc02_paciente_consulta_resultado_marca_avisos_leidos_y_descarga_pdf(
    app, client, session, datos_escenario_37, caplog
):
    """TC-02: Paciente consulta JSON completo, marca solo sus avisos de ese estudio y descarga PDF."""
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "mail-37-2", "estado": "enviado"}
    app.config["EMAIL_CLIENT"] = mock_email

    assert _cargar_resultado(
        app,
        client,
        datos_escenario_37,
        [datos_escenario_37["v_pat"].id, datos_escenario_37["v_ben"].id],
    ).status_code == 200

    estudio = datos_escenario_37["estudio"]
    # Aviso de otro estudio cuyo id comparte prefijo (#1 vs #10) NO debe marcarse leido
    estudio_id_prefijo = int(f"{estudio.id}0")
    aviso_otro_estudio = Aviso(
        usuario_id=datos_escenario_37["u_paciente"].id,
        mensaje=f"El resultado del estudio #{estudio_id_prefijo} ya esta disponible (diagnostico: negativo).",
        canal=CanalAviso.APP,
        enviado=True,
        leido=False,
    )
    session.add(aviso_otro_estudio)
    session.commit()

    headers_pac = _headers_para(app, datos_escenario_37["u_paciente"])

    # Antes de abrir el resultado: campana muestra 2 avisos APP no leidos
    r_avisos_antes = client.get("/api/avisos?solo_no_leidos=true", headers=headers_pac)
    assert r_avisos_antes.status_code == 200
    assert r_avisos_antes.get_json()["no_leidos"] == 2

    with caplog.at_level(logging.INFO):
        r_json = client.get(f"/api/estudios/{estudio.id}/resultado", headers=headers_pac)

    assert r_json.status_code == 200
    assert r_json.headers.get("Cache-Control") == "private, no-store"
    assert r_json.headers.get("X-Content-Type-Options") == "nosniff"
    body = r_json.get_json()
    assert body["ok"] is True
    assert body["estudio_id"] == estudio.id
    assert body["estado_estudio"] == EstadoEstudio.RESULTADO_CARGADO.value
    assert body["patologia_sospechada"] == {
        "id": datos_escenario_37["patologia"].id,
        "nombre": "Fabry",
    }

    actual = body["resultado_actual"]
    assert actual["positivo"] is True
    assert actual["diagnostico"] == ConclusionDiagnostica.POSITIVO.value
    assert actual["fecha_proximo_estudio"] is None
    assert actual["pdf_url"] == f"/api/estudios/{estudio.id}/resultado/pdf"
    assert len(actual["variantes"]) == 2
    assert actual["variantes"][0]["notacion"] == "c.644A>G"
    assert actual["variantes"][0]["gen"] == {
        "id": datos_escenario_37["gen_gla"].id,
        "simbolo": "GLA",
        "nombre": "Galactosidasa alfa",
        "es_hallazgo_secundario": False,
    }
    assert f"step=2_consulta_resultado estudio_id={estudio.id}" in caplog.text
    assert "positivo=True" in caplog.text

    # Los avisos del paciente para este estudio quedaron leidos; el del estudio prefijo y los del medico siguen sin leer
    avisos_pac_estudio = session.scalars(
        select(Aviso).where(
            Aviso.usuario_id == datos_escenario_37["u_paciente"].id,
            Aviso.mensaje.contains(f"estudio #{estudio.id} "),
        )
    ).all()
    assert len(avisos_pac_estudio) == 2
    assert all(a.leido is True for a in avisos_pac_estudio)

    session.refresh(aviso_otro_estudio)
    assert aviso_otro_estudio.leido is False

    avisos_medico = session.scalars(
        select(Aviso).where(Aviso.usuario_id == datos_escenario_37["u_medico"].id)
    ).all()
    assert len(avisos_medico) == 2
    assert all(a.leido is False for a in avisos_medico)

    # Campana del paciente ahora tiene solo 1 no leido (el del otro estudio)
    r_avisos_despues = client.get("/api/avisos", headers=headers_pac)
    assert r_avisos_despues.status_code == 200
    assert r_avisos_despues.get_json()["no_leidos"] == 1

    # Descargar PDF 2 veces seguidas -> 200 OK y estudio permanece en RESULTADO_CARGADO
    for _ in range(2):
        r_pdf = client.get(f"/api/estudios/{estudio.id}/resultado/pdf", headers=headers_pac)
        assert r_pdf.status_code == 200
        assert r_pdf.mimetype == "application/pdf"
        assert r_pdf.headers.get("Content-Disposition") == (
            f'attachment; filename="resultado_estudio_{estudio.id}.pdf"'
        )
        assert r_pdf.headers.get("Cache-Control") == "private, no-store"
        assert r_pdf.headers.get("X-Content-Type-Options") == "nosniff"
        assert r_pdf.data.startswith(b"%PDF-")
        texto = _extraer_texto_pdf(r_pdf.data)
        assert "POSITIVO" in texto
        assert "c.644A>G" in texto
        assert "GLA" in texto

    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.RESULTADO_CARGADO


def test_tc03_medico_tratante_consulta_marca_sus_avisos_y_descarga_pdf(
    app, client, session, datos_escenario_37
):
    """TC-03: Medico tratante consulta detalle, marca sus avisos como leidos y descarga PDF."""
    assert _cargar_resultado(
        app, client, datos_escenario_37, [datos_escenario_37["v_pat"].id]
    ).status_code == 200
    estudio_id = datos_escenario_37["estudio"].id
    headers_med = _headers_para(app, datos_escenario_37["u_medico"])

    r_json = client.get(f"/api/estudios/{estudio_id}/resultado", headers=headers_med)
    assert r_json.status_code == 200
    assert r_json.get_json()["resultado_actual"]["positivo"] is True

    avisos_med = session.scalars(
        select(Aviso).where(Aviso.usuario_id == datos_escenario_37["u_medico"].id)
    ).all()
    assert all(a.leido is True for a in avisos_med)

    # Avisos del paciente no fueron tocados por la lectura del medico
    avisos_pac = session.scalars(
        select(Aviso).where(Aviso.usuario_id == datos_escenario_37["u_paciente"].id)
    ).all()
    assert all(a.leido is False for a in avisos_pac)

    r_pdf = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers_med)
    assert r_pdf.status_code == 200
    assert r_pdf.mimetype == "application/pdf"
    assert r_pdf.data.startswith(b"%PDF-")


def test_tc04_resultado_vus_expone_diagnostico_y_fecha_un_anio_en_json_y_pdf(
    app, client, datos_escenario_37, monkeypatch
):
    """TC-04: Variante VUS sin PATOGENICA -> positivo=False, diagnostico='vus', fecha +1 anio en JSON y PDF."""
    monkeypatch.setattr(
        resultado_service,
        "ahora_utc_naive",
        lambda: datetime(2026, 11, 21, 14, 0, 0),
    )
    assert _cargar_resultado(
        app,
        client,
        datos_escenario_37,
        [datos_escenario_37["v_vus"].id, datos_escenario_37["v_ben"].id],
    ).status_code == 200

    estudio_id = datos_escenario_37["estudio"].id
    headers_pac = _headers_para(app, datos_escenario_37["u_paciente"])

    r_json = client.get(f"/api/estudios/{estudio_id}/resultado", headers=headers_pac)
    assert r_json.status_code == 200
    body = r_json.get_json()
    assert body["fecha_reevaluacion_vus"] == "2027-11-21"
    actual = body["resultado_actual"]
    assert actual["positivo"] is False
    assert actual["diagnostico"] == ConclusionDiagnostica.VUS.value
    assert actual["fecha_proximo_estudio"] == "2027-11-21"
    variante_vus = next(v for v in actual["variantes"] if v["notacion"] == "c.5123C>T")
    assert variante_vus["gen"]["es_hallazgo_secundario"] is True

    r_pdf = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers_pac)
    assert r_pdf.status_code == 200
    texto_pdf = _extraer_texto_pdf(r_pdf.data)
    assert "VUS" in texto_pdf
    assert "2027-11-21" in texto_pdf


def test_tc05_rechazo_403_otro_paciente_no_filtra_ni_altera_avisos(
    app, client, session, datos_escenario_37, caplog
):
    """TC-05: Otro paciente recibe 403 en JSON y PDF sin alterar los avisos del titular."""
    assert _cargar_resultado(
        app, client, datos_escenario_37, [datos_escenario_37["v_pat"].id]
    ).status_code == 200
    estudio_id = datos_escenario_37["estudio"].id
    headers_otro = _headers_para(app, datos_escenario_37["u_paciente_otro"])

    with caplog.at_level(logging.WARNING):
        for ruta in (
            f"/api/estudios/{estudio_id}/resultado",
            f"/api/estudios/{estudio_id}/resultado/pdf",
        ):
            r = client.get(ruta, headers=headers_otro)
            assert r.status_code == 403
            assert r.get_json()["ok"] is False

    assert "acceso_denegado_resultado" in caplog.text
    avisos_titular = session.scalars(
        select(Aviso).where(Aviso.usuario_id == datos_escenario_37["u_paciente"].id)
    ).all()
    assert all(a.leido is False for a in avisos_titular)


def test_tc06_rechazo_403_otro_medico_y_roles_no_autorizados(app, client, datos_escenario_37):
    """TC-06: Medico no tratante y administrativo reciben 403 en JSON y PDF."""
    assert _cargar_resultado(
        app, client, datos_escenario_37, [datos_escenario_37["v_pat"].id]
    ).status_code == 200
    estudio_id = datos_escenario_37["estudio"].id

    for usuario in (datos_escenario_37["u_medico_otro"], datos_escenario_37["u_admin"]):
        headers = _headers_para(app, usuario)
        for ruta in (
            f"/api/estudios/{estudio_id}/resultado",
            f"/api/estudios/{estudio_id}/resultado/pdf",
        ):
            r = client.get(ruta, headers=headers)
            assert r.status_code == 403
            assert r.get_json()["ok"] is False


def test_tc07_rechazo_409_estudio_sin_resultado_404_y_401(app, client, session, datos_escenario_37):
    """TC-07: Estudio en EN_ANALISIS_BIOINFORMATICO o EN_VIAJE_COREA -> 409; inexistente -> 404; sin sesion -> 401."""
    estudio = datos_escenario_37["estudio"]
    headers_pac = _headers_para(app, datos_escenario_37["u_paciente"])

    assert client.get(f"/api/estudios/{estudio.id}/resultado").status_code == 401
    assert client.get(f"/api/estudios/{estudio.id}/resultado/pdf").status_code == 401

    for estado in (EstadoEstudio.EN_ANALISIS_BIOINFORMATICO, EstadoEstudio.EN_VIAJE_COREA):
        estudio.estado = estado
        session.commit()
        for ruta in (
            f"/api/estudios/{estudio.id}/resultado",
            f"/api/estudios/{estudio.id}/resultado/pdf",
        ):
            r = client.get(ruta, headers=headers_pac)
            assert r.status_code == 409
            assert r.get_json()["code"] == "RESULTADO_AUN_NO_DISPONIBLE"

    assert client.get("/api/estudios/999999/resultado", headers=headers_pac).status_code == 404


def test_step3_regeneracion_pdf_abort_cleanup_log_error_y_path_traversal(
    app, client, session, datos_escenario_37, monkeypatch, caplog
):
    """STEP 3 + ABORT_CLEANUP: regenera PDF si falta, loguea ERROR y borra .tmp si falla, frena traversal."""
    carga = _cargar_resultado(app, client, datos_escenario_37, [datos_escenario_37["v_pat"].id])
    assert carga.status_code == 200
    estudio_id = datos_escenario_37["estudio"].id
    resultado_id = carga.get_json()["resultado"]["id"]
    pdf_fisico = (
        datos_escenario_37["tmp_path"]
        / "resultados"
        / f"resultado_analisis_{datos_escenario_37['analisis'].id}.pdf"
    )
    headers_pac = _headers_para(app, datos_escenario_37["u_paciente"])

    # Faltante en disco -> regenera deterministicamente
    pdf_fisico.unlink()
    r_regen = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers_pac)
    assert r_regen.status_code == 200
    assert r_regen.data.startswith(b"%PDF-")
    assert pdf_fisico.is_file()

    # Faltante + fallo de regeneracion -> ABORT_CLEANUP sin .tmp y log ERROR con estudio_id/resultado_id/path
    pdf_fisico.unlink()
    monkeypatch.setattr(FPDF, "output", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("EIO")))
    with caplog.at_level(logging.ERROR):
        r_err = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers_pac)
    monkeypatch.undo()
    assert r_err.status_code == 500
    assert r_err.get_json()["retryable"] is True
    assert not list((datos_escenario_37["tmp_path"] / "resultados").glob("*.tmp"))
    assert "abort_cleanup_pdf" in caplog.text
    assert f"estudio_id={estudio_id}" in caplog.text
    assert f"resultado_id={resultado_id}" in caplog.text

    # Path traversal en BD -> 400 RUTA_ARCHIVO_INVALIDA
    res_bd = session.get(Resultado, resultado_id)
    assert res_bd is not None
    res_bd.pdf_path = "../../etc/passwd"
    session.commit()
    r_trav = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers_pac)
    assert r_trav.status_code == 400
    assert r_trav.get_json()["code"] == "RUTA_ARCHIVO_INVALIDA"


def test_avisos_endpoint_aislamiento_filtros_y_seguridad(app, client, session, datos_escenario_37):
    """GET /api/avisos aila por usuario, filtra APP/solo_no_leidos/limite y valida auth/query."""
    assert client.get("/api/avisos").status_code == 401

    assert _cargar_resultado(
        app, client, datos_escenario_37, [datos_escenario_37["v_pat"].id]
    ).status_code == 200
    estudio_id = datos_escenario_37["estudio"].id

    headers_pac = _headers_para(app, datos_escenario_37["u_paciente"])
    r = client.get("/api/avisos", headers=headers_pac)
    assert r.status_code == 200
    assert r.headers.get("Cache-Control") == "private, no-store"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    body = r.get_json()
    assert body["ok"] is True
    assert body["no_leidos"] == 1
    assert len(body["avisos"]) == 1
    assert body["avisos"][0]["canal"] == CanalAviso.APP.value
    assert body["avisos"][0]["leido"] is False
    assert body["avisos"][0]["estudio_id"] == estudio_id

    # Otro paciente no ve avisos ajenos
    r_otro = client.get("/api/avisos", headers=_headers_para(app, datos_escenario_37["u_paciente_otro"]))
    assert r_otro.status_code == 200
    assert r_otro.get_json()["no_leidos"] == 0
    assert r_otro.get_json()["avisos"] == []

    # Parametros invalidos -> 400 DATOS_INVALIDOS
    for qs in ("solo_no_leidos=talvez", "limite=0", "limite=101", "limite=abc"):
        r_bad = client.get(f"/api/avisos?{qs}", headers=headers_pac)
        assert r_bad.status_code == 400
        assert r_bad.get_json()["code"] == "DATOS_INVALIDOS"

    # Usuario con debe_cambiar_password=True -> 403
    datos_escenario_37["u_paciente"].debe_cambiar_password = True
    session.commit()
    r_pwd = client.get("/api/avisos", headers=headers_pac)
    assert r_pwd.status_code == 403
    assert r_pwd.get_json()["code"] == "DEBE_CAMBIAR_PASSWORD_INICIAL"


def test_error_bd_al_marcar_avisos_leidos_no_bloquea_consulta_resultado(
    app, client, datos_escenario_37, monkeypatch, caplog
):
    """Un fallo puntual al actualizar Aviso.leido no debe impedir consultar el resultado clinico."""
    assert _cargar_resultado(
        app, client, datos_escenario_37, [datos_escenario_37["v_pat"].id]
    ).status_code == 200
    estudio_id = datos_escenario_37["estudio"].id

    def _fallar_avisos(_uid, _eid):
        raise OperationalError("UPDATE avisos", {}, Exception("lock timeout"))

    monkeypatch.setattr(bioinformatica_repo, "marcar_avisos_estudio_leidos", _fallar_avisos)
    with caplog.at_level(logging.WARNING):
        r = client.get(
            f"/api/estudios/{estudio_id}/resultado",
            headers=_headers_para(app, datos_escenario_37["u_paciente"]),
        )
    assert r.status_code == 200
    assert r.get_json()["resultado_actual"]["positivo"] is True
    assert "error_marcar_avisos_leidos" in caplog.text
