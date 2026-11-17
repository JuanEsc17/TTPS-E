"""Blueprint para patologias y busqueda de sintomas SNOMED (/api/v1)."""
from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services import patologia_service
from src.web.decorators.auth import requiere_sesion
from src.web.validators.patologias_validator import PatologiaSchema

patologias_bp = Blueprint("patologias", __name__, url_prefix="/api/v1")


@patologias_bp.get("/patologias")
@requiere_sesion(roles=(Rol.GERENTE_MEDICO, Rol.MEDICO, Rol.BIOINFORMATICO, Rol.ADMIN_GENERAL))
def listar_patologias():
    return jsonify({"ok": True, "data": patologia_service.listar_patologias()}), 200


@patologias_bp.post("/patologias")
@requiere_sesion(roles=(Rol.GERENTE_MEDICO,), codigo_rol_denegado="SOLO_GERENTE_MEDICO")
def crear_patologia():
    payload = request.get_json(silent=True) or {}
    datos = PatologiaSchema().load(payload)
    resultado = patologia_service.guardar_patologia(
        gerente_usuario_id=g.usuario_actual.id,
        nombre=datos["nombre"] or "",
        descripcion=datos["descripcion"],
        sintoma_cardinal=datos["sintoma_cardinal"],
        sintomas_secundarios=datos["sintomas_secundarios"],
    )
    return jsonify({"ok": True, "data": resultado}), 201


@patologias_bp.put("/patologias/<int:patologia_id>")
@requiere_sesion(roles=(Rol.GERENTE_MEDICO,), codigo_rol_denegado="SOLO_GERENTE_MEDICO")
def modificar_patologia(patologia_id: int):
    payload = request.get_json(silent=True) or {}
    datos = PatologiaSchema().load(payload)
    resultado = patologia_service.guardar_patologia(
        patologia_id=patologia_id,
        gerente_usuario_id=g.usuario_actual.id,
        nombre=datos["nombre"] or "",
        descripcion=datos["descripcion"],
        sintoma_cardinal=datos["sintoma_cardinal"],
        sintomas_secundarios=datos["sintomas_secundarios"],
    )
    return jsonify({"ok": True, "data": resultado}), 200


@patologias_bp.get("/sintomas/snomed")
@requiere_sesion(roles=(Rol.GERENTE_MEDICO, Rol.MEDICO))
def buscar_sintomas_snomed():
    q = request.args.get("q", "")
    limite = request.args.get("limite", default=10, type=int)
    resultados = patologia_service.buscar_sintomas_snomed(q, limite=limite)
    return jsonify({"ok": True, "data": resultados}), 200
