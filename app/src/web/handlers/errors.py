"""Manejadores globales de excepciones y respuestas de error HTTP."""
from flask import Flask, jsonify
from marshmallow import ValidationError
from src.core.services.excepciones import ErrorDominio


def registrar_manejadores_errores(app: Flask) -> None:
    @app.errorhandler(ErrorDominio)
    def manejar_error_dominio(exc: ErrorDominio):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": exc.mensaje,
                    "code": exc.codigo,
                    "retryable": exc.reintentable,
                }
            ),
            exc.http_status
        )
    
    @app.errorhandler(ValidationError)
    def manejar_error_validacion(exc: ValidationError):
        return (
            jsonify(
                {
                    "ok:":False,
                    "error": "Los datos enviados son invalidos o estan incompletos.",
                    "code": "DATOS_INVALIDOS",
                    "retryable": False,
                    "detalles": exc.messages,
                }
            ),
            400,
        )