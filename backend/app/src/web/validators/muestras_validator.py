"""Funciones de validacion para solicitudes de toma de muestras y remuestreo (Escenarios 9 y 10)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.core.models.enums import MotivoDescarte
from src.core.services.excepciones import ErrorDatosInvalidos


def _parsear_entero_positivo(valor_raw: Any, nombre_campo: str) -> tuple[int | None, str | None]:
    """Convierte un valor opcional a entero positivo validando su formato."""
    if valor_raw is None or str(valor_raw).strip() == "":
        return None, None
    try:
        numero = int(valor_raw)
    except (ValueError, TypeError):
        return None, f"El parametro '{nombre_campo}' debe ser un entero positivo."
    if numero <= 0:
        return None, f"El parametro '{nombre_campo}' debe ser un entero positivo."
    return numero, None


def validar_filtros_pendientes_toma(
    args: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Valida los parametros de filtro para listar turnos pendientes de extraccion."""
    dni_raw = args.get("dni") if hasattr(args, "get") else None
    dni = str(dni_raw).strip() if dni_raw is not None and str(dni_raw).strip() else None

    estudio_id, error = _parsear_entero_positivo(
        args.get("estudio_id") if hasattr(args, "get") else None,
        "estudio_id",
    )
    if error:
        return None, error

    centro_id, error = _parsear_entero_positivo(
        args.get("centro_id") if hasattr(args, "get") else None,
        "centro_id",
    )
    if error:
        return None, error

    fecha: date | None = None
    fecha_raw = args.get("fecha") if hasattr(args, "get") else None
    if fecha_raw is not None and str(fecha_raw).strip():
        try:
            fecha = date.fromisoformat(str(fecha_raw).strip())
        except (ValueError, TypeError):
            return None, "El formato de 'fecha' debe ser YYYY-MM-DD."

    return {
        "dni": dni,
        "estudio_id": estudio_id,
        "centro_id": centro_id,
        "fecha": fecha,
    }, None


def validar_registrar_toma_muestra(
    payload: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Valida el cuerpo opcional de la solicitud de registro de toma de muestra."""
    if payload is None or payload == {}:
        return {"tomada_en": None}, None

    if not isinstance(payload, dict):
        return None, "El cuerpo de la solicitud debe ser un objeto JSON valido."

    tomada_en: datetime | None = None
    tomada_en_raw = payload.get("tomada_en")
    if tomada_en_raw is not None:
        if not isinstance(tomada_en_raw, str) or not tomada_en_raw.strip():
            return None, "El campo 'tomada_en' debe ser una cadena ISO-8601 valida."
        try:
            tomada_en = datetime.fromisoformat(tomada_en_raw.strip())
        except (ValueError, TypeError):
            return (
                None,
                "El campo 'tomada_en' debe tener formato ISO-8601 valido (ej: 2026-11-18T10:30:00).",
            )
        if tomada_en.tzinfo is not None:
            tomada_en = tomada_en.replace(tzinfo=None)

    return {"tomada_en": tomada_en}, None


def validar_filtros_remuestreables(args: Any) -> dict[str, Any]:
    """Valida los filtros para listar estudios elegibles para remuestreo (Escenario 10)."""
    dni_raw = args.get("dni") if hasattr(args, "get") else None
    dni = str(dni_raw).strip() if dni_raw is not None and str(dni_raw).strip() else None

    estudio_id, error = _parsear_entero_positivo(
        args.get("estudio_id") if hasattr(args, "get") else None,
        "estudio_id",
    )
    if error:
        raise ErrorDatosInvalidos(error)

    return {
        "dni": dni,
        "estudio_id": estudio_id,
    }


def validar_remuestreo_estudio(payload: Any) -> dict[str, Any]:
    """Valida el cuerpo JSON para declarar el remuestreo de un estudio (Escenario 10 / ADR-004)."""
    if not isinstance(payload, dict):
        raise ErrorDatosInvalidos("El cuerpo de la solicitud debe ser un objeto JSON valido.")

    motivo_descarte_raw = payload.get("motivo_descarte")
    if not isinstance(motivo_descarte_raw, str) or not motivo_descarte_raw.strip():
        raise ErrorDatosInvalidos(
            "El campo 'motivo_descarte' es obligatorio.",
            codigo="MOTIVO_DESCARTE_REQUERIDO",
        )

    motivo_descarte_norm = motivo_descarte_raw.strip().lower()
    try:
        motivo_descarte = MotivoDescarte(motivo_descarte_norm)
    except ValueError as exc:
        validos = ", ".join(m.value for m in MotivoDescarte)
        raise ErrorDatosInvalidos(
            f"El campo 'motivo_descarte' es invalido. Valores permitidos: {validos}.",
            codigo="MOTIVO_DESCARTE_INVALIDO",
        ) from exc

    motivo_raw = payload.get("motivo")
    if not isinstance(motivo_raw, str) or not motivo_raw.strip():
        raise ErrorDatosInvalidos(
            "El campo 'motivo' es obligatorio.",
            codigo="MOTIVO_REQUERIDO",
        )
    motivo = motivo_raw.strip()
    if len(motivo) > 500:
        raise ErrorDatosInvalidos("El campo 'motivo' no puede superar los 500 caracteres.")

    obs_raw = payload.get("observaciones_calidad")
    observaciones_calidad: str | None = None
    if obs_raw is not None:
        if not isinstance(obs_raw, str):
            raise ErrorDatosInvalidos("El campo 'observaciones_calidad' debe ser texto.")
        limpio = obs_raw.strip()
        if len(limpio) > 500:
            raise ErrorDatosInvalidos(
                "El campo 'observaciones_calidad' no puede superar los 500 caracteres."
            )
        observaciones_calidad = limpio or None

    return {
        "motivo_descarte": motivo_descarte,
        "observaciones_calidad": observaciones_calidad,
        "motivo": motivo,
    }