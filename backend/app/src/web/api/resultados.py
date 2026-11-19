"""Blueprint de endpoints para consulta y descarga de resultados de exoma (Escenario 16)."""
from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, make_response, request
from src.core.services import resultado_service
from src.core.services.excepciones import ErrorDominio
from src.web.decorators.auth import requiere_sesion

resultados_bp = Blueprint("resultados", __name__, url_prefix="/api")


def _parsear_analisis_id_opcional() -> int | None:
    raw = request.args.get("analisis_id")
    if raw is None or raw == "":
        return None
    try:
        valor = int(raw)
    except ValueError as exc:
        raise ErrorDominio(
            "El parametro analisis_id debe ser un entero positivo.",
            codigo="DATOS_INVALIDOS",
            http_status=400,
        ) from exc
    if valor <= 0:
        raise ErrorDominio(
            "El parametro analisis_id debe ser un entero positivo.",
            codigo="DATOS_INVALIDOS",
            http_status=400,
        )
    return valor


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
    analisis_id = _parsear_analisis_id_opcional()
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
