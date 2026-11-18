"""Tests de aceptacion para Escenario 15: Analizar un estudio mediante bioinformatica."""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from src.clients import EmailClient
from src.clients.exceptions import ClienteConexionError
from src.core.database import db
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
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)


def _token_para(app, usuario: Usuario) -> str:
    return emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=usuario.rol.value,
        scope=SCOPE_ACCESO_COMPLETO,
        ttl_segundos=3600,
    )


def _headers_para(app, usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token_para(app, usuario)}"}


@pytest.fixture
def escenario_datos(app, session, tmp_path):
    """Prepara usuarios, estudio en viaje a Corea y genes para Escenario 15."""
    app.config["STORAGE_DIR"] = str(tmp_path)

    u_admin = Usuario(
        email="admin.corea@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.ADMINISTRATIVO,
        nombre="Laura",
        apellido="Gomez",
        telefono="1144001100",
    )
    u_bio_1 = Usuario(
        email="bio1@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.BIOINFORMATICO,
        nombre="Ariadna",
        apellido="Guarino",
        telefono="1144002201",
    )
    u_bio_2 = Usuario(
        email="bio2@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.BIOINFORMATICO,
        nombre="Mateo",
        apellido="Silva",
        telefono="1144002202",
    )
    u_medico = Usuario(
        email="medico.exoma@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.MEDICO,
        nombre="Juan",
        apellido="Escudero",
        telefono="1144003300",
    )
    u_paciente = Usuario(
        email="paciente.exoma@gmail.com",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.PACIENTE,
        nombre="Sofia",
        apellido="Perez",
        telefono="1144004400",
    )
    session.add_all([u_admin, u_bio_1, u_bio_2, u_medico, u_paciente])
    session.flush()

    patologia = Patologia(nombre="Enfermedad de Pompe", descripcion="Glucogenosis tipo II")
    gen_gaa = Gen(simbolo="GAA", nombre="Alpha glucosidase", es_hallazgo_secundario=False)
    gen_brca1 = Gen(simbolo="BRCA1", nombre="BRCA1 DNA repair", es_hallazgo_secundario=True)
    gen_ajeno = Gen(simbolo="GLA", nombre="Galactosidasa alfa", es_hallazgo_secundario=False)
    session.add_all([patologia, gen_gaa, gen_brca1, gen_ajeno])
    session.flush()

    medico = Medico(usuario_id=u_medico.id, matricula="MN-9988")
    session.add(medico)
    session.flush()

    paciente = Paciente(
        usuario_id=u_paciente.id,
        medico_id=medico.id,
        dni="40111222",
        fecha_nacimiento=date(2026, 9, 1),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="Sospecha Pompe infantil",
        tipo_sospecha="clinica",
    )
    session.add(paciente)
    session.flush()

    estudio = Estudio(
        paciente_id=paciente.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.EN_VIAJE_COREA,
        es_pompe_urgente=False,
    )
    session.add(estudio)
    session.flush()

    session.add_all(
        [
            EstudioGen(estudio_id=estudio.id, gen_id=gen_gaa.id, origen=OrigenGen.PATOLOGIA),
            EstudioGen(estudio_id=estudio.id, gen_id=gen_brca1.id, origen=OrigenGen.HALLAZGO_SECUNDARIO),
        ]
    )
    session.commit()

    return {
        "u_admin": u_admin,
        "u_bio_1": u_bio_1,
        "u_bio_2": u_bio_2,
        "u_medico": u_medico,
        "u_paciente": u_paciente,
        "paciente": paciente,
        "medico": medico,
        "patologia": patologia,
        "gen_gaa": gen_gaa,
        "gen_brca1": gen_brca1,
        "gen_ajeno": gen_ajeno,
        "estudio": estudio,
        "tmp_path": tmp_path,
    }


def test_tc01_cargar_datos_crudos_json_y_multipart(app, client, session, escenario_datos):
    """TC-01: Administrativo carga ACTG, crea DatosCrudos, Analisis(INICIAL), auditoria y avisos."""
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "mail-bio-1", "estado": "pendiente"}
    app.config["EMAIL_CLIENT"] = mock_email

    estudio = escenario_datos["estudio"]
    resp = client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=_headers_para(app, escenario_datos["u_admin"]),
        json={
            "nombre_archivo": "corea_42.txt",
            "contenido_actg": ">seq_estudio\nATCGGCTA\nactg",
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["ok"] is True
    assert body["estudio_id"] == estudio.id
    assert body["estado_estudio"] == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA.value
    assert body["archivo_path"] == f"storage/datos_crudos/estudio_{estudio.id}.txt"

    archivo_fisico = escenario_datos["tmp_path"] / "datos_crudos" / f"estudio_{estudio.id}.txt"
    assert archivo_fisico.is_file()
    assert "ATCGGCTA\nACTG" in archivo_fisico.read_text(encoding="utf-8")

    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA

    dc = session.scalar(select(DatosCrudos).where(DatosCrudos.estudio_id == estudio.id))
    assert dc is not None
    assert dc.cargado_por_id == escenario_datos["u_admin"].id

    analisis = session.scalar(select(Analisis).where(Analisis.estudio_id == estudio.id))
    assert analisis is not None
    assert analisis.tipo == TipoAnalisis.INICIAL
    assert analisis.bioinformatico_id is None
    analisis_genes = session.scalars(
        select(AnalisisGen).where(AnalisisGen.analisis_id == analisis.id)
    ).all()
    assert {ag.gen_id for ag in analisis_genes} == {
        escenario_datos["gen_gaa"].id,
        escenario_datos["gen_brca1"].id,
    }

    auditoria = session.scalar(
        select(RegistroModificacion).where(
            RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
            RegistroModificacion.entidad_id == estudio.id,
        )
    )
    assert auditoria is not None
    assert auditoria.accion == TipoAccionAuditoria.CAMBIO_ESTADO
    assert auditoria.cambios["estado"]["nuevo"] == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA.value

    avisos_bio = session.scalars(
        select(Aviso).where(Aviso.usuario_id == escenario_datos["u_bio_1"].id)
    ).all()
    assert {a.canal for a in avisos_bio} == {CanalAviso.APP, CanalAviso.MAIL}
    assert all(a.enviado for a in avisos_bio)
    mock_email.enviar_aviso.assert_called_once()


def test_tc01b_cargar_datos_crudos_multipart_file_y_conflictos(app, client, session, escenario_datos):
    """Carga por multipart/form-data y rechazo ante duplicado o estado invalido."""
    import io

    estudio = escenario_datos["estudio"]
    headers = _headers_para(app, escenario_datos["u_admin"])

    resp = client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=headers,
        data={"archivo_datos_crudos": (io.BytesIO(b"ATCGATCG"), "corea.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201

    dup = client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=headers,
        json={"contenido_actg": "ATCG"},
    )
    assert dup.status_code == 409
    assert dup.get_json()["code"] == "DATOS_CRUDOS_YA_CARGADOS"

    # Estudio en estado distinto de En viaje a Corea sin datos crudos
    estudio_creado = Estudio(
        paciente_id=escenario_datos["paciente"].id,
        medico_id=escenario_datos["medico"].id,
        patologia_sospechada_id=escenario_datos["patologia"].id,
        estado=EstadoEstudio.CREADO,
    )
    session.add(estudio_creado)
    session.commit()

    err_estado = client.post(
        f"/api/estudios/{estudio_creado.id}/datos-crudos",
        headers=headers,
        json={"contenido_actg": "ATCG"},
    )
    assert err_estado.status_code == 409
    assert err_estado.get_json()["code"] == "ESTUDIO_NO_ESTA_EN_VIAJE_A_COREA"


@pytest.mark.parametrize("contenido_invalido", ["ACTGZ99", "   ", ">solo_header\n", "1234"])
def test_tc02_rechaza_datos_crudos_invalidos(app, client, session, escenario_datos, contenido_invalido):
    """TC-02: Rechaza con 400 ARCHIVO_DATOS_CRUDOS_INVALIDO y mantiene En viaje a Corea."""
    estudio = escenario_datos["estudio"]
    resp = client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=_headers_para(app, escenario_datos["u_admin"]),
        json={"contenido_actg": contenido_invalido},
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "ARCHIVO_DATOS_CRUDOS_INVALIDO"

    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.EN_VIAJE_COREA
    assert not (escenario_datos["tmp_path"] / "datos_crudos" / f"estudio_{estudio.id}.txt").exists()


def test_tc02b_abort_cleanup_elimina_archivo_si_falla_bd(app, client, session, escenario_datos, monkeypatch):
    """ABORT_CLEANUP: Si falla commit de BD tras escribir ACTG, elimina archivo huerfano."""
    estudio = escenario_datos["estudio"]

    def _fallar_commit():
        raise SQLAlchemyError("Error de BD simulado")

    monkeypatch.setattr(db.session, "commit", _fallar_commit)
    resp = client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=_headers_para(app, escenario_datos["u_admin"]),
        json={"contenido_actg": "ATCGGCTA"},
    )
    monkeypatch.undo()

    assert resp.status_code == 500
    assert not (escenario_datos["tmp_path"] / "datos_crudos" / f"estudio_{estudio.id}.txt").exists()
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.EN_VIAJE_COREA


def test_tc03_priorizacion_pompe_urgente_en_bandeja(app, client, session, escenario_datos):
    """TC-03: El estudio Pompe urgente mas reciente aparece en posicion 0 de la bandeja."""
    ahora = datetime.now()
    normal_antiguo = Estudio(
        paciente_id=escenario_datos["paciente"].id,
        medico_id=escenario_datos["medico"].id,
        patologia_sospechada_id=escenario_datos["patologia"].id,
        estado=EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        es_pompe_urgente=False,
        created_at=ahora - timedelta(hours=5),
        updated_at=ahora - timedelta(hours=5),
    )
    pompe_reciente = Estudio(
        paciente_id=escenario_datos["paciente"].id,
        medico_id=escenario_datos["medico"].id,
        patologia_sospechada_id=escenario_datos["patologia"].id,
        estado=EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        es_pompe_urgente=True,
        created_at=ahora,
        updated_at=ahora,
    )
    session.add_all([normal_antiguo, pompe_reciente])
    session.commit()

    resp = client.get(
        "/api/bioinformatica/estudios",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
    )
    assert resp.status_code == 200
    estudios = resp.get_json()["estudios"]
    assert len(estudios) == 2
    assert estudios[0]["estudio_id"] == pompe_reciente.id
    assert estudios[0]["es_pompe_urgente"] is True
    assert estudios[1]["estudio_id"] == normal_antiguo.id


def test_tc04_toma_exclusiva_y_bloqueo_concurrencia(app, client, session, escenario_datos):
    """TC-04: Bioinformatico A toma estudio (200) y Bioinformatico B recibe 409."""
    estudio = escenario_datos["estudio"]
    client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=_headers_para(app, escenario_datos["u_admin"]),
        json={"contenido_actg": "ATCGGCTA"},
    )

    resp_a = client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/tomar",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={},
    )
    assert resp_a.status_code == 200
    body_a = resp_a.get_json()
    assert body_a["estado_estudio"] == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO.value
    assert body_a["bioinformatico_id"] == escenario_datos["u_bio_1"].id
    assert {g["simbolo"] for g in body_a["genes"]} == {"GAA", "BRCA1"}

    resp_b = client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/tomar",
        headers=_headers_para(app, escenario_datos["u_bio_2"]),
        json={},
    )
    assert resp_b.status_code == 409
    assert resp_b.get_json()["code"] == "ESTUDIO_YA_TOMADO_POR_OTRO_BIOINFORMATICO"


def test_tc05_consulta_y_sincronizacion_variantes_y_fallback_cache(
    app, client, session, escenario_datos, monkeypatch
):
    """TC-05: Consulta variantes en Apigen, hace upsert por (gen_id, notacion) y usa cache local si cae."""
    gen_gaa = escenario_datos["gen_gaa"]

    class _ApigenOk:
        def obtener_variantes(self, simbolo: str):
            assert simbolo == "GAA"
            return [
                {"id": "GAA:c.1935C>A", "hgvs_c": "c.1935C>A", "clasificacion": "patogenica"},
                {"notacion": "c.2065G>A", "clinvar_id": "VCV000092611", "clasificacion": "benigna"},
                {"id": "GAA:c.1194+5G>A", "hgvs_c": "c.1194+5G>A", "clasificacion": "vus"},
            ]

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenOk()
    headers = _headers_para(app, escenario_datos["u_bio_1"])

    resp = client.get(f"/api/bioinformatica/genes/{gen_gaa.id}/variantes", headers=headers)
    assert resp.status_code == 200
    variantes = resp.get_json()["variantes"]
    assert len(variantes) == 3
    assert {v["clasificacion"] for v in variantes} == {"patogenica", "benigna", "vus"}

    # Reclasificacion de variante existente sin duplicar filas
    class _ApigenReclasificado:
        def obtener_variantes(self, simbolo: str):
            return [
                {"notacion": "c.1194+5G>A", "clinvar_id": "VCV000551203", "clasificacion": "patogenica"},
            ]

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenReclasificado()
    resp_upd = client.get(f"/api/bioinformatica/genes/{gen_gaa.id}/variantes", headers=headers)
    assert resp_upd.status_code == 200
    assert resp_upd.get_json()["variantes"][0]["clasificacion"] == "patogenica"
    total_bd = session.scalars(select(Variante).where(Variante.gen_id == gen_gaa.id)).all()
    assert len(total_bd) == 3

    # Contingencia: si la API falla 3 veces y hay cache local, responde 200 con warning
    class _ApigenCaido:
        def __init__(self):
            self.intentos = 0

        def obtener_variantes(self, simbolo: str):
            self.intentos += 1
            raise ClienteConexionError("Timeout Apigen")

    caido = _ApigenCaido()
    app.config["BIOINFORMATICA_CLIENT"] = caido
    monkeypatch.setattr("src.core.services.bioinformatica_service.time.sleep", lambda _s: None)

    resp_cache = client.get(f"/api/bioinformatica/genes/{gen_gaa.id}/variantes", headers=headers)
    assert resp_cache.status_code == 200
    assert caido.intentos == 3
    assert resp_cache.get_json()["warning"] == "USANDO_CATALOGO_LOCAL_CACHEADO"
    assert len(resp_cache.get_json()["variantes"]) == 3

    # Sin cache local en otro gen -> 502 retryable
    caido_sin_cache = _ApigenCaido()
    app.config["BIOINFORMATICA_CLIENT"] = caido_sin_cache
    resp_502 = client.get(
        f"/api/bioinformatica/genes/{escenario_datos['gen_ajeno'].id}/variantes",
        headers=headers,
    )
    assert resp_502.status_code == 502
    assert resp_502.get_json()["code"] == "BIOINFORMATICS_API_UNAVAILABLE"
    assert resp_502.get_json()["retryable"] is True


def test_tc06_registrar_variantes_positivo_genera_pdf_y_notifica(
    app, client, session, escenario_datos
):
    """TC-06: Registrar variante patogenica + VUS genera Resultado positivo, PDF y avisos."""
    mock_email = MagicMock(spec=EmailClient)
    mock_email.enviar_aviso.return_value = {"id": "mail-res-1", "estado": "pendiente"}
    app.config["EMAIL_CLIENT"] = mock_email

    estudio = escenario_datos["estudio"]
    gen_gaa = escenario_datos["gen_gaa"]

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
    session.add_all([v_pat, v_vus])
    session.commit()

    client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=_headers_para(app, escenario_datos["u_admin"]),
        json={"contenido_actg": "ATCGGCTA"},
    )
    client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/tomar",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={},
    )

    resp = client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/analisis",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={"variantes_ids": [v_pat.id, v_vus.id]},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["estado_estudio"] == EstadoEstudio.RESULTADO_CARGADO.value
    assert body["resultado"]["positivo"] is True
    assert body["resultado"]["diagnostico"] == ConclusionDiagnostica.POSITIVO.value
    assert body["resultado"]["fecha_proximo_estudio"] is None
    assert len(body["variantes_registradas"]) == 2

    pdf_fisico = (
        escenario_datos["tmp_path"]
        / "resultados"
        / f"resultado_analisis_{body['analisis_id']}.pdf"
    )
    assert pdf_fisico.is_file()
    assert pdf_fisico.read_bytes().startswith(b"%PDF-")

    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.RESULTADO_CARGADO
    assert estudio.fecha_reevaluacion_vus is None

    avs = session.scalars(
        select(AnalisisVariante).where(AnalisisVariante.analisis_id == body["analisis_id"])
    ).all()
    assert {av.variante_id for av in avs} == {v_pat.id, v_vus.id}

    res_bd = session.get(Resultado, body["resultado"]["id"])
    assert res_bd is not None
    assert res_bd.positivo is True

    aviso_pac = session.scalars(
        select(Aviso).where(Aviso.usuario_id == escenario_datos["u_paciente"].id)
    ).all()
    assert {a.canal for a in aviso_pac} == {CanalAviso.APP, CanalAviso.MAIL}


def test_tc06b_resultado_vus_programa_fecha_a_un_anio_y_bisiesto(
    app, client, session, escenario_datos
):
    """Resultado solo VUS (sin patogenicas) fija diagnostico='vus' y fecha +1 anio."""
    assert sumar_un_anio(date(2024, 2, 29)) == date(2025, 2, 28)

    estudio = escenario_datos["estudio"]
    v_vus = Variante(
        gen_id=escenario_datos["gen_gaa"].id,
        notacion="c.546G>T",
        clinvar_id="VCV000188901",
        clasificacion=ClasificacionVariante.VUS,
    )
    session.add(v_vus)
    session.commit()

    client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=_headers_para(app, escenario_datos["u_admin"]),
        json={"contenido_actg": "ATCGGCTA"},
    )
    client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/tomar",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={},
    )

    resp = client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/analisis",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={"variantes_ids": [v_vus.id]},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["resultado"]["positivo"] is False
    assert body["resultado"]["diagnostico"] == ConclusionDiagnostica.VUS.value
    assert body["resultado"]["fecha_proximo_estudio"] is not None

    session.refresh(estudio)
    assert estudio.fecha_reevaluacion_vus is not None
    assert estudio.fecha_reevaluacion_vus.isoformat() == body["resultado"]["fecha_proximo_estudio"]


def test_tc07_rechaza_variante_gen_no_solicitado_y_otro_bioinformatico(
    app, client, session, escenario_datos
):
    """TC-07: Rechaza 400 variante de gen ajeno y 403 si otro bioinformatico intenta cargar."""
    estudio = escenario_datos["estudio"]
    v_ajena = Variante(
        gen_id=escenario_datos["gen_ajeno"].id,
        notacion="c.644A>G",
        clinvar_id="VCV000010730",
        clasificacion=ClasificacionVariante.PATOGENICA,
    )
    session.add(v_ajena)
    session.commit()

    client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=_headers_para(app, escenario_datos["u_admin"]),
        json={"contenido_actg": "ATCGGCTA"},
    )
    client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/tomar",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={},
    )

    resp_400 = client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/analisis",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={"variantes_ids": [v_ajena.id]},
    )
    assert resp_400.status_code == 400
    assert resp_400.get_json()["code"] == "VARIANTE_FUERA_DE_GENES_DEL_ESTUDIO"

    resp_403 = client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/analisis",
        headers=_headers_para(app, escenario_datos["u_bio_2"]),
        json={"variantes_ids": []},
    )
    assert resp_403.status_code == 403
    assert resp_403.get_json()["code"] == "ESTUDIO_ASIGNADO_A_OTRO_BIOINFORMATICO"


def test_control_roles_y_rollback_pdf_en_analisis(
    app, client, session, escenario_datos, monkeypatch
):
    """Verifica 403 por rol incorrecto y ABORT_CLEANUP de PDF si falla commit en STEP 4."""
    estudio = escenario_datos["estudio"]

    # Rol no administrativo intentando cargar datos crudos
    r_403_admin = client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={"contenido_actg": "ATCG"},
    )
    assert r_403_admin.status_code == 403

    # Rol no bioinformatico intentando ver bandeja
    r_403_bio = client.get(
        "/api/bioinformatica/estudios",
        headers=_headers_para(app, escenario_datos["u_admin"]),
    )
    assert r_403_bio.status_code == 403

    # Carga y toma valida, luego falla commit en STEP 4 -> PDF eliminado y estado preservado
    client.post(
        f"/api/estudios/{estudio.id}/datos-crudos",
        headers=_headers_para(app, escenario_datos["u_admin"]),
        json={"contenido_actg": "ATCG"},
    )
    tomar = client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/tomar",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={},
    )
    analisis_id = tomar.get_json()["analisis_id"]

    def _fallar_commit():
        raise SQLAlchemyError("Fallo al guardar resultado")

    monkeypatch.setattr(db.session, "commit", _fallar_commit)
    resp_err = client.post(
        f"/api/bioinformatica/estudios/{estudio.id}/analisis",
        headers=_headers_para(app, escenario_datos["u_bio_1"]),
        json={"variantes_ids": []},
    )
    monkeypatch.undo()

    assert resp_err.status_code == 500
    assert not (
        escenario_datos["tmp_path"] / "resultados" / f"resultado_analisis_{analisis_id}.pdf"
    ).exists()
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO
