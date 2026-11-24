"""Tests de aceptacion para Escenario 24: Consultar variantes."""
from datetime import date, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.clients import ApigenClient, ClienteConexionError, ClienteServicioError
from src.core.database import db
from src.core.models import (
    Analisis,
    AnalisisGen,
    ClasificacionVariante,
    ConclusionDiagnostica,
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


@pytest.fixture
def datos_escenario_24(session):
    """Prepara usuarios, estudio en analisis bioinformatico y genes para Escenario 24."""
    u_bio_1 = Usuario(
        email="bio24_1@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.BIOINFORMATICO,
        nombre="Ariadna",
        apellido="Guarino",
        telefono="1144002401",
    )
    u_bio_2 = Usuario(
        email="bio24_2@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.BIOINFORMATICO,
        nombre="Mateo",
        apellido="Silva",
        telefono="1144002402",
    )
    u_medico = Usuario(
        email="medico24@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.MEDICO,
        nombre="Juan",
        apellido="Escudero",
        telefono="1144002403",
    )
    u_admin = Usuario(
        email="admin24@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.ADMINISTRATIVO,
        nombre="Laura",
        apellido="Gomez",
        telefono="1144002404",
    )
    u_paciente = Usuario(
        email="pac24@gmail.com",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.PACIENTE,
        nombre="Sofia",
        apellido="Perez",
        telefono="1144002405",
    )
    session.add_all([u_bio_1, u_bio_2, u_medico, u_admin, u_paciente])
    session.flush()

    patologia = Patologia(nombre="Enfermedad de Pompe 24", descripcion="Glucogenosis tipo II")
    gen_gaa = Gen(simbolo="GAA", nombre="Alpha glucosidase", es_hallazgo_secundario=False)
    gen_gla = Gen(simbolo="GLA", nombre="Galactosidasa alfa", es_hallazgo_secundario=False)
    gen_reanalisis = Gen(simbolo="GBA", nombre="Glucocerebrosidasa", es_hallazgo_secundario=False)
    session.add_all([patologia, gen_gaa, gen_gla, gen_reanalisis])
    session.flush()

    medico = Medico(usuario_id=u_medico.id, matricula="MN-2424")
    session.add(medico)
    session.flush()

    paciente = Paciente(
        usuario_id=u_paciente.id,
        medico_id=medico.id,
        dni="40242424",
        fecha_nacimiento=date(2020, 5, 10),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="Sospecha Pompe",
        tipo_sospecha="clinica",
    )
    session.add(paciente)
    session.flush()

    estudio = Estudio(
        paciente_id=paciente.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.EN_ANALISIS_BIOINFORMATICO,
    )
    session.add(estudio)
    session.flush()

    session.add(EstudioGen(estudio_id=estudio.id, gen_id=gen_gaa.id, origen=OrigenGen.PATOLOGIA))
    analisis = Analisis(
        estudio_id=estudio.id,
        tipo=TipoAnalisis.INICIAL,
        bioinformatico_id=u_bio_1.id,
    )
    session.add(analisis)
    session.flush()
    session.add(AnalisisGen(analisis_id=analisis.id, gen_id=gen_gaa.id))
    session.commit()

    return {
        "u_bio_1": u_bio_1,
        "u_bio_2": u_bio_2,
        "u_medico": u_medico,
        "u_admin": u_admin,
        "estudio": estudio,
        "analisis": analisis,
        "gen_gaa": gen_gaa,
        "gen_gla": gen_gla,
        "gen_reanalisis": gen_reanalisis,
    }


def test_tc01_happy_path_consulta_y_sincroniza_variantes(app, client, session, datos_escenario_24):
    """TC-01: Consulta variantes de un gen del estudio, devuelve contrato v1 y persiste en BD."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    class _ApigenOk:
        def obtener_variantes(self, simbolo: str):
            assert simbolo == "GAA"
            return {
                "ok": True,
                "gen_simbolo": "GAA",
                "variantes": [
                    {"notacion": "c.-32-13T>G", "clinvar_id": "VCV000004027", "clasificacion": "patogenica"},
                    {"notacion": "c.2065G>A", "clinvar_id": "VCV000092615", "clasificacion": "benigna"},
                    {"notacion": "c.546G>T", "clinvar_id": "VCV000188901", "clasificacion": "inocua"},
                    {"notacion": "c.1551+5G>A", "clinvar_id": "VCV000451822", "clasificacion": "vus"},
                ],
            }

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenOk()
    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_1"]),
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    data = body["data"]
    assert data["estudio_id"] == estudio.id
    assert data["estado_estudio"] == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO.value
    assert data["gen"] == {
        "gen_id": gen_gaa.id,
        "simbolo": "GAA",
        "nombre": "Alpha glucosidase",
    }
    assert data["fuente"] == "api_bioinformatica"
    assert len(data["variantes"]) == 4
    assert {v["clasificacion"] for v in data["variantes"]} == {
        "patogenica",
        "benigna",
        "inocua",
        "vus",
    }
    assert all(isinstance(v["variante_id"], int) for v in data["variantes"])

    en_bd = session.scalars(select(Variante).where(Variante.gen_id == gen_gaa.id)).all()
    assert len(en_bd) == 4
    session.refresh(estudio)
    assert estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO


def test_tc02_reclasificacion_variante_existente_sin_duplicar(app, client, session, datos_escenario_24):
    """TC-02: Upsert actualiza clasificacion y clinvar_id sin duplicar (gen_id, notacion)."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    existente = Variante(
        gen_id=gen_gaa.id,
        notacion="c.1551+5G>A",
        clinvar_id="VCV000451822",
        clasificacion=ClasificacionVariante.VUS,
    )
    session.add(existente)
    session.commit()
    variante_id_original = existente.id

    class _ApigenReclasificado:
        def obtener_variantes(self, simbolo: str):
            return [
                {"notacion": "c.1551+5G>A", "clinvar_id": "VCV000999999", "clasificacion": "patogenica"},
            ]

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenReclasificado()
    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_1"]),
    )

    assert resp.status_code == 200
    variantes = resp.get_json()["data"]["variantes"]
    assert len(variantes) == 1
    assert variantes[0]["variante_id"] == variante_id_original
    assert variantes[0]["clasificacion"] == "patogenica"
    assert variantes[0]["clinvar_id"] == "VCV000999999"

    filas = session.scalars(select(Variante).where(Variante.gen_id == gen_gaa.id)).all()
    assert len(filas) == 1
    assert filas[0].clasificacion == ClasificacionVariante.PATOGENICA


def test_tc03_gen_no_perteneciente_al_estudio_y_reanalisis_restringido(
    app, client, session, datos_escenario_24
):
    """TC-03: 422 si el gen no pertenece al analisis activo (incluyendo reanalisis restringido)."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]
    gen_gla = datos_escenario_24["gen_gla"]
    gen_reanalisis = datos_escenario_24["gen_reanalisis"]
    headers = _headers_para(app, datos_escenario_24["u_bio_1"])

    resp_422 = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gla.id}/variantes",
        headers=headers,
    )
    assert resp_422.status_code == 422
    body_422 = resp_422.get_json()
    assert body_422["ok"] is False
    assert body_422["code"] == "GEN_NO_SOLICITADO_EN_ESTUDIO"
    assert body_422["retryable"] is False

    # Cerrar analisis inicial con resultado y abrir reanalisis solo para gen_reanalisis
    session.add(
        Resultado(
            analisis_id=datos_escenario_24["analisis"].id,
            positivo=False,
            diagnostico=ConclusionDiagnostica.NEGATIVO,
            pdf_path="storage/resultados/test.pdf",
            generado_en=datetime.now(),
        )
    )
    reanalisis = Analisis(
        estudio_id=estudio.id,
        tipo=TipoAnalisis.REANALISIS,
        bioinformatico_id=datos_escenario_24["u_bio_1"].id,
    )
    session.add(reanalisis)
    session.flush()
    session.add(AnalisisGen(analisis_id=reanalisis.id, gen_id=gen_reanalisis.id))
    session.commit()

    # En el reanalisis, gen_gaa (solo del analisis inicial) queda fuera -> 422
    resp_viejo = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=headers,
    )
    assert resp_viejo.status_code == 422
    assert resp_viejo.get_json()["code"] == "GEN_NO_SOLICITADO_EN_ESTUDIO"

    # gen_reanalisis si esta habilitado en el reanalisis activo -> 200
    class _ApigenReanalisis:
        def obtener_variantes(self, simbolo: str):
            assert simbolo == "GBA"
            return [{"notacion": "c.1226A>G", "clinvar_id": "VCV000004290", "clasificacion": "patogenica"}]

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenReanalisis()
    resp_ok = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_reanalisis.id}/variantes",
        headers=headers,
    )
    assert resp_ok.status_code == 200
    assert resp_ok.get_json()["data"]["gen"]["simbolo"] == "GBA"


@pytest.mark.parametrize(
    "estado_invalido",
    [
        EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        EstadoEstudio.RESULTADO_CARGADO,
        EstadoEstudio.CREADO,
    ],
)
def test_tc04_estudio_en_estado_invalido(app, client, session, datos_escenario_24, estado_invalido):
    """TC-04: Retorna 409 ESTADO_ESTUDIO_INVALIDO_PARA_ANALISIS si no esta en EN_ANALISIS_BIOINFORMATICO."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]
    estudio.estado = estado_invalido
    session.commit()

    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_1"]),
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["ok"] is False
    assert body["code"] == "ESTADO_ESTUDIO_INVALIDO_PARA_ANALISIS"


@pytest.mark.parametrize("clave_usuario", ["u_medico", "u_admin"])
def test_tc05_usuario_con_rol_distinto_de_bioinformatico(app, client, datos_escenario_24, clave_usuario):
    """TC-05: Retorna 403 SOLO_BIOINFORMATICO para roles no autorizados y 403 si otro bioinformatico."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24[clave_usuario]),
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "SOLO_BIOINFORMATICO"


def test_tc05b_estudio_asignado_a_otro_o_sin_asignar(app, client, session, datos_escenario_24):
    """Otro bioinformatico o estudio sin bioinformatico asignado en analisis activo recibe 403."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_2"]),
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "ESTUDIO_ASIGNADO_A_OTRO_BIOINFORMATICO"

    datos_escenario_24["analisis"].bioinformatico_id = None
    session.commit()
    resp_sin_asignar = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_1"]),
    )
    assert resp_sin_asignar.status_code == 403
    assert resp_sin_asignar.get_json()["code"] == "ESTUDIO_ASIGNADO_A_OTRO_BIOINFORMATICO"


def test_tc06_fallback_cache_local_con_reintentos_y_backoff(
    app, client, session, datos_escenario_24, monkeypatch
):
    """TC-06: Ante 3 fallos transitorios (backoff 0.5s, 1.0s), sirve cache local con 200."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    v_cache = Variante(
        gen_id=gen_gaa.id,
        notacion="c.1935C>A",
        clinvar_id="VCV000004031",
        clasificacion=ClasificacionVariante.PATOGENICA,
    )
    session.add(v_cache)
    session.commit()

    esperas: list[float] = []
    monkeypatch.setattr(
        "src.core.services.bioinformatica_service.time.sleep",
        lambda s: esperas.append(s),
    )

    class _ApigenTimeout:
        def __init__(self):
            self.intentos = 0

        def obtener_variantes(self, simbolo: str):
            self.intentos += 1
            raise ClienteConexionError("Timeout upstream")

    caido = _ApigenTimeout()
    app.config["BIOINFORMATICA_CLIENT"] = caido

    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_1"]),
    )
    assert resp.status_code == 200
    assert caido.intentos == 3
    assert esperas == [0.5, 1.0]
    data = resp.get_json()["data"]
    assert data["fuente"] == "cache_local_contingencia"
    assert len(data["variantes"]) == 1
    assert data["variantes"][0]["variante_id"] == v_cache.id
    assert data["variantes"][0]["notacion"] == "c.1935C>A"


def test_tc07_fallo_total_sin_cache_local_retorna_503(
    app, client, datos_escenario_24, monkeypatch
):
    """TC-07: Ante 3 fallos 5xx/timeout sin cache local, retorna 503 API_BIOINFORMATICA_NO_DISPONIBLE."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    monkeypatch.setattr("src.core.services.bioinformatica_service.time.sleep", lambda _s: None)

    class _Apigen503:
        def __init__(self):
            self.intentos = 0

        def obtener_variantes(self, simbolo: str):
            self.intentos += 1
            raise ClienteServicioError("503 upstream", codigo_http=503)

    caido = _Apigen503()
    app.config["BIOINFORMATICA_CLIENT"] = caido

    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_1"]),
    )
    assert resp.status_code == 503
    assert caido.intentos == 3
    body = resp.get_json()
    assert body["ok"] is False
    assert body["code"] == "API_BIOINFORMATICA_NO_DISPONIBLE"
    assert body["retryable"] is True


def test_not_found_estudio_o_gen_inexistente(app, client, datos_escenario_24):
    """STEP 1 FAILURE(not_found): 404 ESTUDIO_O_GEN_NO_ENCONTRADO si falta estudio o gen."""
    headers = _headers_para(app, datos_escenario_24["u_bio_1"])
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    r_est = client.get(f"/api/v1/estudios/99999/genes/{gen_gaa.id}/variantes", headers=headers)
    assert r_est.status_code == 404
    assert r_est.get_json()["code"] == "ESTUDIO_O_GEN_NO_ENCONTRADO"

    r_gen = client.get(f"/api/v1/estudios/{estudio.id}/genes/99999/variantes", headers=headers)
    assert r_gen.status_code == 404
    assert r_gen.get_json()["code"] == "ESTUDIO_O_GEN_NO_ENCONTRADO"


@pytest.mark.parametrize(
    "payload_invalido",
    [
        "texto-invalido",
        {"ok": False, "error": "gen desconocido"},
        [{"notacion": "c.1935C>A", "clasificacion": "clasificacion_inexistente"}],
        [{"clasificacion": "patogenica"}],
    ],
)
def test_api_bioinformatica_404_y_payload_malformado_retorna_502(
    app, client, datos_escenario_24, payload_invalido
):
    """STEP 2 FAILURE(permanent_external_error): 404 o payload/clasificacion invalida -> 502."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]
    headers = _headers_para(app, datos_escenario_24["u_bio_1"])

    class _ApigenMalformado:
        def obtener_variantes(self, simbolo: str):
            return payload_invalido

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenMalformado()
    resp = client.get(f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes", headers=headers)
    assert resp.status_code == 502
    assert resp.get_json()["code"] == "RESPUESTA_INVALIDA_API_BIOINFORMATICA"


def test_apigen_probablemente_patogenica_mapea_a_vus(app, client, datos_escenario_24):
    """Apigen real devuelve 'probablemente_patogenica'; debe sincronizarse como 'vus' sin 502."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    class _ApigenReal:
        def obtener_variantes(self, simbolo: str):
            return [
                {"id": "GAA:c.-32-1G>C", "hgvs_c": "c.-32-1G>C", "clasificacion": "probablemente_patogenica"},
            ]

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenReal()
    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_1"]),
    )
    assert resp.status_code == 200
    variantes = resp.get_json()["data"]["variantes"]
    assert len(variantes) == 1
    assert variantes[0]["notacion"] == "c.-32-1G>C"
    assert variantes[0]["clasificacion"] == "vus"


def test_apigen_client_404_mapea_a_502_sin_filtrar_detalle_interno(app, client, datos_escenario_24):
    """HTTP 404 real desde ApigenClient se traduce a 502 sin exponer detalles internos de upstream."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "detalle_interno_supabase_secret"})

    app.config["BIOINFORMATICA_CLIENT"] = ApigenClient(
        api_key="test",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )
    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_1"]),
    )
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["code"] == "RESPUESTA_INVALIDA_API_BIOINFORMATICA"
    assert "detalle_interno_supabase_secret" not in body["error"]


def test_filtros_paginacion_en_cache_validaciones_400_y_dedup_larga(
    app, client, session, datos_escenario_24, monkeypatch
):
    """Valida dedup tras truncar a 120 chars, filtros/paginacion en cache y errores 400."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]
    headers = _headers_para(app, datos_escenario_24["u_bio_1"])

    # Dos notaciones >120 chars con mismo prefijo no deben duplicar filas
    prefijo = "c." + ("A" * 120)
    class _ApigenLargas:
        def obtener_variantes(self, simbolo: str):
            return [
                {"notacion": prefijo + "1", "clinvar_id": "VCV1", "clasificacion": "patogenica"},
                {"notacion": prefijo + "2", "clinvar_id": "VCV2", "clasificacion": "benigna"},
            ]

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenLargas()
    resp_dedup = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=headers,
    )
    assert resp_dedup.status_code == 200
    assert len(resp_dedup.get_json()["data"]["variantes"]) == 1

    # Validaciones 400 de filtros/paginacion
    r_bad_clas = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes?clasificacion=invalida",
        headers=headers,
    )
    assert r_bad_clas.status_code == 400
    assert r_bad_clas.get_json()["code"] == "CLASIFICACION_INVALIDA"

    r_bad_pag = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes?limite=0",
        headers=headers,
    )
    assert r_bad_pag.status_code == 400
    assert r_bad_pag.get_json()["code"] == "PAGINACION_INVALIDA"

    # Paginacion respetada en fallback de cache local
    session.add_all(
        [
            Variante(gen_id=gen_gaa.id, notacion="c.100A>G", clinvar_id="VCV10", clasificacion=ClasificacionVariante.VUS),
            Variante(gen_id=gen_gaa.id, notacion="c.200A>G", clinvar_id="VCV20", clasificacion=ClasificacionVariante.VUS),
            Variante(gen_id=gen_gaa.id, notacion="c.300A>G", clinvar_id="VCV30", clasificacion=ClasificacionVariante.VUS),
        ]
    )
    session.commit()

    class _ApigenCaido:
        def obtener_variantes(self, *_args, **_kwargs):
            raise ClienteConexionError("Timeout")

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenCaido()
    monkeypatch.setattr("src.core.services.bioinformatica_service.time.sleep", lambda _s: None)

    resp_pag = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes?clasificacion=vus&limite=1&offset=1",
        headers=headers,
    )
    assert resp_pag.status_code == 200
    variantes_pag = resp_pag.get_json()["data"]["variantes"]
    assert len(variantes_pag) == 1
    assert variantes_pag[0]["notacion"] == "c.200A>G"


def test_step1_error_bd_retorna_json_504_retryable(app, client, datos_escenario_24, monkeypatch):
    """STEP 1 FAILURE(timeout/BD): Error de BD devuelve JSON 504 reintentable (no HTML 500)."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]

    def _fallar_consulta(*_args, **_kwargs):
        raise SQLAlchemyError("Timeout leyendo PostgreSQL")

    monkeypatch.setattr(bioinformatica_repo, "buscar_estudio_por_id", _fallar_consulta)
    resp = client.get(
        f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes",
        headers=_headers_para(app, datos_escenario_24["u_bio_1"]),
    )
    monkeypatch.undo()

    assert resp.status_code == 504
    body = resp.get_json()
    assert body["ok"] is False
    assert body["retryable"] is True


def test_step3_colision_concurrencia_y_abort_cleanup_bd(
    app, client, session, datos_escenario_24, monkeypatch
):
    """STEP 3: Recupera ante IntegrityError concurrente (200) y hace ROLLBACK + 503 ante error de BD."""
    estudio = datos_escenario_24["estudio"]
    gen_gaa = datos_escenario_24["gen_gaa"]
    headers = _headers_para(app, datos_escenario_24["u_bio_1"])

    class _ApigenOk:
        def obtener_variantes(self, simbolo: str):
            return [{"notacion": "c.1935C>A", "clinvar_id": "VCV000004031", "clasificacion": "patogenica"}]

    app.config["BIOINFORMATICA_CLIENT"] = _ApigenOk()

    # Simular IntegrityError en el primer commit (colision concurrente)
    commit_original = db.session.commit
    llamadas = {"n": 0}

    def _commit_con_colision():
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))
        return commit_original()

    monkeypatch.setattr(db.session, "commit", _commit_con_colision)
    resp_ok = client.get(f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes", headers=headers)
    monkeypatch.undo()

    assert resp_ok.status_code == 200
    assert len(resp_ok.get_json()["data"]["variantes"]) == 1

    # Simular error persistente de BD -> ABORT_CLEANUP (rollback) y 503
    def _fallar_sync(_gen_id, _items):
        raise SQLAlchemyError("Fallo de conexion a PostgreSQL")

    monkeypatch.setattr(bioinformatica_repo, "sincronizar_variantes_gen", _fallar_sync)
    resp_503 = client.get(f"/api/v1/estudios/{estudio.id}/genes/{gen_gaa.id}/variantes", headers=headers)
    monkeypatch.undo()

    assert resp_503.status_code == 503
    assert resp_503.get_json()["retryable"] is True
