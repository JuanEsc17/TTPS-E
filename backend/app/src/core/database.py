from __future__ import annotations

import logging
import os
from typing import Any

from flask_sqlalchemy_lite import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from .models.base import Base

logger = logging.getLogger(__name__)
db = SQLAlchemy()


def normalizar_database_url(database_url: str) -> str:
    """Normaliza la URI de base de datos para usar psycopg v3 y SSL en Supabase."""
    limpia = database_url.strip()
    if limpia.startswith("postgres://"):
        limpia = "postgresql+psycopg://" + limpia.removeprefix("postgres://")
    elif limpia.startswith("postgresql://"):
        limpia = "postgresql+psycopg://" + limpia.removeprefix("postgresql://")

    if limpia.startswith("sqlite"):
        return limpia

    parsed = make_url(limpia)
    host = (parsed.host or "").lower()
    if (
        parsed.get_backend_name() == "postgresql"
        and host.endswith((".supabase.com", ".supabase.co"))
        and "sslmode" not in parsed.query
    ):
        parsed = parsed.update_query_dict({"sslmode": "require"})
    return parsed.render_as_string(hide_password=False)


def construir_config_engine(database_url: str) -> str | dict[str, Any]:
    """Construye la configuracion de SQLAlchemy compatible con SQLite y PostgreSQL/Supabase."""
    url_normalizada = normalizar_database_url(database_url)
    if url_normalizada.startswith("sqlite"):
        return url_normalizada

    return {
        "url": url_normalizada,
        "pool_pre_ping": True,
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "300")),
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "3")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "2")),
    }


def verificar_conexion_db() -> bool:
    """Ejecuta una consulta liviana para validar conectividad activa con la base de datos."""
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        logger.error("[database] fallo_conexion_db err=%s", exc)
        return False
    return True


def init_app(app):
    db.init_app(app)
    return db


# Alias para compatibilidad con BaseModel
BaseModel = Base


def create_tables():
    # Importar el paquete registra todos los modelos en Base.metadata
    from . import models  # noqa: F401

    Base.metadata.create_all(db.engine)


def reset_db():
    from . import models  # noqa: F401

    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
