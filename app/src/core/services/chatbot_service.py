"""Servicio de consultas al chatbot externo sobre patologias (Escenario 25)."""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from src.clients.chatbot_client import ChatbotClient
from src.clients.exceptions import (
    ClienteAutenticacionError,
    ClienteConexionError,
    ClienteServicioError,
    ClienteValidacionError,
)
from src.core.repos import clinica_repo, usuario_repo
from src.core.services.excepciones import ErrorDominio

logger = logging.getLogger(__name__)

_PATOLOGIAS_HABILITADAS_DEFAULT: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Enfermedad de Fabry", ("fabry",)),
    ("Enfermedad de Pompe", ("pompe",)),
    ("Mucopolisacaridosis 1", ("mucopolisacaridosis", "mps 1", "mps1", "mps-1", "hurler")),
    ("Enfermedad de Gaucher", ("gaucher",)),
    ("ASMD", ("asmd", "niemann-pick", "niemann pick")),
)

_RE_BLOQUES_PELIGROSOS = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_RE_TAGS_HTML = re.compile(r"</?[a-zA-Z!][^>]*>")
_RE_ESPACIOS_LINEA = re.compile(r"[ \t]{2,}")


def _sanear_respuesta(texto: str) -> str:
    """Elimina bloques script/style y etiquetas HTML preservando texto legible."""
    sin_bloques = _RE_BLOQUES_PELIGROSOS.sub("", texto)
    sin_tags = _RE_TAGS_HTML.sub("", sin_bloques)
    lineas = [_RE_ESPACIOS_LINEA.sub(" ", linea).strip() for linea in sin_tags.splitlines()]
    return "\n".join(linea for linea in lineas if linea).strip()


def _es_error_timeout(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return True
    if isinstance(exc.__cause__, (httpx.TimeoutException, TimeoutError)):
        return True
    texto = str(exc).lower()
    return "timeout" in texto or "timed out" in texto


def _extraer_patologias_relacionadas(
    *,
    pregunta: str,
    respuesta: str,
    patologia_contexto: str | None,
    respuesta_upstream: Any,
) -> list[str]:
    """Identifica las patologias mencionadas sin depender de campos extra de la API externa."""
    encontradas: list[str] = []
    if isinstance(respuesta_upstream, list):
        for item in respuesta_upstream:
            nombre = str(item).strip()
            if nombre and nombre not in encontradas:
                encontradas.append(nombre)

    if patologia_contexto and patologia_contexto not in encontradas:
        encontradas.append(patologia_contexto)

    texto_completo = f"{pregunta} {respuesta}".lower()
    for nombre_canonico, aliases in _PATOLOGIAS_HABILITADAS_DEFAULT:
        if any(alias in texto_completo for alias in aliases) and nombre_canonico not in encontradas:
            encontradas.append(nombre_canonico)

    nombres_vistos = {e.lower() for e in encontradas}
    for pat in clinica_repo.listar_patologias():
        nombre_bd = pat.nombre.strip()
        if nombre_bd and nombre_bd.lower() in texto_completo and nombre_bd.lower() not in nombres_vistos:
            encontradas.append(nombre_bd)
            nombres_vistos.add(nombre_bd.lower())

    return encontradas


def _enviar_con_reintento(
    cliente: ChatbotClient,
    mensaje_envio: str,
    conversacion_id: str | None,
) -> dict[str, Any]:
    """Envia la consulta al chatbot con 1 reintento (backoff 1s) ante red o 502/503/504."""
    url_destino = os.environ.get("CHATBOT_URL") or os.environ.get("CHATBOT_API_URL") or "chatbot_externo"

    for intento in range(2):
        inicio = time.monotonic()
        try:
            resultado = cliente.enviar_mensaje(mensaje_envio, conversacion_id=conversacion_id)
            latencia_ms = int((time.monotonic() - inicio) * 1000)
            logger.info(
                "[chatbot_client] step_2_derivar_pregunta_chatbot status=200 latency_ms=%d",
                latencia_ms,
            )
            return resultado if isinstance(resultado, dict) else {}
        except ClienteValidacionError as exc:
            latencia_ms = int((time.monotonic() - inicio) * 1000)
            logger.warning(
                "[chatbot_client] step_2_derivar_pregunta_chatbot status=%s latency_ms=%d",
                exc.codigo_http or 422,
                latencia_ms,
            )
            raise ErrorDominio(
                "La consulta no pudo ser procesada por el asistente de patologias.",
                codigo="CONSULTA_NO_PROCESABLE_POR_CHATBOT",
                http_status=422,
                reintentable=False,
            ) from exc
        except ClienteAutenticacionError as exc:
            latencia_ms = int((time.monotonic() - inicio) * 1000)
            logger.error(
                "[chatbot_client] error de autenticacion con chatbot externo status=%s latency_ms=%d",
                exc.codigo_http or 401,
                latencia_ms,
            )
            raise ErrorDominio(
                "El asistente de consultas sobre patologias no se encuentra disponible en este momento.",
                codigo="CHATBOT_NO_DISPONIBLE",
                http_status=503,
                reintentable=False,
            ) from exc
        except (ClienteConexionError, ClienteServicioError, httpx.TimeoutException, TimeoutError) as exc:
            latencia_ms = int((time.monotonic() - inicio) * 1000)
            es_timeout = _es_error_timeout(exc) or getattr(exc, "codigo_http", None) == 504
            status_ext = getattr(exc, "codigo_http", None) or (504 if es_timeout else 503)
            logger.warning(
                "[chatbot_client] step_2_derivar_pregunta_chatbot status=%s latency_ms=%d intento=%d",
                status_ext,
                latencia_ms,
                intento + 1,
            )
            puede_reintentar = isinstance(
                exc, (ClienteConexionError, httpx.TimeoutException, TimeoutError)
            ) or status_ext in (502, 503, 504)
            if intento == 0 and puede_reintentar:
                time.sleep(1.0)
                continue

            logger.error("[chatbot_service] abort_cleanup indisponibilidad url=%s status=%s", url_destino, status_ext)
            if es_timeout:
                raise ErrorDominio(
                    "El servicio de chatbot sobre patologias no respondio dentro del tiempo esperado.",
                    codigo="CHATBOT_TIMEOUT",
                    http_status=504,
                    reintentable=True,
                ) from exc
            raise ErrorDominio(
                "El asistente de consultas sobre patologias no se encuentra disponible en este momento. "
                "Por favor, intente nuevamente en unos instantes.",
                codigo="CHATBOT_NO_DISPONIBLE",
                http_status=503,
                reintentable=True,
            ) from exc

    raise AssertionError("Estado inalcanzable en reintentos de chatbot")


def consultar_chatbot(
    *,
    usuario_id: int,
    pregunta: str,
    patologia_id: int | None = None,
    conversacion_id: str | None = None,
    chatbot_client: ChatbotClient | None = None,
) -> dict[str, Any]:
    """Valida la consulta del paciente y la deriva al chatbot sin enviar PII."""
    pregunta_limpia = (pregunta or "").replace("\x00", "").strip()
    if len(pregunta_limpia) < 3 or len(pregunta_limpia) > 1000:
        raise ErrorDominio(
            "La pregunta debe tener entre 3 y 1000 caracteres.",
            codigo="PREGUNTA_INVALIDA",
            http_status=400,
        )

    conv_limpia = conversacion_id.strip() if isinstance(conversacion_id, str) and conversacion_id.strip() else None
    if conv_limpia is not None and len(conv_limpia) > 200:
        raise ErrorDominio(
            "El identificador de conversacion no puede superar los 200 caracteres.",
            codigo="CONSULTA_NO_PROCESABLE_POR_CHATBOT",
            http_status=400,
        )

    paciente = usuario_repo.buscar_paciente_por_usuario_id(usuario_id)
    paciente_ref_id = paciente.id if paciente is not None else usuario_id

    patologia_nombre: str | None = None
    if patologia_id is not None:
        patologia = clinica_repo.buscar_patologia_por_id(patologia_id)
        if patologia is None:
            raise ErrorDominio(
                "Patologia no encontrada.",
                codigo="PATOLOGIA_NO_ENCONTRADA",
                http_status=404,
            )
        patologia_nombre = patologia.nombre

    logger.info(
        "[chatbot_service] step_1_validar_consulta_chatbot paciente_id=%s patologia_id=%s",
        paciente_ref_id,
        patologia_id,
    )

    # Envia unicamente la pregunta (y contexto de patologia publica si fue seleccionada), nunca PII
    mensaje_envio = pregunta_limpia
    if patologia_nombre and patologia_nombre.lower() not in pregunta_limpia.lower():
        prefijado = f"Sobre {patologia_nombre}: {pregunta_limpia}"
        if len(prefijado) <= 1000:
            mensaje_envio = prefijado

    cliente = chatbot_client or ChatbotClient()
    try:
        resultado_ext = _enviar_con_reintento(cliente, mensaje_envio, conv_limpia)
    finally:
        if hasattr(cliente, "close"):
            cliente.close()

    respuesta_cruda = resultado_ext.get("respuesta")
    respuesta_limpia = _sanear_respuesta(respuesta_cruda) if isinstance(respuesta_cruda, str) else ""
    if not respuesta_limpia:
        raise ErrorDominio(
            "El asistente devolvio una respuesta vacia. Intente nuevamente.",
            codigo="RESPUESTA_CHATBOT_VACIA",
            http_status=502,
            reintentable=True,
        )

    patologias_relacionadas = _extraer_patologias_relacionadas(
        pregunta=pregunta_limpia,
        respuesta=respuesta_limpia,
        patologia_contexto=patologia_nombre,
        respuesta_upstream=resultado_ext.get("patologias_relacionadas"),
    )

    logger.info(
        "[chatbot_service] step_3_respuesta_entregada_ok paciente_id=%s chars=%d",
        paciente_ref_id,
        len(respuesta_limpia),
    )

    return {
        "pregunta": pregunta_limpia,
        "respuesta": respuesta_limpia,
        "patologias_relacionadas": patologias_relacionadas,
        "respondido_en": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "conversacion_id": resultado_ext.get("conversacion_id"),
        "tipo": resultado_ext.get("tipo") or "respuesta",
    }
