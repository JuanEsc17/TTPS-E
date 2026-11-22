"""Tests unitarios para la capa de clientes de APIs externas."""
import base64
import json
from datetime import date, datetime

import httpx
import pytest
from src.clients import (
    PARENTESCOS_MAP,
    PARENTESCOS_POR_NOMBRE,
    ApigenClient,
    BioinformaticaClient,
    CdssClient,
    ChatbotClient,
    ClienteAutenticacionError,
    ClienteConexionError,
    ClienteServicioError,
    ClienteValidacionError,
    CuponesClient,
    EmailClient,
    FamiliogramaClient,
    FedexClient,
    ObraSocialClient,
    OptimizacionClient,
    SnomedClient,
)

# ==========================================
# 1. Tests FamiliogramaClient
# ==========================================

def test_familiograma_catalogos_estaticos():
    """Verifica que el catalogo estatico de parentescos contenga los 16 items del LEL/API."""
    assert len(PARENTESCOS_MAP) == 16
    assert PARENTESCOS_MAP[0] == "paciente"
    assert PARENTESCOS_MAP[1] == "progenitor"
    assert PARENTESCOS_POR_NOMBRE["paciente"] == 0
    assert PARENTESCOS_POR_NOMBRE["padre"] == 1
    assert PARENTESCOS_POR_NOMBRE["madre"] == 1


def test_familiograma_salud_exitoso():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/functions/v1/familiograma/salud"
        return httpx.Response(200, json={"estado": "disponible"})

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    fam_client = FamiliogramaClient(client=client_mock)

    res = fam_client.verificar_salud()
    assert res == {"estado": "disponible"}


def test_familiograma_obtener_parentescos_exitoso():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/functions/v1/familiograma/parentescos"
        assert request.headers.get("x-api-key") == "clave_test"
        return httpx.Response(
            200,
            json=[{"id": 0, "parentesco": "paciente"}, {"id": 1, "parentesco": "progenitor"}],
        )

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    fam_client = FamiliogramaClient(api_key="clave_test", client=client_mock)

    items = fam_client.obtener_parentescos()
    assert len(items) == 2
    assert items[0]["parentesco"] == "paciente"


def test_familiograma_generar_y_guardar_svg(tmp_path):
    svg_dummy = "<svg><circle cx='50' cy='50' r='40'/></svg>"
    b64_dummy = base64.b64encode(svg_dummy.encode("utf-8")).decode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-api-key") == "clave_test"
        body = json.loads(request.content)
        assert len(body["personas"]) == 2
        assert body["personas"][0]["parentesco"] == 0
        return httpx.Response(
            200,
            json={
                "advertencias": [],
                "imagen": {"tipo": "image/svg+xml", "base64": b64_dummy},
            },
        )

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    fam_client = FamiliogramaClient(api_key="clave_test", client=client_mock)

    personas = [
        {"parentesco": 0, "nombre": "Juan", "apellido": "Perez"},
        {"parentesco": 1, "nombre": "Carlos", "apellido": "Perez"},
    ]
    resp = fam_client.generar_familiograma(personas)
    assert resp["imagen"]["tipo"] == "image/svg+xml"

    # Decodificar y guardar
    svg_texto = fam_client.decodificar_svg(resp["imagen"]["base64"])
    assert svg_texto == svg_dummy

    archivo_svg = tmp_path / "familiograma.svg"
    fam_client.guardar_svg(resp["imagen"]["base64"], archivo_svg)
    assert archivo_svg.exists()
    assert archivo_svg.read_text(encoding="utf-8") == svg_dummy


def test_familiograma_error_autenticacion():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"mensaje": "Credenciales invalidas"}})

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    fam_client = FamiliogramaClient(client=client_mock)

    with pytest.raises(ClienteAutenticacionError) as exc_info:
        fam_client.obtener_parentescos()
    assert exc_info.value.codigo_http == 401


def test_familiograma_error_validacion_422():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": {"mensaje": "Falta persona con codigo 0"}})

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    fam_client = FamiliogramaClient(client=client_mock)

    with pytest.raises(ClienteValidacionError) as exc_info:
        fam_client.generar_familiograma([{"parentesco": 1, "nombre": "Papa", "apellido": "Perez"}])
    assert exc_info.value.codigo_http == 422


# ==========================================
# 2. Tests EmailClient
# ==========================================

def test_email_verificar_conexion():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/functions/v1/avisos"
        assert request.headers.get("X-API-Key") == "avs_123"
        return httpx.Response(200, json={"mensaje": "Autenticación exitosa", "sistema": {"nombre": "grupo01"}})

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    email_client = EmailClient(api_key="avs_123", client=client_mock)

    res = email_client.verificar_conexion()
    assert res["mensaje"] == "Autenticación exitosa"
    assert res["sistema"]["nombre"] == "grupo01"


def test_email_enviar_aviso_202_accepted():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Idempotency-Key") == "idem-key-1"
        body = json.loads(request.content)
        assert body["asunto"] == "Resultado de exoma"
        assert body["destinatarios"] == [{"canal": "email", "destino": "paciente@mail.com"}]
        return httpx.Response(202, json={"id": "uuid-1234", "estado": "pendiente", "creado": True})

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    email_client = EmailClient(api_key="avs_123", client=client_mock)

    res = email_client.enviar_aviso(
        asunto="Resultado de exoma",
        mensaje="Estimado paciente, su resultado ya esta disponible.",
        destinatarios=["paciente@mail.com"],
        referencia="EC-001",
        idempotency_key="idem-key-1",
    )
    assert res["id"] == "uuid-1234"
    assert res["estado"] == "pendiente"
    assert res["creado"] is True


def test_email_consultar_estado():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/functions/v1/avisos/uuid-1234"
        return httpx.Response(
            200,
            json={
                "id": "uuid-1234",
                "asunto": "Resultado de exoma",
                "estado": "enviado",
                "envios": [{"destino": "paciente@mail.com", "estado": "enviado"}],
            },
        )

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    email_client = EmailClient(api_key="avs_123", client=client_mock)

    res = email_client.consultar_estado("uuid-1234")
    assert res["estado"] == "enviado"
    assert len(res["envios"]) == 1


def test_email_error_idempotencia_409():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"error": "Idempotency-Key utilizada con otro contenido"})

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    email_client = EmailClient(api_key="avs_123", client=client_mock)

    with pytest.raises(ClienteValidacionError) as exc_info:
        email_client.enviar_aviso(
            asunto="Otro asunto",
            mensaje="Mensaje",
            destinatarios=["otro@mail.com"],
            idempotency_key="idem-key-1",
        )
    assert exc_info.value.codigo_http == 409


# ==========================================
# 3. Tests OptimizacionClient
# ==========================================

def test_optimizacion_recorrido_exitoso():
    coords_entrada = [
        {"lat": -34.6037, "lon": -58.3816},
        {"lat": -34.5700, "lon": -58.4300},
        {"lat": -34.5900, "lon": -58.3900},
        {"lat": -34.5450, "lon": -58.4500},
    ]
    coords_ordenadas = [
        {"lat": -34.6037, "lon": -58.3816},
        {"lat": -34.5900, "lon": -58.3900},
        {"lat": -34.5700, "lon": -58.4300},
        {"lat": -34.5450, "lon": -58.4500},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/optimizacion"
        body = json.loads(request.content)
        assert len(body["coordenadas"]) == 4
        return httpx.Response(200, json={"coordenadas": coords_ordenadas})

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    opt_client = OptimizacionClient(client=client_mock)

    res = opt_client.optimizar_recorrido(coords_entrada)
    assert res == coords_ordenadas
    # Comprobar que primer y ultimo punto quedan fijos
    assert res[0] == coords_entrada[0]
    assert res[-1] == coords_entrada[-1]


def test_optimizacion_menos_de_dos_coordenadas_falla_local():
    opt_client = OptimizacionClient()
    with pytest.raises(ClienteValidacionError) as exc_info:
        opt_client.optimizar_recorrido([{"lat": -34.6037, "lon": -58.3816}])
    assert "al menos 2 coordenadas" in exc_info.value.mensaje


# ==========================================
# 4. Tests SnomedClient
# ==========================================

def test_snomed_buscar_sintomas_exitoso():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/functions/v1/terminologia/sintomas"
        assert request.url.params["q"] == "fiebre"
        assert request.url.params["limite"] == "5"
        assert request.headers.get("X-API-Key") == "snomed_key_1"
        assert request.headers.get("x-region") == "us-east-1"
        return httpx.Response(
            200,
            json={
                "resultados": [
                    {
                        "sctid": 386661006,
                        "termino_preferido": "fiebre",
                        "estrategia": "exacta",
                    }
                ]
            },
        )

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    snomed_client = SnomedClient(api_key="snomed_key_1", client=client_mock)

    res = snomed_client.buscar_sintomas("fiebre", limite=5)
    assert len(res) == 1
    assert res[0]["sctid"] == "386661006"
    assert res[0]["termino_preferido"] == "fiebre"


def test_snomed_validacion_local_texto_corto_y_limite():
    snomed_client = SnomedClient(api_key="snomed_key_1")
    with pytest.raises(ClienteValidacionError):
        snomed_client.buscar_sintomas("ab")
    with pytest.raises(ClienteValidacionError):
        snomed_client.buscar_sintomas("fiebre", limite=0)
    with pytest.raises(ClienteValidacionError):
        snomed_client.buscar_sintomas("fiebre", limite=51)


def test_snomed_error_400_detalle():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detalle": "Parametro q invalido"})

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    snomed_client = SnomedClient(api_key="snomed_key_1", client=client_mock)

    with pytest.raises(ClienteValidacionError) as exc_info:
        snomed_client.buscar_sintomas("abc")
    assert exc_info.value.codigo_http == 400
    assert "Parametro q invalido" in exc_info.value.mensaje


# ==========================================
# 5. Tests ApigenClient (Bioinformatica)
# ==========================================

def test_apigen_alias_bioinformatica():
    assert BioinformaticaClient is ApigenClient


def test_apigen_buscar_genes_y_variantes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("apikey") == "sb_test"
        if request.url.path == "/rest/v1/gen":
            assert request.url.params["simbolo"] == "ilike.GA*"
            return httpx.Response(200, json=[{"simbolo": "GAA"}, {"simbolo": "GAB1"}])
        if request.url.path == "/rest/v1/variantes":
            assert request.url.params["gen"] == "eq.GAA"
            assert request.headers.get("Prefer") == "count=exact"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "GAA:c.-32-13T>G",
                        "hgvs_c": "c.-32-13T>G",
                        "proteina": None,
                        "clasificacion": "patogenica",
                    }
                ],
            )
        return httpx.Response(404)

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    apigen = ApigenClient(api_key="sb_test", client=client_mock)

    genes = apigen.buscar_genes("GA")
    assert [g["simbolo"] for g in genes] == ["GAA", "GAB1"]

    variantes = apigen.obtener_variantes("GAA")
    assert len(variantes) == 1
    assert variantes[0]["id"] == "GAA:c.-32-13T>G"


def test_apigen_rpcs_diagnostico_y_alta_patologia():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if request.url.path == "/rest/v1/rpc/genes_por_patologia":
            assert body["p_patologia"] == "POMPE"
            return httpx.Response(200, json=["GAA"])
        if request.url.path == "/rest/v1/rpc/confirma_diagnostico":
            return httpx.Response(200, json=True)
        if request.url.path == "/rest/v1/rpc/resultado_diagnostico":
            return httpx.Response(200, json="portador")
        if request.url.path == "/rest/v1/rpc/hallazgos_secundarios":
            assert body["p_excluir_patologias"] == ["POMPE"]
            return httpx.Response(
                200,
                json=[{"variante": "BRCA2:c.5946del", "gen": "BRCA2", "clasificacion": "patogenica"}],
            )
        if request.url.path == "/rest/v1/rpc/alta_patologia":
            assert body["p_codigo"] == "MPS3A"
            return httpx.Response(
                200,
                json=[{"codigo": "MPS3A", "nombre": body["p_nombre"], "genes": ["SGSH"]}],
            )
        return httpx.Response(404)

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    apigen = ApigenClient(api_key="sb_test", grupo_id="grupo1", client=client_mock)

    assert apigen.obtener_genes_por_patologia("POMPE") == ["GAA"]
    assert apigen.confirmar_diagnostico("POMPE", ["c.-32-13T>G", "c.525del"]) is True
    assert apigen.obtener_resultado_diagnostico("POMPE", ["GAA:c.-32-13T>G"]) == "portador"
    hallazgos = apigen.obtener_hallazgos_secundarios(
        ["BRCA2:c.5946del", "GAA:c.-32-13T>G"], excluir_patologias=["POMPE"]
    )
    assert hallazgos[0]["gen"] == "BRCA2"
    alta = apigen.registrar_patologia("MPS3A", "Mucopolisacaridosis 3A", ["SGSH"], "autosomica_recesiva")
    assert alta[0]["codigo"] == "MPS3A"


def test_apigen_error_400_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "Variante inexistente: GAA:c.99999A>G"})

    client_mock = httpx.Client(transport=httpx.MockTransport(handler))
    apigen = ApigenClient(api_key="sb_test", client=client_mock)

    with pytest.raises(ClienteValidacionError) as exc_info:
        apigen.obtener_resultado_diagnostico("POMPE", ["GAA:c.99999A>G"])
    assert exc_info.value.codigo_http == 400
    assert "Variante inexistente" in exc_info.value.mensaje



# ==========================================
# 6. Tests CdssClient
# ==========================================

def test_cdss_flujo_completo():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            assert "X-API-Key" not in request.headers
            return httpx.Response(200, json={"status": "ok", "db": "ok"})
        assert request.headers.get("X-API-Key") == "cdss_key"
        if request.url.path == "/api/v1/patologias":
            return httpx.Response(200, json=[{"codigo": "FABRY", "nombre": "Enfermedad de Fabry"}])
        if request.url.path == "/api/v1/estrategias":
            return httpx.Response(200, json=["MAYOR_CANTIDAD_SINTOMAS", "MENOR_DIFERENCIA"])
        if request.url.path == "/api/v1/diagnostico":
            body = json.loads(request.content)
            assert body == {"sintomas": ["247398009", "29738008"]}
            return httpx.Response(
                200,
                json={"compatible": True, "estrategia": "MENOR_DIFERENCIA", "patologias": ["GAUCHER"]},
            )
        if request.url.path == "/api/v1/configuracion":
            return httpx.Response(200, json={"cliente": "Grupo 1", "estrategia": "MENOR_DIFERENCIA"})
        if request.url.path == "/api/v1/configuracion/estrategia":
            assert request.method == "PUT"
            assert json.loads(request.content) == {"estrategia": "MENOR_DIFERENCIA"}
            return httpx.Response(200, json={"cliente": "Grupo 1", "estrategia": "MENOR_DIFERENCIA"})
        return httpx.Response(404)

    cdss = CdssClient(api_key="cdss_key", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert cdss.verificar_salud() == {"status": "ok", "db": "ok"}
    assert cdss.listar_patologias()[0]["codigo"] == "FABRY"
    assert "MENOR_DIFERENCIA" in cdss.listar_estrategias()
    assert cdss.sugerir_diagnostico(["247398009", "29738008"])["compatible"] is True
    assert cdss.obtener_configuracion()["cliente"] == "Grupo 1"
    assert cdss.actualizar_estrategia("MENOR_DIFERENCIA")["estrategia"] == "MENOR_DIFERENCIA"


def test_cdss_validacion_y_errores():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/patologias":
            return httpx.Response(401, json={"detail": "API key invalida", "código": "API_KEY_INVALIDA"})
        return httpx.Response(503, json={"detail": "DB sin conexion", "código": "SERVICIO_NO_DISPONIBLE"})

    cdss = CdssClient(api_key="bad", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ClienteValidacionError):
        cdss.sugerir_diagnostico([])
    with pytest.raises(ClienteAutenticacionError) as exc_401:
        cdss.listar_patologias()
    assert exc_401.value.codigo_http == 401
    with pytest.raises(ClienteServicioError) as exc_503:
        cdss.verificar_salud()
    assert exc_503.value.codigo_http == 503


# ==========================================
# 7. Tests ChatbotClient
# ==========================================

def test_chatbot_estado_y_mensaje():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert "x-chatbot-token" not in request.headers
            return httpx.Response(200, json={"estado": "ok"})
        assert request.headers.get("apikey") == "pub_key"
        assert request.headers.get("x-chatbot-token") == "tok_grupo"
        body = json.loads(request.content)
        assert body == {"mensaje": "¿Qué es un exoma clínico?", "conversacion_id": None}
        return httpx.Response(
            200,
            json={
                "respuesta": "El exoma es...",
                "conversacion_id": "conv-1",
                "tipo": "respuesta",
            },
        )

    bot = ChatbotClient(
        apikey="pub_key",
        token="tok_grupo",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert bot.verificar_estado() == {"estado": "ok"}
    res = bot.enviar_mensaje("  ¿Qué es un exoma clínico?  ")
    assert res["tipo"] == "respuesta"
    assert res["conversacion_id"] == "conv-1"


def test_chatbot_validacion_reintento_429_y_errores():
    intentos = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal intentos
        intentos += 1
        if intentos == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"detail": "Rate limit"})
        return httpx.Response(
            200,
            json={"respuesta": "Ok tras espera", "conversacion_id": "c2", "tipo": "respuesta"},
        )

    bot = ChatbotClient(
        apikey="pub",
        token="tok",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ClienteValidacionError):
        bot.enviar_mensaje("   ")
    with pytest.raises(ClienteValidacionError):
        bot.enviar_mensaje("x" * 1001)

    res = bot.enviar_mensaje("Hola")
    assert intentos == 2
    assert res["respuesta"] == "Ok tras espera"


# ==========================================
# 8. Tests CuponesClient
# ==========================================

def test_cupones_flujo_completo():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-API-Key") == "ecg_test"
        assert "Authorization" not in request.headers
        if request.url.path == "/functions/v1/cupones-api/cupones":
            assert request.url.params["estado"] == "disponible"
            return httpx.Response(200, json={"items": [], "total": 0, "limit": 20, "offset": 0})
        if request.url.path == "/functions/v1/cupones-api/generar_cupones_gerencia":
            body = json.loads(request.content)
            assert body == {"p_gerente_id": "G-1", "p_cantidad": 1, "p_porcentaje_descuento": 20}
            return httpx.Response(200, json=[{"codigo_cupon": "53399388", "porcentaje": 20}])
        if request.url.path == "/functions/v1/cupones-api/asignar_cupon_a_medico":
            return httpx.Response(200, json=True)
        if request.url.path == "/functions/v1/cupones-api/asignar_cupon_a_paciente":
            return httpx.Response(200, json=True)
        if request.url.path == "/functions/v1/cupones-api/canjear_cupon":
            return httpx.Response(200, json=True)
        return httpx.Response(404)

    cup = CuponesClient(api_key="ecg_test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert cup.listar_cupones(estado="disponible")["total"] == 0
    lote = cup.generar_cupones_gerencia("G-1", 1, 20)
    assert lote[0]["codigo_cupon"] == "53399388"
    assert cup.asignar_cupon_a_medico("G-1", "M-1", "53399388") is True
    assert cup.asignar_cupon_a_paciente("M-1", "P-1", "53399388") is True
    assert cup.canjear_cupon("P-1", "53399388") is True


def test_cupones_errores_403_y_409():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generar_cupones_gerencia"):
            return httpx.Response(403, json={"code": "OTRO_GERENTE", "message": "Ya existe gerente"})
        return httpx.Response(409, json={"code": "YA_USADO", "message": "Cupon ya canjeado"})

    cup = CuponesClient(api_key="ecg_test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ClienteValidacionError) as exc_403:
        cup.generar_cupones_gerencia("G-2", 1, 10)
    assert exc_403.value.codigo_http == 403
    with pytest.raises(ClienteValidacionError) as exc_409:
        cup.canjear_cupon("P-1", "53399388")
    assert exc_409.value.codigo_http == 409


# ==========================================
# 9. Tests FedexClient
# ==========================================

def test_fedex_flujo_completo():
    expected_auth = "Basic " + base64.b64encode(b"grupo01:secreto").decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/functions/v1/fedex/retiros" and request.method == "POST":
            assert request.headers.get("Authorization") == expected_auth
            body = json.loads(request.content)
            assert body == {"lugar": "La Plata", "fecha_programada": "2026-12-15T15:00:00"}
            return httpx.Response(
                201,
                json={"mensaje": "OK", "retiro": {"id": "uuid-1", "lugar": "La Plata"}},
            )
        if request.url.path == "/functions/v1/fedex/retiros" and request.method == "GET":
            assert request.headers.get("Authorization") == expected_auth
            assert request.url.params["pagina"] == "1"
            return httpx.Response(200, json={"pagina": 1, "limite": 10, "total": 1, "retiros": []})
        if request.url.path == "/functions/v1/fedex/retiros/uuid-1":
            assert "Authorization" not in request.headers
            return httpx.Response(200, json={"id": "uuid-1", "estado": "PROGRAMADO"})
        return httpx.Response(404)

    fedex = FedexClient(
        usuario="grupo01",
        password="secreto",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    creado = fedex.programar_retiro("La Plata", datetime(2026, 12, 15, 15, 0, 0))
    assert creado["retiro"]["id"] == "uuid-1"
    assert fedex.listar_retiros()["total"] == 1
    assert fedex.consultar_retiro("uuid-1")["estado"] == "PROGRAMADO"


def test_fedex_validacion_y_error_red():
    fedex = FedexClient(usuario="grupo01", password="secreto")
    with pytest.raises(ClienteValidacionError):
        fedex.programar_retiro("La Plata", "2026-12-15T15:00:00Z")
    with pytest.raises(ClienteValidacionError):
        fedex.listar_retiros(pagina=0)

    def handler_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    fedex_offline = FedexClient(
        usuario="grupo01",
        password="secreto",
        client=httpx.Client(transport=httpx.MockTransport(handler_error)),
    )
    with pytest.raises(ClienteConexionError):
        fedex_offline.consultar_retiro("uuid-1")


# ==========================================
# 10. Tests ObraSocialClient
# ==========================================

def test_obra_social_flujo_completo(tmp_path):
    pdf_file = tmp_path / "amparo.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 contenido")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/functions/v1/api/":
            assert "x-api-key" not in request.headers
            return httpx.Response(200, json={"servicio": "Obras Sociales", "version": "1.0.0"})
        if request.url.path == "/functions/v1/api/obras-sociales":
            assert request.headers.get("x-api-key") == "osk_test"
            return httpx.Response(200, json={"datos": [{"id": "os-1", "nombre": "OSDE"}], "total": 1})
        if request.url.path == "/functions/v1/api/solicitudes" and request.method == "POST":
            body = json.loads(request.content)
            assert body["fecha"] == "2026-11-13"
            return httpx.Response(
                201,
                json={
                    "id": "sol-1",
                    "estado": "pendiente",
                    "urls_simulacion": {
                        "autorizar": "https://api.test/simulacion/tok-1/autorizar",
                        "rechazar": "https://api.test/simulacion/tok-1/rechazar",
                    },
                },
            )
        if request.url.path == "/functions/v1/api/solicitudes/sol-1/demanda":
            assert "multipart/form-data" in request.headers.get("content-type", "")
            return httpx.Response(201, json={"id": "sol-1", "estado": "demanda_en_curso"})
        if request.url.path == "/simulacion/tok-1/autorizar":
            assert json.loads(request.content) == {"porcentaje": 90}
            return httpx.Response(200, json={"id": "sol-1", "estado": "autorizada"})
        if request.url.path == "/functions/v1/api/simulacion/tok-1/rechazar":
            return httpx.Response(200, json={"id": "sol-1", "estado": "rechazada"})
        return httpx.Response(404)

    os_client = ObraSocialClient(
        api_key="osk_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert os_client.verificar_estado()["version"] == "1.0.0"
    assert os_client.listar_obras_sociales(buscar="osde")["datos"][0]["nombre"] == "OSDE"
    sol = os_client.crear_solicitud("os-1", "Ana Perez", date(2026, 11, 13), "est-1")
    assert sol["estado"] == "pendiente"
    assert os_client.simular_rechazo("tok-1", "Falta documentacion")["estado"] == "rechazada"
    assert os_client.presentar_demanda("sol-1", pdf_file)["estado"] == "demanda_en_curso"
    assert os_client.simular_autorizacion(sol["urls_simulacion"]["autorizar"], 90)["estado"] == "autorizada"


def test_obra_social_errores_y_limite_pdf():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"error": {"codigo": "ESTADO_INVALIDO", "mensaje": "Ya autorizada", "detalle": {}}},
        )

    os_client = ObraSocialClient(
        api_key="osk_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ClienteValidacionError):
        os_client.presentar_demanda("sol-1", b"x" * (5 * 1024 * 1024 + 1))
    with pytest.raises(ClienteValidacionError) as exc_409:
        os_client.presentar_demanda("sol-1", b"%PDF-1.4 ok")
    assert exc_409.value.codigo_http == 409
    assert "Ya autorizada" in exc_409.value.mensaje
