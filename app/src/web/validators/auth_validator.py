"""Esquemas Marshmallow para endpoints de autenticacion."""
from marshmallow import Schema, fields, pre_load, validate


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=1))
    dispositivo_identificador = fields.Str(
        required=True,
        validate=validate.Regexp(r"\S", error="No puede estar vacio."),
    )

    @pre_load
    def normalizar_campos(self, data: dict, **kwargs: object) -> dict:
        if not isinstance(data, dict):
            return data
        limpio = dict(data)
        for campo in ("email", "dispositivo_identificador"):
            if isinstance(limpio.get(campo), str):
                limpio[campo] = limpio[campo].strip()
        return limpio
    
class CambiarPasswordInicialSchema(Schema):
    password_inicial = fields.Str(required=True, validate=validate.Length(min=1))
    nueva_password = fields.Str(required=True, validate=validate.Length(min=1))
    confirmacion_password = fields.Str(required=True, validate=validate.Length(min=1))
    dispositivo_identificador = fields.Str(
        required=True,
        validate=validate.Regexp(r"\S", error="No puede estar vacio.")
    )

    @pre_load
    def normalizar_dispositivo(self, data:dict, **kwargs:object) -> dict:
        if isinstance(data, dict) and isinstance(data.get("dispositivo_identificador"), str):
            return {**data, "dispositivo_identificador": data["dispositivo_identificador"].strip()}
        return data


class VerificarDispositivoSchema(Schema):
    codigo = fields.Str(
        required=True,
        validate=validate.Regexp(r"^\d{6}$", error="Debe tener exactamente 6 digitos."),
    )
    dispositivo_identificador = fields.Str(
        required=True,
        validate=validate.Regexp(r"\S", error="No puede estar vacio."),
    )

    @pre_load
    def normalizar(self, data: dict, **kwargs: object) -> dict:
        if not isinstance(data, dict):
            return data
        limpio = dict(data)
        for campo in ("codigo", "dispositivo_identificador"):
            if isinstance(limpio.get(campo), str):
                limpio[campo] = limpio[campo].strip()
        return limpio


class ReenviarCodigoSchema(Schema):
    dispositivo_identificador = fields.Str(
        required=True,
        validate=validate.Regexp(r"\S", error="No puede estar vacio."),
    )

    @pre_load
    def normalizar(self, data: dict, **kwargs: object) -> dict:
        if isinstance(data, dict) and isinstance(data.get("dispositivo_identificador"), str):
            return {**data, "dispositivo_identificador": data["dispositivo_identificador"].strip()}
        return data