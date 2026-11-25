"""Validacion del cuerpo de la solicitud de emision de presupuesto (Escenario 3)."""
from __future__ import annotations

from typing import Any

from src.core.services.excepciones import ErrorDatosInvalidos


def validar_emitir_presupuesto(payload: Any) -> dict[str, Any]:
    """El body es opcional; solo puede traer obra_social_id (entero positivo o null)."""
    if payload is None:
        return {"obra_social_id": None}
    if not isinstance(payload, dict):
        raise ErrorDatosInvalidos("El cuerpo de la solicitud debe ser un objeto JSON valido.")

    valor = payload.get("obra_social_id")
    if valor is None:
        return {"obra_social_id": None}
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ErrorDatosInvalidos(
            "El campo 'obra_social_id' debe ser un entero positivo.",
            codigo="OBRA_SOCIAL_ID_INVALIDO",
        )
    return {"obra_social_id": valor}

def validar_filtros_pendientes_presupuesto(args: Any) -> dict[str, Any]:
    """Filtro opcional por DNI: solo digitos."""
    dni = str(args.get("dni") or "").strip()
    if dni and not dni.isdigit():
        raise ErrorDatosInvalidos(
            "El parametro 'dni' debe contener solo numeros.", codigo="DNI_INVALIDO"
        )
    return {"dni": dni or None}