"""Blueprint de salud del sistema (/api/health)."""
from __future__ import annotations

from flask import Blueprint, jsonify
from src.core.database import verificar_conexion_db

salud_bp = Blueprint("salud", __name__, url_prefix="/api")


@salud_bp.get("/health")
def verificar_salud():
    """Verifica que el servicio web y la base de datos respondan correctamente."""
    if not verificar_conexion_db():
        return (
            jsonify(
                {
                    "ok": False,
                    "estado": "degradado",
                    "base_de_datos": "desconectada",
                }
            ),
            503,
        )

    return (
        jsonify(
            {
                "ok": True,
                "estado": "operativo",
                "base_de_datos": "conectada",
            }
        ),
        200,
    )
