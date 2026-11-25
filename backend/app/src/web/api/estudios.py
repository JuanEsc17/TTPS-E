"""Blueprint de estudios de exoma y consulta de genes (/api/v1)."""
from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services import estudio_service
from src.web.decorators.auth import requiere_sesion
from src.web.validators.estudios_validator import AltaEstudioSchema

estudios_bp = Blueprint("estudios", __name__, url_prefix="/api/v1")


@estudios_bp.get("/estudios")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def listar_estudios():
    estudios = estudio_service.listar_estudios_medico(g.usuario_actual.id)
    return jsonify({"ok": True, "data": estudios}), 200


@estudios_bp.post("/estudios")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def dar_de_alta_estudio():
    payload = request.get_json(silent=True) or {}
    datos = AltaEstudioSchema().load(payload)
    resultado = estudio_service.dar_de_alta_estudio(
        usuario_actual_id=g.usuario_actual.id,
        datos=datos,
    )
    return jsonify({"ok": True, "data": resultado}), 201


@estudios_bp.get("/patologias/<int:patologia_id>/genes")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def obtener_genes_patologia(patologia_id: int):
    incluir_sec = request.args.get("incluir_secundarios", "false").lower() == "true"
    resultado = estudio_service.obtener_genes_para_estudio(
        patologia_id=patologia_id,
        incluir_secundarios=incluir_sec,
    )
    return jsonify({"ok": True, "data": resultado}), 200


@estudios_bp.get("/bioinformatica/genes")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def buscar_genes():
    q = request.args.get("q", "")
    resultado = estudio_service.buscar_genes_manuales(q=q)
    return jsonify({"ok": True, "data": resultado}), 200


@estudios_bp.get("/obras-sociales")
@requiere_sesion(roles=(Rol.MEDICO, Rol.GERENTE_MEDICO))
def listar_obras_sociales():
    resultado = estudio_service.listar_obras_sociales()
    return jsonify({"ok": True, "data": resultado}), 200