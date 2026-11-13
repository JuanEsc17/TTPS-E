"""Configuracion de fixtures de pytest para tests del sistema."""
import pytest
from flask import Flask
from flask.testing import FlaskClient
from src import create_app
from src.core.database import db
from src.core.models.base import Base


@pytest.fixture
def app() -> Flask:
    """Fixture que crea una aplicacion Flask configurada para testing en memoria."""
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })

    with application.app_context():
        Base.metadata.create_all(db.engine)
        yield application
        Base.metadata.drop_all(db.engine)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Fixture para emitir peticiones HTTP simuladas contra la app."""
    return app.test_client()


@pytest.fixture
def session(app: Flask):
    """Fixture que provee la sesion de SQLAlchemy para insertar datos en tests."""
    with app.app_context():
        yield db.session
