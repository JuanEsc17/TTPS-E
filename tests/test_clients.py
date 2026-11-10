"""Tests unitarios para la capa de clientes de APIs externas (Familiograma, Email, Optimizacion)."""
import base64
import json

import httpx
import pytest
from src.clients import (
    PARENTESCOS_MAP,
    PARENTESCOS_POR_NOMBRE,
    ApigenClient,
    BioinformaticaClient,
    ClienteAutenticacionError,
    ClienteValidacionError,
    EmailClient,
    FamiliogramaClient,
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
