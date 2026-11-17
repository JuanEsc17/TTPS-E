"""Esquemas Marshmallow para endpoints de medicos y especialidades."""
from marshmallow import EXCLUDE, Schema, fields, pre_load


class RegistroMedicoSchema(Schema):
    class Meta:
        # Ignora campos extra no declarados (ej. evita que inyecten "rol": "gerente_medico")
        unknown = EXCLUDE

    nombre = fields.Str(required=True)
    apellido = fields.Str(required=True)
    # Se valida como string porque incluye prefijos/guiones (ej. "+5492214448899")
    telefono = fields.Str(required=True)
    email = fields.Str(required=True)
    password = fields.Str(required=True)
    matricula = fields.Str(required=True)
    # strict=True evita que acepte strings/booleans como enteros (ej. "1" o True)
    especialidades_ids = fields.List(fields.Int(strict=True), required=True)
    dispositivo_identificador = fields.Str(
        required=False,
        allow_none=True,
        load_default=None,
    )

    @pre_load
    def normalizar_campos(self, data: dict, **kwargs: object) -> dict:
        # Se ejecuta antes de validar: quita espacios al inicio/fin de los textos
        if not isinstance(data, dict):
            return data
        limpio = dict(data)
        for campo in ("nombre", "apellido", "telefono", "email", "matricula", "dispositivo_identificador"):
            if isinstance(limpio.get(campo), str):
                limpio[campo] = limpio[campo].strip()
        return limpio