"""Application factory de Flask para el Sistema de Laboratorio de Exoma Clinico."""
import os

from flask import Flask

from .core.database import db


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)

    # Configuracion por defecto
    database_url = os.environ.get(
        "DATABASE_URL",
        "sqlite:///:memory:"  # SQLite en memoria por defecto para desarrollo/tests rapidos
    )
    app.config["SQLALCHEMY_ENGINES"] = {"default": database_url}
    app.config["TESTING"] = False

    if config:
        # Si pasan SQLALCHEMY_DATABASE_URI o database_url por config, adaptarlo a SQLALCHEMY_ENGINES
        if "SQLALCHEMY_DATABASE_URI" in config:
            uri = config.pop("SQLALCHEMY_DATABASE_URI")
            app.config["SQLALCHEMY_ENGINES"] = {"default": uri}
        app.config.update(config)

    # Inicializar extensiones
    db.init_app(app)

    return app
