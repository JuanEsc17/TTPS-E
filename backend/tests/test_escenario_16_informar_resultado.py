"""Tests de aceptacion y seguridad API para Escenario 16: Informar el resultado de un estudio."""
from __future__ import annotations

import logging
import re
import zlib
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.clients import EmailClient
from src.clients.exceptions import ClienteServicioError
from src.core.models import (
    Analisis,
    AnalisisGen,
    AnalisisVariante,
    Aviso,
    CanalAviso,
    ClasificacionVariante,
    ConclusionDiagnostica,
    DatosCrudos,
    EntidadAuditable,
    EstadoEstudio,
    Estudio,
    EstudioGen,
    Gen,
    Medico,
    OrigenGen,
    Paciente,
    Patologia,
    RegistroModificacion,
    Resultado,
    Rol,
    TipoAccionAuditoria,
    TipoAnalisis,
    Usuario,
    Variante,
    sumar_un_anio,
)
from src.core.repos import bioinformatica_repo
from src.core.services import resultado_service
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    SCOPE_VERIFICAR_DISPOSITIVO,
    decodificar_token,
    emitir_token,
    hashear_password,
    tokens_revocados,
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


def _token_para(app, usuario: Usuario, *, scope: str = SCOPE_ACCESO_COMPLETO) -> str:
    return emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=scope,
        ttl_segundos=3600,
    )


def _headers_para(app, usuario: Usuario, *, scope: str = SCOPE_ACCESO_COMPLETO) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token_para(app, usuario, scope=scope)}"}


@pytest.fixture
def datos_escenario_16(app, session, tmp_path):
    """Prepara estudio en estado En analisis de un bioinformatico con actores y variantes."""
    app.config["STORAGE_DIR"] = str(tmp_path)

    u_bio = Usuario(
        email="bio.e16@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.BIOINFORMATICO,
        nombre="Ariadna",
        apellido="Guarino",
        telefono="1144001001",
    )
    u_medico = Usuario(
        email="medico.e16@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.MEDICO,
        nombre="Juan",
        apellido="Escudero",
        telefono="1144001002",
    )
    u_medico_otro = Usuario(
        email="medico.otro.e16@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.MEDICO,
        nombre="Clara",
        apellido="Mendez",
        telefono="1144001003",
    )
    u_gerente = Usuario(
        email="gerente.e16@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.GERENTE_MEDICO,
        nombre="Elena",
        apellido="Vidal",
        telefono="1144001004",
    )
    u_paciente = Usuario(
        email="paciente.e16@gmail.com",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.PACIENTE,
        nombre="Sofia",
        apellido="Perez",
        telefono="1144001005",
    )
    u_paciente_otro = Usuario(
        email="paciente.otro.e16@gmail.com",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.PACIENTE,
        nombre="Lucas",
        apellido="Gomez",
        telefono="1144001006",
    )
    u_admin = Usuario(
        email="admin.e16@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.ADMINISTRATIVO,
        nombre="Laura",
        apellido="Diaz",
        telefono="1144001007",
    )
    u_transportista = Usuario(
        email="transp.e16@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.TRANSPORTISTA,
        nombre="Diego",
        apellido="Ruiz",
        telefono="1144001008",
    )
    u_admin_general = Usuario(
        email="admingen.e16@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.ADMIN_GENERAL,
        nombre="Marta",
        apellido="Sosa",
        telefono="1144001009",
    )
    session.add_all(
        [
            u_bio,
            u_medico,
            u_medico_otro,
            u_gerente,
            u_paciente,
            u_paciente_otro,
            u_admin,
            u_transportista,
            u_admin_general,
        ]
    )
    session.flush()

    patologia = Patologia(nombre="Enfermedad de Pompe", descripcion="Glucogenosis tipo II")
    gen_gaa = Gen(simbolo="GAA", nombre="Alpha glucosidase", es_hallazgo_secundario=False)
    gen_brca1 = Gen(simbolo="BRCA1", nombre="BRCA1 DNA repair", es_hallazgo_secundario=True)
    session.add_all([patologia, gen_gaa, gen_brca1])
    session.flush()

    medico = Medico(usuario_id=u_medico.id, matricula="MN-16001")
    medico_otro = Medico(usuario_id=u_medico_otro.id, matricula="MN-16002")
    gerente_medico = Medico(usuario_id=u_gerente.id, matricula="MN-16003")
    session.add_all([medico, medico_otro, gerente_medico])
    session.flush()

    paciente = Paciente(
        usuario_id=u_paciente.id,
        medico_id=medico.id,
        dni="40161616",
        fecha_nacimiento=date(1995, 4, 12),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="Sospecha de enfermedad de Pompe",
        tipo_sospecha="clinica",
    )
    paciente_otro = Paciente(
        usuario_id=u_paciente_otro.id,
        medico_id=medico_otro.id,
        dni="40999999",
        fecha_nacimiento=date(1990, 1, 5),
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
            EstudioGen(estudio_id=estudio.id, gen_id=gen_gaa.id, origen=OrigenGen.PATOLOGIA),
            EstudioGen(
                estudio_id=estudio.id,
                gen_id=gen_brca1.id,
                origen=OrigenGen.HALLAZGO_SECUNDARIO,
            ),
        ]
    )

    dc_rel = f"storage/datos_crudos/estudio_{estudio.id}.txt"
    dc_fisico = tmp_path / "datos_crudos" / f"estudio_{estudio.id}.txt"
    dc_fisico.parent.mkdir(parents=True, exist_ok=True)
    dc_fisico.write_text("ATCGGCTAGCTA\n", encoding="utf-8")
    session.add(
        DatosCrudos(
            estudio_id=estudio.id,
            cargado_por_id=u_admin.id,
            archivo_path=dc_rel,
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
            AnalisisGen(analisis_id=analisis.id, gen_id=gen_gaa.id),
            AnalisisGen(analisis_id=analisis.id, gen_id=gen_brca1.id),
        ]
    )

    v_pat = Variante(
        gen_id=gen_gaa.id,
        notacion="c.1935C>A",
        clinvar_id="VCV000004025",
        clasificacion=ClasificacionVariante.PATOGENICA,
    )
    v_vus = Variante(
        gen_id=gen_gaa.id,
        notacion="c.1194+5G>A",
        clinvar_id="VCV000551203",
        clasificacion=ClasificacionVariante.VUS,
    )
    v_ben = Variante(
        gen_id=gen_gaa.id,
        notacion="c.2065G>A",
        clinvar_id="VCV000092611",
        clasificacion=ClasificacionVariante.BENIGNA,
    )
    v_ino = Variante(
        gen_id=gen_brca1.id,
        notacion="c.4837A>G",
        clinvar_id="VCV000055298",
        clasificacion=ClasificacionVariante.INOCUA,
    )
    session.add_all([v_pat, v_vus, v_ben, v_ino])
    session.commit()

    return {
        "u_bio": u_bio,
        "u_medico": u_medico,
        "u_medico_otro": u_medico_otro,
        "u_gerente": u_gerente,
        "u_paciente": u_paciente,
        "u_paciente_otro": u_paciente_otro,
        "u_admin": u_admin,
        "u_transportista": u_transportista,
        "u_admin_general": u_admin_general,
        "medico": medico,
        "medico_otro": medico_otro,
        "gerente_medico": gerente_medico,
        "paciente": paciente,
        "paciente_otro": paciente_otro,
        "patologia": patologia,
        "gen_gaa": gen_gaa,
        "gen_brca1": gen_brca1,
        "estudio": estudio,
        "analisis": analisis,
        "v_pat": v_pat,
        "v_vus": v_vus,
        "v_ben": v_ben,
        "v_ino": v_ino,
        "tmp_path": tmp_path,
    }


def _cargar_resultado_http(app, client, datos, variantes_ids: list[int]):
    return client.post(
        f"/api/bioinformatica/estudios/{datos['estudio'].id}/analisis",
        headers=_headers_para(app, datos["u_bio"]),
        json={"variantes_ids": variantes_ids},
    )


def test_tc01_resultado_positivo_genera_pdf_auditoria_y_avisos(
    app, client, session, datos_escenario_16
):
    """TC-01: >=1 variante PATOGENICA + VUS -> positivo=True, PDF completo, auditoria y avisos."""
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "mail-16-1", "estado": "pendiente"}
    app.config["EMAIL_CLIENT"] = mock_email

    resp = _cargar_resultado_http(
        app,
        client,
        datos_escenario_16,
        [datos_escenario_16["v_pat"].id, datos_escenario_16["v_vus"].id],
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["estado_estudio"] == EstadoEstudio.RESULTADO_CARGADO.value
    assert body["resultado"]["positivo"] is True
    assert body["resultado"]["diagnostico"] == ConclusionDiagnostica.POSITIVO.value
    assert body["resultado"]["fecha_proximo_estudio"] is None

    estudio = datos_escenario_16["estudio"]
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.RESULTADO_CARGADO
    assert estudio.fecha_reevaluacion_vus is None

    res_bd = session.get(Resultado, body["resultado"]["id"])
    assert res_bd is not None
    assert res_bd.positivo is True
    assert res_bd.diagnostico == ConclusionDiagnostica.POSITIVO
    assert res_bd.fecha_proximo_estudio is None

    pdf_fisico = (
        datos_escenario_16["tmp_path"]
        / "resultados"
        / f"resultado_analisis_{datos_escenario_16['analisis'].id}.pdf"
    )
    assert pdf_fisico.is_file()
    pdf_bytes = pdf_fisico.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-")
    texto_pdf = _extraer_texto_pdf(pdf_bytes)
    assert "Sofia Perez" in texto_pdf
    assert "40161616" in texto_pdf
    assert "Juan Escudero" in texto_pdf
    assert "MN-16001" in texto_pdf
    assert "Enfermedad de Pompe" in texto_pdf
    assert "GAA (Alpha glucosidase)" in texto_pdf
    assert "POSITIVO" in texto_pdf
    assert "c.1935C>A" in texto_pdf
    assert "VCV000004025" in texto_pdf
    assert "c.1194+5G>A" in texto_pdf

    auditoria = session.scalar(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
            RegistroModificacion.entidad_id == estudio.id,
        )
    )
    assert auditoria is not None
    assert auditoria.accion == TipoAccionAuditoria.CAMBIO_ESTADO
    assert auditoria.usuario_id == datos_escenario_16["u_bio"].id
    assert auditoria.cambios["estado"]["nuevo"] == EstadoEstudio.RESULTADO_CARGADO.value
    assert auditoria.cambios["resultado_id"]["nuevo"] == res_bd.id
    assert auditoria.cambios["diagnostico"]["nuevo"] == "positivo"
    assert auditoria.cambios["fecha_reevaluacion_vus"]["nuevo"] is None


@pytest.mark.parametrize("usar_benigna_inocua", [True, False])
def test_tc02_resultado_negativo_sin_patogenica_ni_vus(
    app, client, session, datos_escenario_16, usar_benigna_inocua
):
    """TC-02: Solo BENIGNA/INOCUA o ninguna variante -> positivo=False, diagnostico=negativo."""
    variantes_ids = (
        [datos_escenario_16["v_ben"].id, datos_escenario_16["v_ino"].id]
        if usar_benigna_inocua
        else []
    )
    resp = _cargar_resultado_http(app, client, datos_escenario_16, variantes_ids)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["estado_estudio"] == EstadoEstudio.RESULTADO_CARGADO.value
    assert body["resultado"]["positivo"] is False
    assert body["resultado"]["diagnostico"] == ConclusionDiagnostica.NEGATIVO.value
    assert body["resultado"]["fecha_proximo_estudio"] is None

    estudio = datos_escenario_16["estudio"]
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.RESULTADO_CARGADO
    assert estudio.fecha_reevaluacion_vus is None

    pdf_fisico = (
        datos_escenario_16["tmp_path"]
        / "resultados"
        / f"resultado_analisis_{datos_escenario_16['analisis'].id}.pdf"
    )
    texto_pdf = _extraer_texto_pdf(pdf_fisico.read_bytes())
    assert "NEGATIVO" in texto_pdf
    if usar_benigna_inocua:
        assert "c.2065G>A" in texto_pdf
        assert "c.4837A>G" in texto_pdf
    else:
        assert "No se detectaron variantes" in texto_pdf


def test_tc02b_resultado_vus_calcula_fecha_un_anio_pdf_auditoria_y_avisos(
    app, client, session, datos_escenario_16, monkeypatch
):
    """TC-02b: >=1 VUS y 0 PATOGENICA -> diagnostico=vus, fecha +1 anio en BD, PDF, auditoria y avisos."""
    fecha_fija = datetime(2026, 11, 18, 15, 30, 0)
    monkeypatch.setattr(resultado_service, "ahora_utc_naive", lambda: fecha_fija)
    assert sumar_un_anio(date(2024, 2, 29)) == date(2025, 2, 28)

    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "mail-vus-1", "estado": "pendiente"}
    app.config["EMAIL_CLIENT"] = mock_email

    resp = _cargar_resultado_http(
        app,
        client,
        datos_escenario_16,
        [datos_escenario_16["v_vus"].id, datos_escenario_16["v_ben"].id],
    )
    assert resp.status_code == 200
    body = resp.get_json()
    esperada = "2027-11-18"
    assert body["resultado"]["positivo"] is False
    assert body["resultado"]["diagnostico"] == ConclusionDiagnostica.VUS.value
    assert body["resultado"]["fecha_proximo_estudio"] == esperada

    estudio = datos_escenario_16["estudio"]
    session.refresh(estudio)
    assert estudio.fecha_reevaluacion_vus == date(2027, 11, 18)

    pdf_fisico = (
        datos_escenario_16["tmp_path"]
        / "resultados"
        / f"resultado_analisis_{datos_escenario_16['analisis'].id}.pdf"
    )
    texto_pdf = _extraer_texto_pdf(pdf_fisico.read_bytes())
    assert "VUS (Variante de Significado Incierto)" in texto_pdf
    assert "Recomendacion de nuevo estudio / reevaluacion VUS" in texto_pdf
    assert esperada in texto_pdf

    auditoria = session.scalar(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
            RegistroModificacion.entidad_id == estudio.id,
        )
    )
    assert auditoria is not None
    assert auditoria.cambios["diagnostico"]["nuevo"] == "vus"
    assert auditoria.cambios["fecha_reevaluacion_vus"]["nuevo"] == esperada

    avisos = session.scalars(select(Aviso)).all()
    assert len(avisos) == 4
    assert all(esperada in a.mensaje for a in avisos)
    kwargs_mail = mock_email.enviar_aviso.call_args.kwargs
    assert esperada in kwargs_mail["mensaje"]


def test_tc03_notificacion_dual_paciente_y_medico(app, client, session, datos_escenario_16):
    """TC-03: Crea avisos APP y MAIL para Paciente y Medico tratante y despacha correos."""
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "mail-dual-1", "estado": "pendiente"}
    app.config["EMAIL_CLIENT"] = mock_email

    resp = _cargar_resultado_http(app, client, datos_escenario_16, [datos_escenario_16["v_pat"].id])
    assert resp.status_code == 200
    res_id = resp.get_json()["resultado"]["id"]

    mock_email.enviar_aviso.assert_called_once()
    kwargs = mock_email.enviar_aviso.call_args.kwargs
    assert set(kwargs["destinatarios"]) == {
        datos_escenario_16["u_paciente"].email,
        datos_escenario_16["u_medico"].email,
    }
    assert kwargs["referencia"] == f"RESULTADO-{res_id}"
    assert kwargs["idempotency_key"] == f"resultado-{res_id}-aviso"

    avisos_pac = session.scalars(
        select(Aviso).where(Aviso.usuario_id == datos_escenario_16["u_paciente"].id)
    ).all()
    avisos_med = session.scalars(
        select(Aviso).where(Aviso.usuario_id == datos_escenario_16["u_medico"].id)
    ).all()
    assert {a.canal for a in avisos_pac} == {CanalAviso.APP, CanalAviso.MAIL}
    assert {a.canal for a in avisos_med} == {CanalAviso.APP, CanalAviso.MAIL}
    assert all(a.enviado and a.enviado_en is not None for a in avisos_pac + avisos_med)


def test_tc03b_fallo_smtp_reintenta_con_backoff_y_no_revierte_resultado(
    app, client, session, datos_escenario_16, monkeypatch
):
    """STEP 3 FAILURE(smtp_error): 3 reintentos con backoff, no revierte resultado y deja MAIL enviado=False."""
    esperas: list[int] = []
    monkeypatch.setattr(resultado_service.time, "sleep", lambda s: esperas.append(s))

    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.side_effect = ClienteServicioError("SMTP 503", codigo_http=503)
    app.config["EMAIL_CLIENT"] = mock_email

    resp = _cargar_resultado_http(app, client, datos_escenario_16, [datos_escenario_16["v_pat"].id])
    assert resp.status_code == 200
    assert mock_email.enviar_aviso.call_count == 3
    assert esperas == [1, 2]

    estudio = datos_escenario_16["estudio"]
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.RESULTADO_CARGADO

    avisos_app = session.scalars(select(Aviso).where(Aviso.canal == CanalAviso.APP)).all()
    avisos_mail = session.scalars(select(Aviso).where(Aviso.canal == CanalAviso.MAIL)).all()
    assert len(avisos_app) == 2
    assert all(a.enviado is True for a in avisos_app)
    assert len(avisos_mail) == 2
    assert all(a.enviado is False and a.enviado_en is None for a in avisos_mail)


def test_tc04_consulta_json_y_descarga_pdf_paciente_titular(
    app, client, datos_escenario_16
):
    """TC-04: Paciente titular consulta JSON segun contrato y descarga PDF valido."""
    carga = _cargar_resultado_http(
        app,
        client,
        datos_escenario_16,
        [datos_escenario_16["v_pat"].id, datos_escenario_16["v_vus"].id],
    )
    assert carga.status_code == 200
    estudio_id = datos_escenario_16["estudio"].id
    headers_pac = _headers_para(app, datos_escenario_16["u_paciente"])

    resp_json = client.get(f"/api/estudios/{estudio_id}/resultado", headers=headers_pac)
    assert resp_json.status_code == 200
    assert resp_json.headers.get("Cache-Control") == "private, no-store"
    assert resp_json.headers.get("X-Content-Type-Options") == "nosniff"
    body = resp_json.get_json()
    assert body["ok"] is True
    assert body["estudio_id"] == estudio_id
    assert body["estado_estudio"] == EstadoEstudio.RESULTADO_CARGADO.value
    assert body["fecha_reevaluacion_vus"] is None

    actual = body["resultado_actual"]
    assert actual["resultado_id"] == carga.get_json()["resultado"]["id"]
    assert actual["analisis_id"] == datos_escenario_16["analisis"].id
    assert actual["tipo_analisis"] == TipoAnalisis.INICIAL.value
    assert actual["positivo"] is True
    assert actual["diagnostico"] == "positivo"
    assert actual["fecha_proximo_estudio"] is None
    assert actual["generado_en"] is not None
    assert actual["pdf_url"] == f"/api/estudios/{estudio_id}/resultado/pdf"
    assert len(actual["variantes"]) == 2
    assert actual["variantes"][0] == {
        "variante_id": datos_escenario_16["v_pat"].id,
        "gen_simbolo": "GAA",
        "gen": {
            "id": datos_escenario_16["gen_gaa"].id,
            "simbolo": "GAA",
            "nombre": "Alpha glucosidase",
            "es_hallazgo_secundario": False,
        },
        "notacion": "c.1935C>A",
        "clinvar_id": "VCV000004025",
        "clasificacion": "patogenica",
    }
    assert len(body["historial_resultados"]) == 1

    resp_pdf = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers_pac)
    assert resp_pdf.status_code == 200
    assert resp_pdf.mimetype == "application/pdf"
    assert resp_pdf.headers.get("Content-Disposition") == (
        f'attachment; filename="resultado_estudio_{estudio_id}.pdf"'
    )
    assert resp_pdf.headers.get("Cache-Control") == "private, no-store"
    assert resp_pdf.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp_pdf.data.startswith(b"%PDF-")
    assert "c.1935C>A" in _extraer_texto_pdf(resp_pdf.data)


def test_tc05_consulta_y_descarga_pdf_medico_tratante_y_bioinformatico(
    app, client, datos_escenario_16
):
    """TC-05: Medico tratante y Bioinformatico (auditoria tecnica) acceden a JSON y PDF."""
    assert _cargar_resultado_http(
        app, client, datos_escenario_16, [datos_escenario_16["v_pat"].id]
    ).status_code == 200
    estudio_id = datos_escenario_16["estudio"].id

    for usuario in (datos_escenario_16["u_medico"], datos_escenario_16["u_bio"]):
        headers = _headers_para(app, usuario)
        r_json = client.get(f"/api/estudios/{estudio_id}/resultado", headers=headers)
        assert r_json.status_code == 200
        assert r_json.get_json()["resultado_actual"]["positivo"] is True

        r_pdf = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers)
        assert r_pdf.status_code == 200
        assert r_pdf.mimetype == "application/pdf"
        assert r_pdf.data.startswith(b"%PDF-")


def test_reanalisis_historial_medico_solicitante_y_descarga_historica(
    app, client, session, datos_escenario_16
):
    """Soporta historial de reanalisis, acceso/notificacion al medico solicitante y bloqueo IDOR."""
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "mail-re-1", "estado": "pendiente"}
    app.config["EMAIL_CLIENT"] = mock_email

    # 1) Resultado inicial NEGATIVO
    r_inicial = _cargar_resultado_http(app, client, datos_escenario_16, [datos_escenario_16["v_ben"].id])
    assert r_inicial.status_code == 200
    analisis_inicial_id = datos_escenario_16["analisis"].id

    # 2) Simular reanalisis solicitado por gerente_medico (distinto del medico derivante)
    estudio = datos_escenario_16["estudio"]
    estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICO
    reanalisis = Analisis(
        estudio_id=estudio.id,
        tipo=TipoAnalisis.REANALISIS,
        bioinformatico_id=datos_escenario_16["u_bio"].id,
        solicitado_por_id=datos_escenario_16["gerente_medico"].id,
    )
    session.add(reanalisis)
    session.flush()
    session.add(AnalisisGen(analisis_id=reanalisis.id, gen_id=datos_escenario_16["gen_gaa"].id))
    session.commit()

    mock_email.enviar_aviso.reset_mock()
    r_reanalisis = _cargar_resultado_http(
        app, client, datos_escenario_16, [datos_escenario_16["v_pat"].id]
    )
    assert r_reanalisis.status_code == 200
    assert r_reanalisis.get_json()["tipo_analisis"] == TipoAnalisis.REANALISIS.value

    # El gerente medico solicitante del reanalisis tambien fue notificado
    destinatarios = set(mock_email.enviar_aviso.call_args.kwargs["destinatarios"])
    assert datos_escenario_16["u_gerente"].email in destinatarios

    # El gerente medico solicitante puede consultar y descargar ambos analisis del estudio
    headers_gerente = _headers_para(app, datos_escenario_16["u_gerente"])
    resp_json = client.get(f"/api/estudios/{estudio.id}/resultado", headers=headers_gerente)
    assert resp_json.status_code == 200
    body = resp_json.get_json()
    assert body["resultado_actual"]["analisis_id"] == reanalisis.id
    assert body["resultado_actual"]["positivo"] is True
    assert len(body["historial_resultados"]) == 2
    assert body["historial_resultados"][0]["analisis_id"] == analisis_inicial_id
    assert body["historial_resultados"][0]["positivo"] is False
    assert body["historial_resultados"][1]["analisis_id"] == reanalisis.id

    # Descarga por defecto = ultimo resultado (POSITIVO); descarga con ?analisis_id = inicial (NEGATIVO)
    pdf_ultimo = client.get(f"/api/estudios/{estudio.id}/resultado/pdf", headers=headers_gerente)
    assert pdf_ultimo.status_code == 200
    assert "POSITIVO" in _extraer_texto_pdf(pdf_ultimo.data)

    pdf_inicial = client.get(
        f"/api/estudios/{estudio.id}/resultado/pdf?analisis_id={analisis_inicial_id}",
        headers=headers_gerente,
    )
    assert pdf_inicial.status_code == 200
    assert "NEGATIVO" in _extraer_texto_pdf(pdf_inicial.data)

    # IDOR: analisis_id que no pertenece a este estudio -> 404
    pdf_ajeno = client.get(
        f"/api/estudios/{estudio.id}/resultado/pdf?analisis_id=999999",
        headers=headers_gerente,
    )
    assert pdf_ajeno.status_code == 404
    assert pdf_ajeno.get_json()["code"] == "RESULTADO_NO_ENCONTRADO"


def test_tc06_bloqueo_seguridad_terceros_y_roles_no_autorizados(
    app, client, datos_escenario_16, caplog
):
    """TC-06: Paciente ajeno, medico no vinculado y otros roles reciben 403 FORBIDDEN_RESULTADO_GENETICO."""
    assert _cargar_resultado_http(
        app, client, datos_escenario_16, [datos_escenario_16["v_pat"].id]
    ).status_code == 200
    estudio_id = datos_escenario_16["estudio"].id

    usuarios_bloqueados = [
        datos_escenario_16["u_paciente_otro"],
        datos_escenario_16["u_medico_otro"],
        datos_escenario_16["u_gerente"],
        datos_escenario_16["u_admin"],
        datos_escenario_16["u_transportista"],
        datos_escenario_16["u_admin_general"],
    ]

    with caplog.at_level(logging.WARNING):
        for usuario in usuarios_bloqueados:
            headers = _headers_para(app, usuario)
            for ruta in (
                f"/api/estudios/{estudio_id}/resultado",
                f"/api/estudios/{estudio_id}/resultado/pdf",
            ):
                resp = client.get(ruta, headers=headers)
                assert resp.status_code == 403, f"Fallo bloqueo para rol {usuario.rol.value} en {ruta}"
                data = resp.get_json()
                assert data["ok"] is False
                assert data["code"] == "FORBIDDEN_RESULTADO_GENETICO"
                assert data["retryable"] is False

    assert "acceso_denegado_resultado" in caplog.text

    # Roles no permitidos no pueden enumerar si un estudio existe o no
    r_enum = client.get(
        "/api/estudios/999999/resultado",
        headers=_headers_para(app, datos_escenario_16["u_admin"]),
    )
    assert r_enum.status_code == 403
    assert r_enum.get_json()["code"] == "FORBIDDEN_RESULTADO_GENETICO"


def test_seguridad_autenticacion_y_autorizacion_antes_de_estado(
    app, client, session, datos_escenario_16
):
    """Valida 401 sin token/revocado, 403 password inicial/scope y 403 antes de 409."""
    estudio_id = datos_escenario_16["estudio"].id

    # Sin token -> 401
    for ruta in (
        f"/api/estudios/{estudio_id}/resultado",
        f"/api/estudios/{estudio_id}/resultado/pdf",
    ):
        r_no_auth = client.get(ruta)
        assert r_no_auth.status_code == 401
        assert r_no_auth.get_json()["code"] == "NO_AUTENTICADO"

    # Token invalido -> 401
    r_bad = client.get(
        f"/api/estudios/{estudio_id}/resultado",
        headers={"Authorization": "Bearer token.invalido.aqui"},
    )
    assert r_bad.status_code == 401

    # Token revocado -> 401
    token_pac = _token_para(app, datos_escenario_16["u_paciente"])
    payload = decodificar_token(token_pac, str(app.config["SECRET_KEY"]))
    tokens_revocados.revocar(payload["jti"], payload["exp"])
    r_rev = client.get(
        f"/api/estudios/{estudio_id}/resultado",
        headers={"Authorization": f"Bearer {token_pac}"},
    )
    assert r_rev.status_code == 401
    assert r_rev.get_json()["code"] == "SESION_CERRADA_O_INVALIDA"

    # Scope restringido -> 403
    r_scope = client.get(
        f"/api/estudios/{estudio_id}/resultado",
        headers=_headers_para(app, datos_escenario_16["u_paciente"], scope=SCOPE_VERIFICAR_DISPOSITIVO),
    )
    assert r_scope.status_code == 403
    assert r_scope.get_json()["code"] == "DISPOSITIVO_NO_VERIFICADO"

    # Estudio aun SIN resultado: paciente ajeno debe recibir 403 (NO 409) para evitar oracle de estado
    r_oracle = client.get(
        f"/api/estudios/{estudio_id}/resultado",
        headers=_headers_para(app, datos_escenario_16["u_paciente_otro"]),
    )
    assert r_oracle.status_code == 403
    assert r_oracle.get_json()["code"] == "FORBIDDEN_RESULTADO_GENETICO"

    # Paciente titular con debe_cambiar_password=True -> 403
    u_pac = datos_escenario_16["u_paciente"]
    u_pac.debe_cambiar_password = True
    session.commit()
    r_pwd = client.get(
        f"/api/estudios/{estudio_id}/resultado",
        headers=_headers_para(app, u_pac),
    )
    assert r_pwd.status_code == 403
    assert r_pwd.get_json()["code"] == "DEBE_CAMBIAR_PASSWORD_INICIAL"


def test_step4_estado_invalido_409_estudio_404_y_validacion_query(
    app, client, datos_escenario_16
):
    """STEP 4 FAILURE(invalid_state/not_found) + validacion estricta de query params."""
    estudio_id = datos_escenario_16["estudio"].id
    headers_pac = _headers_para(app, datos_escenario_16["u_paciente"])

    # Estudio aun en EN_ANALISIS_BIOINFORMATICO -> 409
    for ruta in (
        f"/api/estudios/{estudio_id}/resultado",
        f"/api/estudios/{estudio_id}/resultado/pdf",
    ):
        resp = client.get(ruta, headers=headers_pac)
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "RESULTADO_AUN_NO_DISPONIBLE"

    # Estudio inexistente -> 404
    r_404 = client.get("/api/estudios/999999/resultado", headers=headers_pac)
    assert r_404.status_code == 404
    assert r_404.get_json()["code"] == "ESTUDIO_NO_ENCONTRADO"

    # Parametros maliciosos o invalidos en analisis_id -> 400 (nunca 500)
    for bad_param in ("abc", "0", "-1", "1' OR '1'='1"):
        r_bad = client.get(
            f"/api/estudios/{estudio_id}/resultado/pdf?analisis_id={bad_param}",
            headers=headers_pac,
        )
        assert r_bad.status_code == 400
        assert r_bad.get_json()["code"] == "DATOS_INVALIDOS"


def test_step4_regenera_pdf_al_vuelo_si_falta_en_disco_y_protege_path_traversal(
    app, client, session, datos_escenario_16, monkeypatch
):
    """STEP 4 FAILURE(file_missing): regenera PDF desde BD si falta y bloquea path traversal."""
    carga = _cargar_resultado_http(
        app, client, datos_escenario_16, [datos_escenario_16["v_pat"].id]
    )
    assert carga.status_code == 200
    estudio_id = datos_escenario_16["estudio"].id
    resultado_id = carga.get_json()["resultado"]["id"]
    pdf_fisico = (
        datos_escenario_16["tmp_path"]
        / "resultados"
        / f"resultado_analisis_{datos_escenario_16['analisis'].id}.pdf"
    )
    assert pdf_fisico.is_file()
    pdf_fisico.unlink()
    assert not pdf_fisico.exists()

    headers_pac = _headers_para(app, datos_escenario_16["u_paciente"])
    resp_regen = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers_pac)
    assert resp_regen.status_code == 200
    assert resp_regen.data.startswith(b"%PDF-")
    assert "c.1935C>A" in _extraer_texto_pdf(resp_regen.data)
    assert pdf_fisico.is_file()
    assert not list((datos_escenario_16["tmp_path"] / "resultados").glob("*.tmp"))

    # Si falta en disco Y falla regeneracion -> 500 retryable sin .tmp huerfano
    pdf_fisico.unlink()

    def _fallar_output(self, *_args, **_kwargs):
        raise OSError("Disco lleno simulado")

    monkeypatch.setattr(FPDF, "output", _fallar_output)
    resp_500 = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers_pac)
    monkeypatch.undo()
    assert resp_500.status_code == 500
    assert resp_500.get_json()["code"] == "ERROR_GENERACION_PDF_RESULTADO"
    assert resp_500.get_json()["retryable"] is True
    assert not list((datos_escenario_16["tmp_path"] / "resultados").glob("*.tmp"))

    # Path traversal en BD bloqueado con 400 RUTA_ARCHIVO_INVALIDA
    res_bd = session.get(Resultado, resultado_id)
    assert res_bd is not None
    res_bd.pdf_path = "../../etc/passwd"
    session.commit()
    resp_trav = client.get(f"/api/estudios/{estudio_id}/resultado/pdf", headers=headers_pac)
    assert resp_trav.status_code == 400
    assert resp_trav.get_json()["code"] == "RUTA_ARCHIVO_INVALIDA"


def test_tc07_fallo_generacion_pdf_revierte_estado_y_limpia_archivos(
    app, client, session, datos_escenario_16, monkeypatch
):
    """TC-07: Error I/O en STEP 1 no crea Resultado/Avisos/Auditoria y preserva estado."""
    def _fallar_pdf(self, *_args, **_kwargs):
        raise OSError("Error I/O simulado al escribir PDF")

    monkeypatch.setattr(FPDF, "output", _fallar_pdf)
    resp = _cargar_resultado_http(
        app, client, datos_escenario_16, [datos_escenario_16["v_pat"].id]
    )
    monkeypatch.undo()

    assert resp.status_code == 500
    body = resp.get_json()
    assert body["ok"] is False
    assert body["code"] == "ERROR_GENERACION_PDF_RESULTADO"
    assert body["retryable"] is True

    estudio = datos_escenario_16["estudio"]
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO
    assert session.scalars(select(Resultado)).all() == []
    assert session.scalars(select(AnalisisVariante)).all() == []
    assert session.scalars(select(Aviso)).all() == []
    assert session.scalars(select(RegistroModificacion)).all() == []
    carpeta_res = datos_escenario_16["tmp_path"] / "resultados"
    if carpeta_res.exists():
        assert list(carpeta_res.iterdir()) == []


def test_abort_cleanup_borra_pdf_huerfano_si_falla_crear_resultado_con_integrity_error(
    app, client, session, datos_escenario_16, monkeypatch
):
    """STEP 2 FAILURE(conflict): IntegrityError en flush limpia PDF ya escrito en STEP 1 y retorna 409."""
    def _fallar_integrity(**_kwargs):
        raise IntegrityError("INSERT INTO resultados", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(bioinformatica_repo, "crear_resultado", _fallar_integrity)
    resp = _cargar_resultado_http(
        app, client, datos_escenario_16, [datos_escenario_16["v_pat"].id]
    )
    monkeypatch.undo()

    assert resp.status_code == 409
    assert resp.get_json()["code"] == "RESULTADO_YA_EXISTE_PARA_ANALISIS"

    pdf_fisico = (
        datos_escenario_16["tmp_path"]
        / "resultados"
        / f"resultado_analisis_{datos_escenario_16['analisis'].id}.pdf"
    )
    assert not pdf_fisico.exists()

    estudio = datos_escenario_16["estudio"]
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO
    assert session.scalars(select(AnalisisVariante)).all() == []


def test_idempotencia_duplicados_y_conflicto_doble_carga(
    app, client, session, datos_escenario_16
):
    """Deduplica variantes_ids repetidas y rechaza 409 doble carga o analisis ya con resultado."""
    v_pat = datos_escenario_16["v_pat"]
    resp = _cargar_resultado_http(app, client, datos_escenario_16, [v_pat.id, v_pat.id])
    assert resp.status_code == 200
    assert len(resp.get_json()["variantes_registradas"]) == 1

    # Reenvio sobre estudio ya en Resultado cargado -> 409
    dup = _cargar_resultado_http(app, client, datos_escenario_16, [v_pat.id])
    assert dup.status_code == 409
    assert dup.get_json()["code"] == "ESTUDIO_NO_ESTA_EN_ANALISIS_BIOINFORMATICO"

    # Estado inconsistente (EN_ANALISIS_BIOINFORMATICO pero analisis ya tiene Resultado) -> 409
    estudio = datos_escenario_16["estudio"]
    estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICO
    session.commit()
    dup_res = _cargar_resultado_http(app, client, datos_escenario_16, [v_pat.id])
    assert dup_res.status_code == 409
    assert dup_res.get_json()["code"] == "RESULTADO_YA_EXISTE_PARA_ANALISIS"


def test_listar_mis_estudios_resultados_aislamiento_por_rol(app, client, datos_escenario_16):
    """GET /api/estudios/mis-estudios aisla estudios por titularidad y bloquea roles ajenos."""
    assert _cargar_resultado_http(
        app, client, datos_escenario_16, [datos_escenario_16["v_pat"].id]
    ).status_code == 200
    estudio_id = datos_escenario_16["estudio"].id

    # Paciente titular ve su estudio con resultado
    r_pac = client.get(
        "/api/estudios/mis-estudios",
        headers=_headers_para(app, datos_escenario_16["u_paciente"]),
    )
    assert r_pac.status_code == 200
    assert r_pac.headers.get("Cache-Control") == "private, no-store"
    estudios_pac = r_pac.get_json()["estudios"]
    assert len(estudios_pac) == 1
    assert estudios_pac[0]["estudio_id"] == estudio_id
    assert estudios_pac[0]["tiene_resultado"] is True
    assert estudios_pac[0]["resultado"]["diagnostico"] == "positivo"

    # Paciente ajeno ve lista vacia (no fuga estudios de terceros)
    r_otro_pac = client.get(
        "/api/estudios/mis-estudios",
        headers=_headers_para(app, datos_escenario_16["u_paciente_otro"]),
    )
    assert r_otro_pac.status_code == 200
    assert r_otro_pac.get_json()["estudios"] == []

    # Medico tratante ve el estudio; medico no vinculado ve lista vacia
    r_med = client.get(
        "/api/estudios/mis-estudios",
        headers=_headers_para(app, datos_escenario_16["u_medico"]),
    )
    assert r_med.status_code == 200
    assert [e["estudio_id"] for e in r_med.get_json()["estudios"]] == [estudio_id]

    r_med_otro = client.get(
        "/api/estudios/mis-estudios",
        headers=_headers_para(app, datos_escenario_16["u_medico_otro"]),
    )
    assert r_med_otro.status_code == 200
    assert r_med_otro.get_json()["estudios"] == []

    # Rol no permitido -> 403
    r_admin = client.get(
        "/api/estudios/mis-estudios",
        headers=_headers_para(app, datos_escenario_16["u_admin"]),
    )
    assert r_admin.status_code == 403
    assert r_admin.get_json()["code"] == "FORBIDDEN_RESULTADO_GENETICO"


