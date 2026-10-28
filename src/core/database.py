from flask_sqlalchemy_lite import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

db = SQLAlchemy()


def init_app(app):
    db.init_app(app)
    return db


class BaseModel(DeclarativeBase):
    """
    Base model for all models.
    """
    __abstract__ = True


def create_tables():
    # Importar el paquete registra todos los modelos en BaseModel.metadata
    from src.core import models  # noqa: F401

    BaseModel.metadata.create_all(db.engine)


def reset_db():
    from src.core import models  # noqa: F401

    BaseModel.metadata.drop_all(db.engine)
    BaseModel.metadata.create_all(db.engine)
