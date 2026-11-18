from flask_sqlalchemy_lite import SQLAlchemy

from .models.base import Base

db = SQLAlchemy()


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
