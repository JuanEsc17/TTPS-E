"""Application factory de Flask para el Sistema de Laboratorio de Exoma Clinico."""
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from .core.database import construir_config_engine, create_tables, db
from .web.api.turnos import turnos_bp

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()

from .web.api.admin_usuarios import admin_usuarios_bp
from .web.api.auth import auth_bp
from .web.api.bioinformatica import bioinformatica_bp
from .web.api.chatbot import chatbot_bp
from .web.api.estudios import estudios_bp
from .web.api.logistica import logistica_bp
from .web.api.medicos import medicos_bp
from .web.api.muestras import muestras_bp
from .web.api.pacientes import pacientes_bp
from .web.api.patologias import patologias_bp
from .web.api.presupuestos import presupuestos_bp
from .web.api.resultados import resultados_bp
from .web.api.salud import salud_bp
from .web.api.sample_sets import sample_sets_bp
from .web.api.snomed import snomed_bp
from .web.handlers.errors import registrar_manejadores_errores


def _cargar_entorno(ruta_env: Path | None = None) -> None:
    """Carga variables desde `.env` sin sobrescribir las ya definidas en el entorno."""
    if ruta_env is not None:
        rutas = [ruta_env]
    else:
        base = Path(__file__).resolve()
        rutas = [base.parents[2] / ".env", base.parents[3] / ".env"]

    for archivo_env in rutas:
        if not archivo_env.is_file():
            continue

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
    app.config["SQLALCHEMY_ENGINES"] = {"default": construir_config_engine(database_url)}
    app.config["TESTING"] = False
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY",
        "dev-secret-key-no-usar-en-produccion",  # shortcut: reemplazar por env en despliegue real
    )

    if config:
        # Si pasan SQLALCHEMY_DATABASE_URI o database_url por config, adaptarlo a SQLALCHEMY_ENGINES
        if "SQLALCHEMY_DATABASE_URI" in config:
            uri = config.pop("SQLALCHEMY_DATABASE_URI")
            app.config["SQLALCHEMY_ENGINES"] = {"default": construir_config_engine(uri)}
        app.config.update(config)

    # Inicializar extensiones
    db.init_app(app)
    registrar_manejadores_errores(app)
    app.register_blueprint(auth_bp)

    # Registrar blueprints

    app.register_blueprint(turnos_bp)
    app.register_blueprint(logistica_bp)
    app.register_blueprint(medicos_bp)
    app.register_blueprint(muestras_bp)
    app.register_blueprint(snomed_bp)
    app.register_blueprint(pacientes_bp)
    app.register_blueprint(patologias_bp)
    app.register_blueprint(chatbot_bp)
    app.register_blueprint(bioinformatica_bp)
    app.register_blueprint(estudios_bp)
    app.register_blueprint(resultados_bp)
    app.register_blueprint(sample_sets_bp)
    app.register_blueprint(salud_bp)
    app.register_blueprint(presupuestos_bp)

    @app.cli.command("init-db")
    def init_db_cli() -> None:
        """Crea las tablas faltantes en la base de datos configurada de forma idempotente."""
        create_tables()
        print("Tablas verificadas/creadas correctamente.")

    @app.cli.command("procesar-ausencias")
    def procesar_ausencias_cli() -> None:
        """Procesa automaticamente al finalizar el dia los turnos sin muestra y notifica por mail."""
        from .core.services.ausencia_service import AusenciaService

        resumen = AusenciaService.procesar_turnos_vencidos()
        print(
            f"Turnos vencidos detectados: {resumen['total_detectados']} | "
            f"Procesados: {resumen['total_procesados']} | "
            f"Errores: {len(resumen['errores'])}"
        )
    app.register_blueprint(admin_usuarios_bp)   
    
    return app
