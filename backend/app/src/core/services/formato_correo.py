"""Formato unificado en texto plano para los correos electronicos del sistema."""
from __future__ import annotations

from collections.abc import Sequence

# shortcut: la API externa POST /avisos solo acepta texto plano (<= 10.000 chars); pasar a HTML si cambia el contrato de API_Notificaciones_por_Email.md
_PREFIJO_ASUNTO = "[Exoma Clínico] "
_MAX_ASUNTO = 200
_MAX_MENSAJE = 10_000
_SEPARADOR_FUERTE = "━" * 36
_SEPARADOR_SUAVE = "─" * 36
_SEPARADOR_DESTACADO = "·" * 32


def asunto_correo(titulo: str) -> str:
    """Normaliza el asunto con prefijo institucional respetando el limite de 200 caracteres."""
    limpio = " ".join(titulo.split())
    if not limpio.startswith(_PREFIJO_ASUNTO):
        limpio = f"{_PREFIJO_ASUNTO}{limpio}"
    if len(limpio) <= _MAX_ASUNTO:
        return limpio
    return f"{limpio[: _MAX_ASUNTO - 1].rstrip()}…"


def formatear_correo(
    *,
    titulo: str,
    introduccion: str,
    saludo: str | None = None,
    destacado: Sequence[str] | None = None,
    secciones: Sequence[tuple[str, Sequence[str]]] | None = None,
    cierre: str | None = None,
) -> str:
    """Compone un correo en texto plano limpio, escaneable y legible en movil y escritorio."""
    bloques: list[str] = [
        f"EXOMA CLÍNICO · Coordinación de Laboratorio\n{_SEPARADOR_FUERTE}",
        titulo.strip().upper(),
    ]

    if saludo and saludo.strip():
        bloques.append(saludo.strip())

    if introduccion and introduccion.strip():
        bloques.append(introduccion.strip())

    if destacado:
        lineas_dest = [linea.strip() for linea in destacado if linea and linea.strip()]
        if lineas_dest:
            cuerpo_dest = "\n".join(f"  {linea}" for linea in lineas_dest)
            bloques.append(f"  {_SEPARADOR_DESTACADO}\n{cuerpo_dest}\n  {_SEPARADOR_DESTACADO}")

    for nombre_seccion, items in secciones or ():
        items_limpios = [item.strip() for item in items if item and item.strip()]
        if not items_limpios:
            continue
        lista = "\n".join(f"• {item}" for item in items_limpios)
        bloques.append(f"{nombre_seccion.strip().upper()}\n{_SEPARADOR_SUAVE}\n{lista}")

    if cierre and cierre.strip():
        bloques.append(cierre.strip())

    bloques.append(
        f"{_SEPARADOR_SUAVE}\n"
        "Sistema de Seguimiento de Estudios de Exoma Clínico\n"
        "Mensaje automático · Por favor, no responda a este correo."
    )

    mensaje = "\n\n".join(bloques)
    if len(mensaje) <= _MAX_MENSAJE:
        return mensaje
    return f"{mensaje[: _MAX_MENSAJE - 1].rstrip()}…"
