"""Blueprint de endpoints para analisis bioinformatico y carga de datos crudos (Escenarios 15 y 24)."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from src.core.models import Rol
from src.core.services import bioinformatica_service
from src.web.decorators.auth import requiere_sesion
from src.web.validators.bioinformatica_validator import (
    CargaDatosCrudosSchema,
    RegistroAnalisisSchema,
)

bioinformatica_bp = Blueprint("bioinformatica", __name__, url_prefix="/api")


@bioinformatica_bp.get("/estudios/pendientes-datos-crudos")
@requiere_sesion(roles=(Rol.ADMINISTRATIVO,), codigo_rol_denegado="SOLO_ADMINISTRATIVO")
def listar_estudios_pendientes_datos_crudos():
    estudios = bioinformatica_service.listar_pendientes_datos_crudos()
    return jsonify({"ok": True, "estudios": estudios}), 200


@bioinformatica_bp.post("/estudios/<int:estudio_id>/datos-crudos")
@requiere_sesion(roles=(Rol.ADMINISTRATIVO,), codigo_rol_denegado="SOLO_ADMINISTRATIVO")
def cargar_datos_crudos(estudio_id: int):
    archivo = request.files.get("archivo_datos_crudos")
    if archivo is not None:
        resultado = bioinformatica_service.cargar_datos_crudos(
            estudio_id=estudio_id,
            usuario_id=g.usuario_actual.id,
            archivo_bytes=archivo.read(),
            ip_origen=request.remote_addr,
        )
    else:
        payload = request.get_json(silent=True)
        if payload is None and "contenido_actg" in request.form:
            payload = {"contenido_actg": request.form.get("contenido_actg", "")}
        datos = CargaDatosCrudosSchema().load(payload or {})
        resultado = bioinformatica_service.cargar_datos_crudos(
            estudio_id=estudio_id,
            usuario_id=g.usuario_actual.id,
            contenido_actg=datos["contenido_actg"] or "",
            ip_origen=request.remote_addr,
        )
    return jsonify({"ok": True, **resultado}), 201


@bioinformatica_bp.get("/bioinformatica/estudios")
@requiere_sesion(roles=(Rol.BIOINFORMATICO,), codigo_rol_denegado="SOLO_BIOINFORMATICO")
def listar_estudios_bioinformatica():
    bandeja = bioinformatica_service.listar_bandeja_bioinformatica(g.usuario_actual.id)
    return jsonify({"ok": True, **bandeja}), 200


@bioinformatica_bp.get("/bioinformatica/estudios/<int:estudio_id>/datos-crudos")
@requiere_sesion(roles=(Rol.BIOINFORMATICO,), codigo_rol_denegado="SOLO_BIOINFORMATICO")
def obtener_datos_crudos_estudio(estudio_id: int):
    datos = bioinformatica_service.obtener_datos_crudos_estudio(
        estudio_id=estudio_id,
        usuario_id=g.usuario_actual.id,
    )
    return jsonify({"ok": True, **datos}), 200


@bioinformatica_bp.post("/bioinformatica/estudios/<int:estudio_id>/tomar")
@requiere_sesion(roles=(Rol.BIOINFORMATICO,), codigo_rol_denegado="SOLO_BIOINFORMATICO")
def tomar_estudio(estudio_id: int):
    resultado = bioinformatica_service.tomar_estudio(
        estudio_id=estudio_id,
        usuario_id=g.usuario_actual.id,
        ip_origen=request.remote_addr,
    )
    return jsonify({"ok": True, **resultado}), 200


@bioinformatica_bp.get("/bioinformatica/genes/<int:gen_id>/variantes")
@requiere_sesion(roles=(Rol.BIOINFORMATICO,), codigo_rol_denegado="SOLO_BIOINFORMATICO")
def consultar_variantes_gen(gen_id: int):
    q = request.args.get("q")
    clasificacion = request.args.get("clasificacion")
    limite = request.args.get("limite", type=int)
    offset = request.args.get("offset", default=0, type=int)
    resultado = bioinformatica_service.consultar_variantes_gen(
        gen_id=gen_id,
        q=q,
        clasificacion=clasificacion,
        limite=limite,
        offset=offset,
    )
    return jsonify({"ok": True, **resultado}), 200


@bioinformatica_bp.get("/v1/estudios/<int:estudio_id>/genes/<int:gen_id>/variantes")
@requiere_sesion(roles=(Rol.BIOINFORMATICO,), codigo_rol_denegado="SOLO_BIOINFORMATICO")
def consultar_variantes_estudio(estudio_id: int, gen_id: int):
    resultado = bioinformatica_service.consultar_variantes_estudio(
        estudio_id=estudio_id,
        gen_id=gen_id,
        usuario_id=g.usuario_actual.id,
        q=request.args.get("q"),
        clasificacion=request.args.get("clasificacion"),
        limite=request.args.get("limite", type=int),
        offset=request.args.get("offset", default=0, type=int),
    )
    return jsonify({"ok": True, "data": resultado}), 200


@bioinformatica_bp.post("/bioinformatica/estudios/<int:estudio_id>/analisis")
@requiere_sesion(roles=(Rol.BIOINFORMATICO,), codigo_rol_denegado="SOLO_BIOINFORMATICO")
def registrar_variantes_analisis(estudio_id: int):
    payload = request.get_json(silent=True) or {}
    datos = RegistroAnalisisSchema().load(payload)
    resultado = bioinformatica_service.registrar_variantes_analisis(
        estudio_id=estudio_id,
        usuario_id=g.usuario_actual.id,
        variantes_ids=datos["variantes_ids"],
        ip_origen=request.remote_addr,
    )
    return jsonify({"ok": True, **resultado}), 200
