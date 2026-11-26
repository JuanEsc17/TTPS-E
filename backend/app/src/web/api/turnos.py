"""Blueprint de endpoints para la gestion de turnos y centros de extraccion."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services.turno_service import TurnoService
from src.web.decorators.auth import requiere_sesion
from src.web.validators.turnos_validator import (
    serializar_centro,
    serializar_centros,
    validar_consulta_disponibilidad,
    validar_solicitar_turno,
)

turnos_bp = Blueprint("turnos", __name__, url_prefix="/api/v1")


@turnos_bp.get("/turnos/mis-estudios")
@requiere_sesion(roles=[Rol.PACIENTE])
def listar_mis_estudios_para_turno() -> tuple[Any, int]:
    """Retorna los estudios del paciente autenticado con su estado y turno activo."""
    estudios = TurnoService.listar_estudios_paciente(g.usuario_actual.id)
    return jsonify({"ok": True, "data": estudios}), 200


@turnos_bp.get("/turnos/mis-turnos")
@requiere_sesion(roles=[Rol.PACIENTE])
def listar_mis_turnos() -> tuple[Any, int]:
    """Retorna el historial completo de turnos del paciente autenticado."""
    turnos = TurnoService.listar_turnos_paciente(g.usuario_actual.id)
    return jsonify({"ok": True, "data": turnos}), 200


@turnos_bp.get("/centros-extraccion")
@requiere_sesion()
def listar_centros() -> tuple[Any, int]:
    """Retorna el listado de centros de extraccion para visualizar en el mapa interactivo."""
    centros = TurnoService.listar_centros()
    return jsonify({"ok": True, "data": serializar_centros(centros)}), 200


@turnos_bp.get("/centros-extraccion/<int:centro_id>/turnos-disponibles")
@requiere_sesion()
def obtener_turnos_disponibles(centro_id: int) -> tuple[Any, int]:
    """Consulta los slots de 15 minutos libres en un centro para una fecha dada."""
    parametros, error = validar_consulta_disponibilidad(request.args)
    if error:
        return jsonify({"ok": False, "error": error}), 422

    resultado, error, status = TurnoService.obtener_disponibilidad(
        centro_id=centro_id,
        fecha=parametros["fecha"],
    )

    if error:
        return jsonify({"ok": False, "error": error}), status

    data = {
        "centro": serializar_centro(resultado["centro"]),
        "fecha": resultado["fecha"],
        "slots_libres": resultado["slots_libres"],
    }
    return jsonify({"ok": True, "data": data}), status


@turnos_bp.post("/estudios/<int:estudio_id>/turnos")
@requiere_sesion(roles=[Rol.PACIENTE])
def reservar_turno(estudio_id: int) -> tuple[Any, int]:
    """Reserva un turno de extraccion de 15 minutos para el paciente titular del estudio."""
    payload = request.get_json(silent=True)
    datos, error = validar_solicitar_turno(payload)
    if error:
        return jsonify({"ok": False, "error": error}), 422

    # Obtenemos el usuario autenticado inyectado por @requiere_sesion
    usuario_actual_id = g.usuario_actual.id

    resultado, error, status = TurnoService.solicitar_turno(
        estudio_id=estudio_id,
        centro_id=datos["centro_id"],
        inicio=datos["inicio"],
        usuario_actual_id=usuario_actual_id,
    )

    if error:
        return jsonify({"ok": False, "error": error}), status

    return jsonify({"ok": True, "data": resultado}), status


@turnos_bp.post("/turnos/<int:turno_id>/cancelar")
@requiere_sesion(roles=[Rol.PACIENTE])
def cancelar_turno(turno_id: int) -> tuple[Any, int]:
    """Cancela un turno de extraccion activo perteneciente al paciente autenticado."""
    usuario_actual_id = g.usuario_actual.id

    resultado, error, status = TurnoService.cancelar_turno(
        turno_id=turno_id,
        usuario_actual_id=usuario_actual_id,
    )

    if error:
        return jsonify({"ok": False, "error": error}), status

    return jsonify({"ok": True, "data": resultado}), status


@turnos_bp.get("/turnos/<int:turno_id>/consentimiento-pdf")
@requiere_sesion(roles=[Rol.PACIENTE])
def descargar_consentimiento_pdf(turno_id: int) -> Any:
    """Descarga el PDF de Orden de Extraccion y Consentimiento Informado del turno."""
    from flask import Response

    usuario_actual_id = g.usuario_actual.id
    resultado, error, status = TurnoService.descargar_consentimiento_pdf(
        turno_id=turno_id,
        usuario_actual_id=usuario_actual_id,
    )
    if error:
        codigo = (
            "FORBIDDEN_NOT_OWNER"
            if status == 403
            else ("RECURSO_NO_ENCONTRADO" if status == 404 else "ERROR_PDF")
        )
        return (
            jsonify(
                {
                    "ok": False,
                    "error": error,
                    "code": codigo,
                    "retryable": status == 502,
                }
            ),
            status,
        )

    pdf_bytes, nombre_archivo = resultado
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

