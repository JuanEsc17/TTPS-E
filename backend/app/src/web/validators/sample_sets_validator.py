"""Validadores de entrada HTTP para consulta de SampleSets (Escenario 12)."""
from __future__ import annotations

from typing import Any

from src.core.models import EstadoSampleSet
from src.core.services.excepciones import ErrorDatosInvalidos


def validar_filtro_estado_sample_set(args: Any) -> EstadoSampleSet | None:
    """Valida el parametro opcional ?estado=... en GET /api/sample-sets."""
    estado_raw = args.get("estado") if hasattr(args, "get") else None
    if estado_raw is None or not str(estado_raw).strip():
        return None
    normalizado = str(estado_raw).strip().lower()
    try:
        return EstadoSampleSet(normalizado)
    except ValueError as exc:
        validos = ", ".join(e.value for e in EstadoSampleSet)
        raise ErrorDatosInvalidos(
            f"El filtro 'estado' es invalido. Valores permitidos: {validos}.",
            codigo="ESTADO_SAMPLE_SET_INVALIDO",
        ) from exc
