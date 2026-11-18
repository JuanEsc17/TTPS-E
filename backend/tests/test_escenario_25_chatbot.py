"""Tests de aceptacion, contrato, seguridad y rendimiento para Escenario 25: Chatbot sobre patologias."""
import json
import time
from datetime import date

import httpx
import pytest
from sqlalchemy import func, select
from src.clients.chatbot_client import ChatbotClient
from src.core.models import (
    ClasificacionVariante,
    Especialidad,
    Gen,
    Medico,
    Paciente,
    Patologia,
    Rol,
    Usuario,
    Variante,
)
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    SCOPE_CAMBIO_PASSWORD_INICIAL,
    SCOPE_VERIFICAR_DISPOSITIVO,
    emitir_token,
    hashear_password,
)


def _crear_token(
    app,
    session,
    *,
    rol: Rol = Rol.PACIENTE,
    email: str = "paciente.chat@lab.org",
    debe_cambiar_password: bool = False,
    scope: str = SCOPE_ACCESO_COMPLETO,
) -> tuple[Usuario, str]:
    usuario = Usuario(
        email=email,
        password_hash=hashear_password("Clave1234"),
        rol=rol,
        nombre="Lucia",
        apellido="Mendez",
        telefono="1155667788",
        debe_cambiar_password=debe_cambiar_password,
    )
    session.add(usuario)
    session.commit()
    token = emitir_token(
        str(app.config["SECRET_KEY"]),
        usuario_id=usuario.id,
        rol=rol.value,
        scope=scope,
        ttl_segundos=3600,
    )
    return usuario, token


def _crear_perfil_paciente_completo(session, usuario: Usuario) -> tuple[Paciente, Patologia]:
    """Crea un paciente con PII y variantes geneticas para verificar minimizacion de datos (RC-2)."""
    esp = Especialidad(nombre="Genetica Clinica")
    session.add(esp)
    med_user = Usuario(
        email="medico.chat@lab.org",
        password_hash=hashear_password("Clave1234"),
        rol=Rol.MEDICO,
        nombre="Carlos",
        apellido="Vega",
        telefono="1144332211",
        debe_cambiar_password=False,
    )
    session.add(med_user)
    session.flush()
    medico = Medico(usuario_id=med_user.id, matricula="MN-99881")
    session.add(medico)

    patologia = Patologia(nombre="Enfermedad de Fabry", descripcion="Patologia lisosomal X-linked")
    session.add(patologia)
    gen = Gen(simbolo="GLA", nombre="Alfa-galactosidasa A")
    session.add(gen)
    session.flush()
    session.add(
        Variante(
            gen_id=gen.id,
            notacion="c.679C>T",
            clinvar_id="VCV000010",
            clasificacion=ClasificacionVariante.PATOGENICA,
        )
    )

    paciente = Paciente(
        usuario_id=usuario.id,
        medico_id=medico.id,
        dni="38999111",
        fecha_nacimiento=date(1995, 4, 12),
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica="Acroparestesia severa en manos y pies desde la infancia.",
        tipo_sospecha="clinica",
        responsable_nombre="Marta Mendez",
        responsable_dni="18222333",
    )
    session.add(paciente)
    session.commit()
    return paciente, patologia


def test_tc01_happy_path_sin_pii_y_sin_mutacion_bd(app, client, session, monkeypatch):
    usuario, token = _crear_token(app, session)
    paciente, patologia = _crear_perfil_paciente_completo(session, usuario)

    capturas: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers.get("apikey") == "pub-test"
        assert request.headers.get("x-chatbot-token") == "tok-test"
        cuerpo = json.loads(request.content)
        capturas.append(cuerpo)
        return httpx.Response(
            200,
            json={
                "respuesta": (
                    "La enfermedad de Fabry es una patologia lisosomal genetica causada por "
                    "deficiencia de la enzima alfa-galactosidasa A."
                ),
                "conversacion_id": "conv-fabry-01",
                "tipo": "respuesta",
            },
        )

    bot = ChatbotClient(
        base_url="https://chatbot.test/functions/v1/chat",
        apikey="pub-test",
        token="tok-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: bot)

    pregunta = "¿Qué es la enfermedad de Fabry y cuáles son sus síntomas principales?"
    resp = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": f"  {pregunta}  ", "patologia_id": patologia.id},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    data = body["data"]
    assert data["pregunta"] == pregunta
    assert "alfa-galactosidasa A" in data["respuesta"]
    assert "Enfermedad de Fabry" in data["patologias_relacionadas"]
    assert data["respondido_en"].endswith("Z")
    assert data["conversacion_id"] == "conv-fabry-01"
    assert data["tipo"] == "respuesta"

    # Verifica minimizacion de datos (RC-2): cero PII/variantes enviadas al modulo externo
    assert len(capturas) == 1
    payload_enviado = json.dumps(capturas[0])
    assert set(capturas[0].keys()) == {"mensaje", "conversacion_id"}
    for secreto in (
        paciente.dni,
        usuario.email,
        usuario.nombre,
        usuario.apellido,
        usuario.telefono,
        paciente.responsable_dni,
        "c.679C>T",
        "Acroparestesia severa",
    ):
        assert secreto not in payload_enviado

    # Sin mutaciones en BD
    assert session.scalar(select(func.count()).select_from(Usuario)) == 2
    assert session.scalar(select(func.count()).select_from(Paciente)) == 1
    assert session.scalar(select(func.count()).select_from(Patologia)) == 1


@pytest.mark.parametrize("tipo_respuesta", ["respuesta", "fuera_de_alcance", "derivar_medico", "sin_informacion"])
def test_tc01b_continuidad_conversacion_y_tipos_genlab(app, client, session, monkeypatch, tipo_respuesta):
    _, token = _crear_token(app, session)
    pat = Patologia(nombre="Enfermedad de Pompe", descripcion="Glucogenosis tipo II")
    session.add(pat)
    session.commit()

    llamadas: list[dict] = []

    class _BotFake:
        def enviar_mensaje(self, mensaje: str, conversacion_id: str | None = None):
            llamadas.append({"mensaje": mensaje, "conversacion_id": conversacion_id})
            return {
                "respuesta": "Respuesta del asistente sobre herencia.",
                "conversacion_id": conversacion_id or "conv-nueva",
                "tipo": tipo_respuesta,
            }

    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: _BotFake())

    resp = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "pregunta": "¿Cómo se hereda?",
            "patologia_id": pat.id,
            "conversacion_id": "conv-previa-123",
        },
    )

    assert resp.status_code == 200
    assert llamadas == [
        {
            "mensaje": "Sobre Enfermedad de Pompe: ¿Cómo se hereda?",
            "conversacion_id": "conv-previa-123",
        }
    ]
    data = resp.get_json()["data"]
    assert data["pregunta"] == "¿Cómo se hereda?"
    assert data["conversacion_id"] == "conv-previa-123"
    assert data["tipo"] == tipo_respuesta
    assert data["patologias_relacionadas"] == ["Enfermedad de Pompe"]


@pytest.mark.parametrize("payload", [{}, {"pregunta": ""}, {"pregunta": "   "}, {"pregunta": "ab"}])
def test_tc02_pregunta_vacia_o_demasiado_corta_retorna_400(app, client, session, monkeypatch, payload):
    _, token = _crear_token(app, session)
    invocado = False

    def _no_debe_llamarse():
        nonlocal invocado
        invocado = True
        raise AssertionError("No debe invocar ChatbotClient ante pregunta invalida")

    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", _no_debe_llamarse)

    resp = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["ok"] is False
    assert body["code"] == "PREGUNTA_INVALIDA"
    assert body["retryable"] is False
    assert invocado is False


def test_tc03_pregunta_excede_longitud_maxima_y_bordes(app, client, session, monkeypatch):
    _, token = _crear_token(app, session)

    class _BotFake:
        def enviar_mensaje(self, mensaje: str, conversacion_id: str | None = None):
            return {"respuesta": "Respuesta valida.", "conversacion_id": "c-1", "tipo": "respuesta"}

    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: _BotFake())

    # Excede 1000 -> 400
    resp_larga = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "x" * 1001},
    )
    assert resp_larga.status_code == 400
    assert resp_larga.get_json()["code"] == "PREGUNTA_INVALIDA"

    # Bordes exactos: 3 y 1000 -> 200
    for largo in (3, 1000):
        resp_ok = client.post(
            "/api/v1/chatbot/consultas",
            headers={"Authorization": f"Bearer {token}"},
            json={"pregunta": "a" * largo},
        )
        assert resp_ok.status_code == 200


@pytest.mark.parametrize(
    "rol",
    [
        Rol.ADMINISTRATIVO,
        Rol.MEDICO,
        Rol.GERENTE_MEDICO,
        Rol.BIOINFORMATICO,
        Rol.TRANSPORTISTA,
        Rol.ADMIN_GENERAL,
    ],
)
def test_tc04_roles_no_paciente_retornan_403(app, client, session, rol):
    _, token = _crear_token(app, session, rol=rol, email=f"{rol.value}@lab.org")
    resp = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es la enfermedad de Gaucher?"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "ACCESO_CHATBOT_NO_AUTORIZADO"


@pytest.mark.parametrize("scope", [SCOPE_CAMBIO_PASSWORD_INICIAL, SCOPE_ACCESO_COMPLETO])
def test_tc04b_paciente_sin_cambiar_password_inicial_retorna_403(app, client, session, scope):
    _, token = _crear_token(
        app,
        session,
        rol=Rol.PACIENTE,
        email=f"inicial.{scope}@lab.org",
        debe_cambiar_password=True,
        scope=scope,
    )
    resp = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es ASMD?"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "ACCESO_CHATBOT_NO_AUTORIZADO"


def test_tc04c_sin_token_y_dispositivo_no_verificado(app, client, session):
    resp_anon = client.post("/api/v1/chatbot/consultas", json={"pregunta": "¿Qué es ASMD?"})
    assert resp_anon.status_code == 401
    assert resp_anon.get_json()["code"] == "NO_AUTENTICADO"

    _, token_2fa = _crear_token(
        app,
        session,
        email="2fa@lab.org",
        scope=SCOPE_VERIFICAR_DISPOSITIVO,
    )
    resp_2fa = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token_2fa}"},
        json={"pregunta": "¿Qué es ASMD?"},
    )
    assert resp_2fa.status_code == 403
    assert resp_2fa.get_json()["code"] == "DISPOSITIVO_NO_VERIFICADO"


@pytest.mark.parametrize("modo_fallo", ["timeout", "503"])
def test_tc05_fallo_transitorio_recuperado_en_reintento(app, client, session, monkeypatch, modo_fallo):
    _, token = _crear_token(app, session)
    esperas: list[float] = []
    intentos = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal intentos
        intentos += 1
        if intentos == 1:
            if modo_fallo == "timeout":
                raise httpx.ReadTimeout("Timeout en primer intento", request=request)
            return httpx.Response(503, json={"detail": "Servicio ocupado"})
        return httpx.Response(
            200,
            json={"respuesta": "La enfermedad de Gaucher afecta el metabolismo lipidico.", "conversacion_id": "c-r", "tipo": "respuesta"},
        )

    bot = ChatbotClient(
        apikey="pub",
        token="tok",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: bot)
    monkeypatch.setattr("src.core.services.chatbot_service.time.sleep", lambda s: esperas.append(s))

    resp = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es la enfermedad de Gaucher?"},
    )
    assert resp.status_code == 200
    assert intentos == 2
    assert esperas == [1.0]
    assert "Gaucher" in resp.get_json()["data"]["patologias_relacionadas"][0]


def test_tc06_timeout_total_retorna_504_y_cierra_conexion(app, client, session, monkeypatch):
    _, token = _crear_token(app, session)
    esperas: list[float] = []
    cerrado = False
    intentos = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal intentos
        intentos += 1
        raise httpx.ReadTimeout("Upstream timed out", request=request)

    bot = ChatbotClient(
        apikey="pub",
        token="tok",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    # Simula que el cliente gestiona su propia conexion para verificar ABORT_CLEANUP
    bot._owns_client = True
    orig_close = bot.close

    def _spy_close():
        nonlocal cerrado
        cerrado = True
        orig_close()

    monkeypatch.setattr(bot, "close", _spy_close)
    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: bot)
    monkeypatch.setattr("src.core.services.chatbot_service.time.sleep", lambda s: esperas.append(s))

    resp = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es MPS 1?"},
    )
    assert resp.status_code == 504
    body = resp.get_json()
    assert body["ok"] is False
    assert body["code"] == "CHATBOT_TIMEOUT"
    assert body["retryable"] is True
    assert intentos == 2
    assert esperas == [1.0]
    assert cerrado is True


def test_tc06b_indisponibilidad_503_y_errores_externos_422_401(app, client, session, monkeypatch):
    _, token = _crear_token(app, session)
    monkeypatch.setattr("src.core.services.chatbot_service.time.sleep", lambda _s: None)

    # 1) 503 persistente tras reintento -> 503 CHATBOT_NO_DISPONIBLE retryable=True
    intentos_503 = 0

    def handler_503(_req: httpx.Request) -> httpx.Response:
        nonlocal intentos_503
        intentos_503 += 1
        return httpx.Response(503, json={"detail": "Apagado temporalmente"})

    bot_503 = ChatbotClient(apikey="pub", token="tok", client=httpx.Client(transport=httpx.MockTransport(handler_503)))
    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: bot_503)
    resp_503 = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es ASMD?"},
    )
    assert resp_503.status_code == 503
    assert resp_503.get_json()["code"] == "CHATBOT_NO_DISPONIBLE"
    assert resp_503.get_json()["retryable"] is True
    assert intentos_503 == 2

    # 2) 422 permanente del chatbot -> 422 CONSULTA_NO_PROCESABLE_POR_CHATBOT sin reintentar
    intentos_422 = 0

    def handler_422(_req: httpx.Request) -> httpx.Response:
        nonlocal intentos_422
        intentos_422 += 1
        return httpx.Response(422, json={"detail": "Formato invalido"})

    bot_422 = ChatbotClient(apikey="pub", token="tok", client=httpx.Client(transport=httpx.MockTransport(handler_422)))
    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: bot_422)
    resp_422 = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es ASMD?"},
    )
    assert resp_422.status_code == 422
    assert resp_422.get_json()["code"] == "CONSULTA_NO_PROCESABLE_POR_CHATBOT"
    assert resp_422.get_json()["retryable"] is False
    assert intentos_422 == 1

    # 3) 401 de configuracion -> 503 sin exponer apikey ni token
    bot_401 = ChatbotClient(
        apikey="SUPER_SECRETO_APIKEY",
        token="SUPER_SECRETO_TOKEN",
        client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(401, json={"detail": "Unauthorized"}))),
    )
    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: bot_401)
    resp_401 = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es ASMD?"},
    )
    assert resp_401.status_code == 503
    body_401 = resp_401.get_json()
    assert body_401["code"] == "CHATBOT_NO_DISPONIBLE"
    assert body_401["retryable"] is False
    assert "SUPER_SECRETO" not in json.dumps(body_401)


@pytest.mark.parametrize("respuesta_raw", ["", "   ", None, "<script>alert(1)</script>"])
def test_tc07_respuesta_vacia_o_solo_script_retorna_502(app, client, session, monkeypatch, respuesta_raw):
    _, token = _crear_token(app, session)

    class _BotVacio:
        def enviar_mensaje(self, mensaje: str, conversacion_id: str | None = None):
            return {"ok": True, "respuesta": respuesta_raw}

    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: _BotVacio())

    resp = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es la enfermedad de Fabry?"},
    )
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["code"] == "RESPUESTA_CHATBOT_VACIA"
    assert body["retryable"] is True


def test_seguridad_saneamiento_xss_validaciones_contrato_y_latencia(app, client, session, monkeypatch):
    _, token = _crear_token(app, session)
    pat = Patologia(nombre="ASMD", descripcion="Deficiencia de esfingomielinasa acida")
    session.add(pat)
    session.commit()

    # patologia_id inexistente -> 404
    resp_404 = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es ASMD?", "patologia_id": 9999},
    )
    assert resp_404.status_code == 404
    assert resp_404.get_json()["code"] == "PATOLOGIA_NO_ENCONTRADA"

    # Tipos invalidos -> 400 DATOS_INVALIDOS con "ok": False bien formado
    for malo in ({"pregunta": 123}, {"pregunta": "hola?", "patologia_id": "1"}, {"pregunta": "hola?", "patologia_id": True}):
        resp_tipo = client.post(
            "/api/v1/chatbot/consultas",
            headers={"Authorization": f"Bearer {token}"},
            json=malo,
        )
        assert resp_tipo.status_code == 400
        assert resp_tipo.get_json()["ok"] is False
        assert resp_tipo.get_json()["code"] == "DATOS_INVALIDOS"

    # conversacion_id > 200 -> 400
    resp_conv = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "¿Qué es ASMD?", "conversacion_id": "c" * 201},
    )
    assert resp_conv.status_code == 400
    assert resp_conv.get_json()["code"] == "CONSULTA_NO_PROCESABLE_POR_CHATBOT"

    # Saneamiento XSS + SQLi seguro + timeout por env var
    monkeypatch.setenv("CHATBOT_API_TIMEOUT_SECONDS", "10")
    bot_timeout_check = ChatbotClient(apikey="p", token="t")
    assert bot_timeout_check.timeout == 10.0
    bot_timeout_check.close()

    class _BotXss:
        def enviar_mensaje(self, mensaje: str, conversacion_id: str | None = None):
            return {
                "respuesta": (
                    "<script>alert('xss')</script><style>body{display:none}</style>"
                    "En ASMD los niveles pueden ser < 5% <img src=x onerror=alert(1)>."
                ),
                "conversacion_id": "c-xss",
                "tipo": "respuesta",
            }

    monkeypatch.setattr("src.core.services.chatbot_service.ChatbotClient", lambda: _BotXss())

    resp_xss = client.post(
        "/api/v1/chatbot/consultas",
        headers={"Authorization": f"Bearer {token}"},
        json={"pregunta": "'; DROP TABLE patologias; -- sobre ASMD", "patologia_id": pat.id},
    )
    assert resp_xss.status_code == 200
    respuesta_segura = resp_xss.get_json()["data"]["respuesta"]
    assert "<script" not in respuesta_segura.lower()
    assert "alert(" not in respuesta_segura
    assert "<img" not in respuesta_segura.lower()
    assert "En ASMD los niveles pueden ser < 5%" in respuesta_segura
    assert session.scalar(select(func.count()).select_from(Patologia)) == 1

    # SLA local (< 200ms p95 con cliente mockeado)
    latencias_ms: list[float] = []
    for _ in range(20):
        t0 = time.perf_counter()
        r = client.post(
            "/api/v1/chatbot/consultas",
            headers={"Authorization": f"Bearer {token}"},
            json={"pregunta": "¿Qué es ASMD?"},
        )
        latencias_ms.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    latencias_ms.sort()
    p95_ms = latencias_ms[int(0.95 * len(latencias_ms)) - 1]
    assert p95_ms < 200.0
