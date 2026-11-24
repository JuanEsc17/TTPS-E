"""Tests de aceptacion y seguridad API para Escenario 17: Reanalizar un estudio."""
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
    EntidadAuditable,
    EstadoEstudio,
    Estudio,
    EstudioGen,
    Gen,
    Medico,
    OrigenGen,
    Paciente,
    Patologia,
    PatologiaGen,
    RegistroModificacion,
    Resultado,
    Rol,
    TipoAccionAuditoria,
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
def datos_escenario_17(app, session, tmp_path):
    """Prepara un estudio en RESULTADO_CARGADO con DatosCrudos y analisis inicial NEGATIVO en GLA."""
    app.config["STORAGE_DIR"] = str(tmp_path)

    u_bio = Usuario(
        email="bio.e17@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.BIOINFORMATICO,
        nombre="Ariadna",
        apellido="Guarino",
        telefono="1144001701",
    )
    u_medico = Usuario(
        email="medico.e17@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.MEDICO,
        nombre="Juan",
        apellido="Escudero",
        telefono="1144001702",
    )
    u_medico_otro = Usuario(
        email="medico.otro.e17@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.MEDICO,
        nombre="Clara",
        apellido="Mendez",
        telefono="1144001703",
    )
    u_paciente = Usuario(
        email="paciente.e17@gmail.com",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.PACIENTE,
        nombre="Sofia",
        apellido="Perez",
        telefono="1144001704",
    )
    u_paciente_otro = Usuario(
        email="paciente.otro.e17@gmail.com",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.PACIENTE,
        nombre="Lucas",
        apellido="Gomez",
        telefono="1144001705",
    )
    u_admin = Usuario(
        email="admin.e17@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.ADMINISTRATIVO,
        nombre="Laura",
        apellido="Diaz",
        telefono="1144001706",
    )
    session.add_all([u_bio, u_medico, u_medico_otro, u_paciente, u_paciente_otro, u_admin])
    session.flush()

    pat_fabry = Patologia(nombre="Fabry", descripcion="Enfermedad lisosomal ligada al X")
    pat_mps1 = Patologia(nombre="MPS1", descripcion="Mucopolisacaridosis tipo I")
    gen_gla = Gen(simbolo="GLA", nombre="Galactosidasa alfa", es_hallazgo_secundario=False)
    gen_idua = Gen(simbolo="IDUA", nombre="Alfa-L-iduronidasa", es_hallazgo_secundario=False)
    gen_gba = Gen(simbolo="GBA", nombre="Glucosilceramidasa beta", es_hallazgo_secundario=False)
    session.add_all([pat_fabry, pat_mps1, gen_gla, gen_idua, gen_gba])
    session.flush()

    session.add_all(
        [
            PatologiaGen(patologia_id=pat_fabry.id, gen_id=gen_gla.id),
            PatologiaGen(patologia_id=pat_mps1.id, gen_id=gen_idua.id),
        ]
    )

    medico = Medico(usuario_id=u_medico.id, matricula="MN-17001")
    medico_otro = Medico(usuario_id=u_medico_otro.id, matricula="MN-17002")
    session.add_all([medico, medico_otro])
    session.flush()

    paciente = Paciente(
        usuario_id=u_paciente.id,
        medico_id=medico.id,
        dni="40171717",
        fecha_nacimiento=date(1993, 6, 15),
        diagnostico_presuntivo_id=pat_fabry.id,
        historia_clinica="Sospecha inicial de Fabry",
        tipo_sospecha="clinica",
    )
    paciente_otro = Paciente(
        usuario_id=u_paciente_otro.id,
        medico_id=medico_otro.id,
        dni="40979797",
        fecha_nacimiento=date(1990, 2, 2),
        diagnostico_presuntivo_id=pat_fabry.id,
        historia_clinica="Otro paciente",
        tipo_sospecha="clinica",
    )
    session.add_all([paciente, paciente_otro])
    session.flush()

    estudio = Estudio(
        paciente_id=paciente.id,
        medico_id=medico.id,
        patologia_sospechada_id=pat_fabry.id,
        estado=EstadoEstudio.EN_ANALISIS_BIOINFORMATICO,
        es_pompe_urgente=False,
    )
    session.add(estudio)
    session.flush()
    session.add(EstudioGen(estudio_id=estudio.id, gen_id=gen_gla.id, origen=OrigenGen.PATOLOGIA))

    dc_rel = f"storage/datos_crudos/estudio_{estudio.id}.txt"
    dc_fisico = tmp_path / "datos_crudos" / f"estudio_{estudio.id}.txt"
    dc_fisico.parent.mkdir(parents=True, exist_ok=True)
    dc_fisico.write_text(">estudio_exoma\nATCGGCTAGCTAGCTA\n", encoding="utf-8")
    session.add(
        DatosCrudos(
            estudio_id=estudio.id,
            cargado_por_id=u_admin.id,
            archivo_path=dc_rel,
        )
    )

    analisis_inicial = Analisis(
        estudio_id=estudio.id,
        tipo=TipoAnalisis.INICIAL,
        bioinformatico_id=u_bio.id,
    )
    session.add(analisis_inicial)
    session.flush()
    session.add(AnalisisGen(analisis_id=analisis_inicial.id, gen_id=gen_gla.id))

    v_gla_ben = Variante(
        gen_id=gen_gla.id,
        notacion="c.937G>T",
        clinvar_id="VCV000010765",
        clasificacion=ClasificacionVariante.BENIGNA,
    )
    v_idua_pat = Variante(
        gen_id=gen_idua.id,
        notacion="c.1205G>A",
        clinvar_id="VCV000011908",
        clasificacion=ClasificacionVariante.PATOGENICA,
    )
    v_gba_vus = Variante(
        gen_id=gen_gba.id,
        notacion="c.1448T>C",
        clinvar_id="VCV000004288",
        clasificacion=ClasificacionVariante.VUS,
    )
    session.add_all([v_gla_ben, v_idua_pat, v_gba_vus])
    session.commit()

    # Completar analisis inicial NEGATIVO para dejar el estudio en RESULTADO_CARGADO
    r_inicial = app.test_client().post(
        f"/api/bioinformatica/estudios/{estudio.id}/analisis",
        headers=_headers_para(app, u_bio),
        json={"variantes_ids": [v_gla_ben.id]},
    )
    assert r_inicial.status_code == 200
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.RESULTADO_CARGADO

    return {
        "u_bio": u_bio,
        "u_medico": u_medico,
        "u_medico_otro": u_medico_otro,
        "u_paciente": u_paciente,
        "u_paciente_otro": u_paciente_otro,
        "u_admin": u_admin,
        "medico": medico,
        "paciente": paciente,
        "pat_fabry": pat_fabry,
        "pat_mps1": pat_mps1,
        "gen_gla": gen_gla,
        "gen_idua": gen_idua,
        "gen_gba": gen_gba,
        "estudio": estudio,
        "analisis_inicial": analisis_inicial,
        "v_gla_ben": v_gla_ben,
        "v_idua_pat": v_idua_pat,
        "v_gba_vus": v_gba_vus,
        "tmp_path": tmp_path,
    }


def test_tc01_solicitud_exitosa_reanalisis_por_medico_tratante(
    app, client, session, datos_escenario_17
):
    """TC-01: POST /api/estudios/<id>/reanalisis crea Analisis(REANALISIS), audita y avisa a bioinformatica."""
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "mail-re17-1", "estado": "enviado"}
    app.config["EMAIL_CLIENT"] = mock_email

    estudio = datos_escenario_17["estudio"]
    resp = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=_headers_para(app, datos_escenario_17["u_medico"]),
        json={
            "nuevos_genes_simbolos": ["idua", "GBA", "IDUA"],
            "nueva_patologia_sospechada_id": datos_escenario_17["pat_mps1"].id,
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["ok"] is True
    assert body["estudio_id"] == estudio.id
    assert body["tipo_analisis"] == TipoAnalisis.REANALISIS.value
    assert body["solicitado_por_medico_id"] == datos_escenario_17["medico"].id
    assert [g["simbolo"] for g in body["nuevos_genes"]] == ["IDUA", "GBA"]
    assert body["estado_estudio"] == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA.value
    assert body["requiere_nueva_muestra"] is False

    # No se creo otro Estudio; el mismo estudio tiene ahora 2 Analisis y 3 EstudioGen
    assert len(session.scalars(select(Estudio)).all()) == 1
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA
    assert estudio.patologia_sospechada_id == datos_escenario_17["pat_mps1"].id
    assert len(estudio.analisis) == 2
    assert estudio.analisis[0].tipo == TipoAnalisis.INICIAL
    assert estudio.analisis[0].resultado is not None
    reanalisis = estudio.analisis[1]
    assert reanalisis.id == body["analisis_id"]
    assert reanalisis.tipo == TipoAnalisis.REANALISIS
    assert reanalisis.solicitado_por_id == datos_escenario_17["medico"].id
    assert reanalisis.bioinformatico_id is None
    assert sorted(ag.gen.simbolo for ag in reanalisis.genes) == ["GBA", "IDUA"]

    origenes_por_gen = {eg.gen.simbolo: eg.origen for eg in estudio.genes}
    assert origenes_por_gen["GLA"] == OrigenGen.PATOLOGIA
    assert origenes_por_gen["IDUA"] == OrigenGen.PATOLOGIA
    assert origenes_por_gen["GBA"] == OrigenGen.MANUAL

    # Registro de auditoria del cambio de estado
    auditorias = session.scalars(
        select(RegistroModificacion)
        .where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
            RegistroModificacion.entidad_id == estudio.id,
        )
        .order_by(RegistroModificacion.id.desc())
    ).all()
    ultima = auditorias[0]
    assert ultima.accion == TipoAccionAuditoria.CAMBIO_ESTADO
    assert ultima.usuario_id == datos_escenario_17["u_medico"].id
    assert ultima.cambios["estado"] == {
        "anterior": EstadoEstudio.RESULTADO_CARGADO.value,
        "nuevo": EstadoEstudio.EN_ANALISIS_BIOINFORMATICA.value,
    }
    assert ultima.cambios["tipo_analisis"]["nuevo"] == TipoAnalisis.REANALISIS.value
    assert ultima.cambios["patologia_sospechada_id"]["nuevo"] == datos_escenario_17["pat_mps1"].id

    # Aviso APP y MAIL al bioinformatico + despacho de correo
    avisos_bio = session.scalars(
        select(Aviso).where(Aviso.usuario_id == datos_escenario_17["u_bio"].id)
    ).all()
    assert {a.canal for a in avisos_bio} == {CanalAviso.APP, CanalAviso.MAIL}
    assert all(a.enviado is True for a in avisos_bio)
    mock_email.enviar_aviso.assert_called_once()
    assert datos_escenario_17["u_bio"].email in mock_email.enviar_aviso.call_args.kwargs["destinatarios"]


def test_tc01b_valida_gen_nuevo_en_apigen_y_maneja_desconocido_o_caida(
    app, client, session, datos_escenario_17
):
    """STEP 1.3: Si un simbolo no esta en BD local, valida via Apigen; rechaza desconocido o 503."""
    estudio = datos_escenario_17["estudio"]
    headers_med = _headers_para(app, datos_escenario_17["u_medico"])

    # Apigen no encuentra el gen -> 400 GEN_DESCONOCIDO
    mock_apigen = MagicMock()
    mock_apigen.buscar_genes.return_value = [{"simbolo": "OTRO"}]
    app.config["BIOINFORMATICA_CLIENT"] = mock_apigen
    r_400 = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=headers_med,
        json={"nuevos_genes_simbolos": ["NOEXISTE"]},
    )
    assert r_400.status_code == 400
    assert r_400.get_json()["code"] == "GEN_DESCONOCIDO"

    # Apigen caido -> 503 retryable
    mock_apigen.buscar_genes.side_effect = ClienteServicioError("503 Apigen", codigo_http=503)
    r_503 = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=headers_med,
        json={"nuevos_genes_simbolos": ["SMPD1"]},
    )
    assert r_503.status_code == 503
    assert r_503.get_json()["code"] == "API_BIOINFORMATICA_NO_DISPONIBLE"
    assert r_503.get_json()["retryable"] is True

    # Apigen valida SMPD1 -> se crea Gen local y se abre el reanalisis
    mock_apigen.buscar_genes.side_effect = None
    mock_apigen.buscar_genes.return_value = [{"simbolo": "SMPD1", "nombre": "Esfingomielinasa"}]
    r_ok = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=headers_med,
        json={"nuevos_genes_simbolos": ["SMPD1"]},
    )
    assert r_ok.status_code == 201
    assert r_ok.get_json()["nuevos_genes"][0]["simbolo"] == "SMPD1"
    assert session.scalar(select(Gen).where(Gen.simbolo == "SMPD1")) is not None


def test_tc02_y_tc06_ciclo_completo_reanalisis_preserva_historial_y_pdfs(
    app, client, session, datos_escenario_17, monkeypatch, caplog
):
    """TC-02 y TC-06: Solicitud -> historial y PDF inicial accesibles en curso -> tomar -> cargar resultado."""
    estudio = datos_escenario_17["estudio"]
    inicial_id = datos_escenario_17["analisis_inicial"].id
    headers_med = _headers_para(app, datos_escenario_17["u_medico"])
    headers_pac = _headers_para(app, datos_escenario_17["u_paciente"])
    headers_bio = _headers_para(app, datos_escenario_17["u_bio"])

    # 1) Medico solicita reanalisis sobre IDUA y GBA
    r_sol = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=headers_med,
        json={"nuevos_genes_simbolos": ["IDUA", "GBA"]},
    )
    assert r_sol.status_code == 201
    reanalisis_id = r_sol.get_json()["analisis_id"]

    # 2) Mientras el reanalisis esta en curso, GET /analisis muestra ambos analisis y PDF inicial sigue descargable
    r_hist_curso = client.get(f"/api/estudios/{estudio.id}/analisis", headers=headers_med)
    assert r_hist_curso.status_code == 200
    assert r_hist_curso.headers.get("Cache-Control") == "private, no-store"
    body_curso = r_hist_curso.get_json()
    assert body_curso["estado_estudio"] == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA.value
    assert body_curso["puede_solicitar_reanalisis"] is False
    assert len(body_curso["historial_analisis"]) == 2
    assert body_curso["historial_analisis"][0]["analisis_id"] == inicial_id
    assert body_curso["historial_analisis"][0]["resultado"]["positivo"] is False
    assert (
        body_curso["historial_analisis"][0]["resultado"]["pdf_url"]
        == f"/api/estudios/{estudio.id}/analisis/{inicial_id}/resultado/pdf"
    )
    assert body_curso["historial_analisis"][1]["analisis_id"] == reanalisis_id
    assert body_curso["historial_analisis"][1]["resultado"] is None

    r_pdf_ini_en_curso = client.get(
        f"/api/estudios/{estudio.id}/analisis/{inicial_id}/resultado/pdf",
        headers=headers_pac,
    )
    assert r_pdf_ini_en_curso.status_code == 200
    assert "NEGATIVO" in _extraer_texto_pdf(r_pdf_ini_en_curso.data)

    # 3) Bandeja de bioinformatica muestra el estudio como REANALISIS con solo los nuevos genes
    r_bandeja = client.get("/api/bioinformatica/estudios", headers=headers_bio)
    assert r_bandeja.status_code == 200
    pendientes = r_bandeja.get_json()["estudios"]
    assert len(pendientes) == 1
    assert pendientes[0]["estudio_id"] == estudio.id
    assert pendientes[0]["tipo_analisis"] == TipoAnalisis.REANALISIS.value
    assert sorted(g["simbolo"] for g in pendientes[0]["genes"]) == ["GBA", "IDUA"]

    # 4) Bioinformatico toma el reanalisis y carga variante VUS en GBA -> fecha_reevaluacion_vus +1 anio
    monkeypatch.setattr(
        resultado_service,
        "ahora_utc_naive",
        lambda: datetime(2026, 11, 21, 15, 0, 0),
    )
    with caplog.at_level(logging.INFO):
        r_tomar = client.post(
            f"/api/bioinformatica/estudios/{estudio.id}/tomar",
            headers=headers_bio,
        )
        assert r_tomar.status_code == 200
        assert r_tomar.get_json()["analisis_id"] == reanalisis_id
        assert r_tomar.get_json()["estado_estudio"] == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO.value

        # Datos crudos previos siguen accesibles para el bioinformatico asignado
        r_dc = client.get(
            f"/api/bioinformatica/estudios/{estudio.id}/datos-crudos",
            headers=headers_bio,
        )
        assert r_dc.status_code == 200
        assert r_dc.get_json()["total_bases"] == 16

        # Intentar cargar una variante de GLA (del analisis inicial, no del reanalisis) falla con 400
        r_fuera = client.post(
            f"/api/bioinformatica/estudios/{estudio.id}/analisis",
            headers=headers_bio,
            json={"variantes_ids": [datos_escenario_17["v_gla_ben"].id]},
        )
        assert r_fuera.status_code == 400
        assert r_fuera.get_json()["code"] == "VARIANTE_FUERA_DE_GENES_DEL_ESTUDIO"

        mock_email = MagicMock(spec=EmailClient)
        mock_email.enviar_aviso.return_value = {"id": "mail-res-re", "estado": "enviado"}
        app.config["EMAIL_CLIENT"] = mock_email

        r_cargar = client.post(
            f"/api/bioinformatica/estudios/{estudio.id}/analisis",
            headers=headers_bio,
            json={"variantes_ids": [datos_escenario_17["v_idua_pat"].id]},
        )

    assert r_cargar.status_code == 200
    body_cargar = r_cargar.get_json()
    assert body_cargar["tipo_analisis"] == TipoAnalisis.REANALISIS.value
    assert body_cargar["total_analisis_en_historial"] == 2
    assert body_cargar["resultado"]["positivo"] is True
    assert body_cargar["resultado"]["diagnostico"] == ConclusionDiagnostica.POSITIVO.value
    assert body_cargar["estado_estudio"] == EstadoEstudio.RESULTADO_CARGADO.value
    assert f"reanalisis_tomado estudio_id={estudio.id}" in caplog.text
    assert f"reanalisis_completado estudio_id={estudio.id}" in caplog.text

    # Notificados paciente y medico
    destinatarios = set(mock_email.enviar_aviso.call_args.kwargs["destinatarios"])
    assert datos_escenario_17["u_paciente"].email in destinatarios
    assert datos_escenario_17["u_medico"].email in destinatarios

    # 5) Historial completo preserva analisis #1 (NEGATIVO) y analisis #2 (POSITIVO) con ambos PDFs descargables
    r_hist_final = client.get(f"/api/estudios/{estudio.id}/analisis", headers=headers_pac)
    assert r_hist_final.status_code == 200
    hist = r_hist_final.get_json()["historial_analisis"]
    assert len(hist) == 2
    assert hist[0]["tipo"] == TipoAnalisis.INICIAL.value
    assert hist[0]["resultado"]["positivo"] is False
    assert hist[1]["tipo"] == TipoAnalisis.REANALISIS.value
    assert hist[1]["resultado"]["positivo"] is True

    pdf_1 = client.get(hist[0]["resultado"]["pdf_url"], headers=headers_pac)
    pdf_2 = client.get(hist[1]["resultado"]["pdf_url"], headers=headers_pac)
    assert pdf_1.status_code == 200 and "NEGATIVO" in _extraer_texto_pdf(pdf_1.data)
    assert pdf_2.status_code == 200 and "POSITIVO" in _extraer_texto_pdf(pdf_2.data)
    assert "c.1205G>A" in _extraer_texto_pdf(pdf_2.data)


def test_tc03_rechaza_genes_ya_analizados_o_vacios_y_filtra_mezcla(
    app, client, datos_escenario_17
):
    """TC-03: 400 GENES_YA_ANALIZADOS_O_VACIOS si solo pide GLA o vacio; si mezcla GLA+IDUA analiza solo IDUA."""
    estudio_id = datos_escenario_17["estudio"].id
    headers_med = _headers_para(app, datos_escenario_17["u_medico"])

    for payload in (
        {"nuevos_genes_simbolos": []},
        {"nuevos_genes_simbolos": ["GLA"]},
        {"genes_ids": [datos_escenario_17["gen_gla"].id]},
        {},
    ):
        r = client.post(
            f"/api/estudios/{estudio_id}/reanalisis",
            headers=headers_med,
            json=payload,
        )
        assert r.status_code == 400
        assert r.get_json()["code"] == "GENES_YA_ANALIZADOS_O_VACIOS"

    # Mezcla de gen ya analizado (GLA) + gen nuevo (IDUA) -> solo crea reanalisis para IDUA
    r_mix = client.post(
        f"/api/estudios/{estudio_id}/reanalisis",
        headers=headers_med,
        json={"nuevos_genes_simbolos": ["GLA", "IDUA"]},
    )
    assert r_mix.status_code == 201
    assert [g["simbolo"] for g in r_mix.get_json()["nuevos_genes"]] == ["IDUA"]


def test_tc04_rechaza_409_estudio_no_apto_para_reanalisis(
    app, client, session, datos_escenario_17
):
    """TC-04: 409 ESTUDIO_NO_APTO_PARA_REANALISIS si no esta en RESULTADO_CARGADO o faltan DatosCrudos."""
    estudio = datos_escenario_17["estudio"]
    headers_med = _headers_para(app, datos_escenario_17["u_medico"])

    estudio.estado = EstadoEstudio.EN_VIAJE_COREA
    session.commit()
    r_estado = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=headers_med,
        json={"nuevos_genes_simbolos": ["IDUA"]},
    )
    assert r_estado.status_code == 409
    assert r_estado.get_json()["code"] == "ESTUDIO_NO_APTO_PARA_REANALISIS"

    # Estudio en RESULTADO_CARGADO pero sin DatosCrudos -> 409
    estudio.estado = EstadoEstudio.RESULTADO_CARGADO
    session.delete(estudio.datos_crudos)
    session.commit()
    r_sin_dc = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=headers_med,
        json={"nuevos_genes_simbolos": ["IDUA"]},
    )
    assert r_sin_dc.status_code == 409
    assert r_sin_dc.get_json()["code"] == "ESTUDIO_NO_APTO_PARA_REANALISIS"


def test_tc05_seguridad_roles_y_medico_ajeno_403_y_401(
    app, client, session, datos_escenario_17
):
    """TC-05: Sin sesion -> 401; Paciente, Administrativo, Bioinformatico y otro Medico -> 403."""
    estudio = datos_escenario_17["estudio"]

    assert client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        json={"nuevos_genes_simbolos": ["IDUA"]},
    ).status_code == 401

    for usuario in (
        datos_escenario_17["u_paciente"],
        datos_escenario_17["u_admin"],
        datos_escenario_17["u_bio"],
        datos_escenario_17["u_medico_otro"],
    ):
        r = client.post(
            f"/api/estudios/{estudio.id}/reanalisis",
            headers=_headers_para(app, usuario),
            json={"nuevos_genes_simbolos": ["IDUA"]},
        )
        assert r.status_code == 403
        assert r.get_json()["ok"] is False

    # Medico ajeno sobre estudio en EN_VIAJE_COREA recibe 403 (NO 409, evita oracle de estado)
    estudio.estado = EstadoEstudio.EN_VIAJE_COREA
    session.commit()
    r_oracle = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=_headers_para(app, datos_escenario_17["u_medico_otro"]),
        json={"nuevos_genes_simbolos": ["IDUA"]},
    )
    assert r_oracle.status_code == 403
    assert r_oracle.get_json()["code"] == "FORBIDDEN_REANALISIS_ESTUDIO"

    # Estudio inexistente para medico -> 404
    r_404 = client.post(
        "/api/estudios/999999/reanalisis",
        headers=_headers_para(app, datos_escenario_17["u_medico"]),
        json={"nuevos_genes_simbolos": ["IDUA"]},
    )
    assert r_404.status_code == 404


def test_historial_analisis_aislamiento_seguridad(app, client, datos_escenario_17):
    """GET /api/estudios/<id>/analisis aisla por titularidad/tratante y bloquea ajenos con 403."""
    estudio_id = datos_escenario_17["estudio"].id
    assert client.get(f"/api/estudios/{estudio_id}/analisis").status_code == 401

    for permitido in (
        datos_escenario_17["u_paciente"],
        datos_escenario_17["u_medico"],
        datos_escenario_17["u_bio"],
    ):
        r = client.get(f"/api/estudios/{estudio_id}/analisis", headers=_headers_para(app, permitido))
        assert r.status_code == 200
        assert r.get_json()["genes_ya_analizados"] == ["GLA"]

    for bloqueado in (
        datos_escenario_17["u_paciente_otro"],
        datos_escenario_17["u_medico_otro"],
        datos_escenario_17["u_admin"],
    ):
        r = client.get(f"/api/estudios/{estudio_id}/analisis", headers=_headers_para(app, bloqueado))
        assert r.status_code == 403


def test_abort_cleanup_preserva_historial_y_pdf_inicial(
    app, client, session, datos_escenario_17, monkeypatch
):
    """ABORT_CLEANUP: error en STEP 2 o fallo PDF en STEP 4 nunca corrompe historial ni borra PDF inicial."""
    estudio = datos_escenario_17["estudio"]
    inicial_id = datos_escenario_17["analisis_inicial"].id
    pdf_inicial = datos_escenario_17["tmp_path"] / "resultados" / f"resultado_analisis_{inicial_id}.pdf"
    assert pdf_inicial.is_file()
    bytes_pdf_inicial = pdf_inicial.read_bytes()

    # Fallo BD en STEP 2 -> rollback, estudio sigue en RESULTADO_CARGADO con 1 solo analisis
    def _fallar_db(**_kwargs):
        raise OperationalError("INSERT INTO analisis", {}, Exception("db down"))

    monkeypatch.setattr(bioinformatica_repo, "crear_analisis_reanalisis", _fallar_db)
    r_err_s2 = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=_headers_para(app, datos_escenario_17["u_medico"]),
        json={"nuevos_genes_simbolos": ["IDUA"]},
    )
    monkeypatch.undo()
    assert r_err_s2.status_code == 500
    assert r_err_s2.get_json()["retryable"] is True
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.RESULTADO_CARGADO
    assert len(estudio.analisis) == 1

    # Crear y tomar reanalisis, luego simular fallo de escritura PDF en STEP 4
    r_sol = client.post(
        f"/api/estudios/{estudio.id}/reanalisis",
        headers=_headers_para(app, datos_escenario_17["u_medico"]),
        json={"nuevos_genes_simbolos": ["IDUA"]},
    )
    assert r_sol.status_code == 201
    reanalisis_id = r_sol.get_json()["analisis_id"]
    assert client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/tomar",
        headers=_headers_para(app, datos_escenario_17["u_bio"]),
    ).status_code == 200

    monkeypatch.setattr(FPDF, "output", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("Disco lleno")))
    r_err_s4 = client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/analisis",
        headers=_headers_para(app, datos_escenario_17["u_bio"]),
        json={"variantes_ids": [datos_escenario_17["v_idua_pat"].id]},
    )
    monkeypatch.undo()
    assert r_err_s4.status_code == 500
    assert r_err_s4.get_json()["retryable"] is True

    # PDF del analisis inicial sigue intacto; no quedo PDF del reanalisis fallido; resultado #1 intacto
    assert pdf_inicial.is_file()
    assert pdf_inicial.read_bytes() == bytes_pdf_inicial
    assert not (
        datos_escenario_17["tmp_path"] / "resultados" / f"resultado_analisis_{reanalisis_id}.pdf"
    ).exists()
    assert session.scalar(select(Resultado).where(Resultado.analisis_id == inicial_id)) is not None
    assert session.scalar(select(Resultado).where(Resultado.analisis_id == reanalisis_id)) is None


def test_catalogo_genes_busqueda_local_apigen_y_permisos(app, client, datos_escenario_17):
    """GET /api/genes filtra locales, enriquece con Apigen y restringe acceso por rol."""
    assert client.get("/api/genes").status_code == 401
    assert client.get(
        "/api/genes",
        headers=_headers_para(app, datos_escenario_17["u_paciente"]),
    ).status_code == 403

    mock_apigen = MagicMock()
    mock_apigen.buscar_genes.return_value = [{"simbolo": "GAA"}, {"simbolo": "GBA"}]
    app.config["BIOINFORMATICA_CLIENT"] = mock_apigen

    r = client.get("/api/genes?q=GA", headers=_headers_para(app, datos_escenario_17["u_medico"]))
    assert r.status_code == 200
    simbolos = [g["simbolo"] for g in r.get_json()["genes"]]
    assert "GAA" in simbolos and "GBA" in simbolos
