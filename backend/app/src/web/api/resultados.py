"""Blueprint de endpoints para consulta/descarga de resultados y avisos (Escenarios 16 y 37)."""
from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, make_response, request
from src.core.services import resultado_service
from src.core.services.excepciones import ErrorDominio
from src.web.decorators.auth import requiere_sesion

resultados_bp = Blueprint("resultados", __name__, url_prefix="/api")


def _parsear_entero_positivo_opcional(nombre: str) -> int | None:
    raw = request.args.get(nombre)
    if raw is None or raw == "":
        return None
    try:
        valor = int(raw)
    except ValueError as exc:
        raise ErrorDominio(
            f"El parametro {nombre} debe ser un entero positivo.",
            codigo="DATOS_INVALIDOS",
            http_status=400,
        ) from exc
    if valor <= 0:
        raise ErrorDominio(
            f"El parametro {nombre} debe ser un entero positivo.",
            codigo="DATOS_INVALIDOS",
            http_status=400,
        )
    return valor


def _parsear_bool_opcional(nombre: str) -> bool:
    raw = request.args.get(nombre)
    if raw is None or raw == "":
        return False
    normalizado = raw.strip().lower()
    if normalizado in ("true", "1"):
        return True
    if normalizado in ("false", "0"):
        return False
    raise ErrorDominio(
        f"El parametro {nombre} debe ser booleano (true/false).",
        codigo="DATOS_INVALIDOS",
        http_status=400,
    )


@resultados_bp.get("/avisos")
@requiere_sesion()
def listar_mis_avisos():
    solo_no_leidos = _parsear_bool_opcional("solo_no_leidos")
    limite = _parsear_entero_positivo_opcional("limite")
    datos = resultado_service.listar_avisos_usuario(
        usuario=g.usuario_actual,
        solo_no_leidos=solo_no_leidos,
        limite=limite if limite is not None else 50,
    )
    resp = make_response(jsonify({"ok": True, **datos}), 200)
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@resultados_bp.get("/estudios/mis-estudios")
@requiere_sesion()
def listar_mis_estudios_resultados():
    estudios = resultado_service.listar_estudios_usuario(usuario=g.usuario_actual)
    resp = make_response(jsonify({"ok": True, "estudios": estudios}), 200)
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@resultados_bp.get("/estudios/<int:estudio_id>/resultado")
@requiere_sesion()
def consultar_resultado_estudio(estudio_id: int):
    datos = resultado_service.consultar_resultado_estudio(
        estudio_id=estudio_id,
        usuario=g.usuario_actual,
    )
    resp = make_response(jsonify({"ok": True, **datos}), 200)
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@resultados_bp.get("/estudios/<int:estudio_id>/resultado/pdf")
@requiere_sesion()
def descargar_resultado_pdf(estudio_id: int):
    analisis_id = _parsear_entero_positivo_opcional("analisis_id")
    pdf_bytes, nombre_archivo = resultado_service.descargar_pdf_resultado(
        estudio_id=estudio_id,
        usuario=g.usuario_actual,
        analisis_id=analisis_id,
    )
    return Response(
        pdf_bytes,
        status=200,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_archivo}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
