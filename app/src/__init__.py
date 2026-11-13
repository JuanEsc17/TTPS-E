"""Application factory de Flask para el Sistema de Laboratorio de Exoma Clinico."""
import os
from pathlib import Path

from flask import Flask

from .core.database import db

from .web.api.auth import auth_bp
from .web.handlers.errors import registrar_manejadores_errores


def _cargar_entorno(ruta_env: Path | None = None) -> None:
    """Carga variables desde `.env` sin sobrescribir las ya definidas en el entorno."""
    archivo_env = ruta_env or (Path(__file__).resolve().parents[2] / ".env")
    if not archivo_env.is_file():
        return

    for linea in archivo_env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in ("'", '"'):
            valor = valor[1:-1]
        if clave:
            os.environ.setdefault(clave, valor)


def create_app(config: dict | None = None) -> Flask:
    _cargar_entorno()
    app = Flask(__name__)

    # Configuracion por defecto
    database_url = os.environ.get(
        "DATABASE_URL",
        "sqlite:///:memory:"  # SQLite en memoria por defecto para desarrollo/tests rapidos
    )
    app.config["SQLALCHEMY_ENGINES"] = {"default": database_url}
    app.config["TESTING"] = False
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY",
        "dev-secret-key-no-usar-en-produccion",  # shortcut: reemplazar por env en despliegue real
    )

    if config:
        # Si pasan SQLALCHEMY_DATABASE_URI o database_url por config, adaptarlo a SQLALCHEMY_ENGINES
        if "SQLALCHEMY_DATABASE_URI" in config:
            uri = config.pop("SQLALCHEMY_DATABASE_URI")
            app.config["SQLALCHEMY_ENGINES"] = {"default": uri}
        app.config.update(config)

    # Inicializar extensiones
    db.init_app(app)
    registrar_manejadores_errores(app)
    app.register_blueprint(auth_bp)

    return app
