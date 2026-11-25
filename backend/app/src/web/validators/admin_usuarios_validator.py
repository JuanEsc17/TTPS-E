"""Esquemas Marshmallow para endpoints del admin general."""
from marshmallow import EXCLUDE, Schema, fields, pre_load


class RegistroUsuarioPorAdminSchema(Schema):
    class Meta:
        unknown = EXCLUDE  # si mandan en el json rol: admin general, lo ignora y no da error de validacion
    nombre = fields.Str(required=True)
    apellido = fields.Str(required=True)
    telefono = fields.Str(required=True)
    email = fields.Str(required=True)
    password = fields.Str(required=True)

    @pre_load
    def normalizar_datos(self, data, **kwargs):
        """ Normaliza los datos de entrada: quita espacios al inicio y final de los strings."""
        if not isinstance(data, dict):
            return data
        limpio = dict(data)
        for campo in ("nombre", "apellido", "telefono", "email", "matricula"):
            if isinstance(limpio.get(campo), str):
                limpio[campo] = limpio[campo].strip()
        return limpio

class RegistroGerenteMedicoSchema(RegistroUsuarioPorAdminSchema):
    class Meta:
        unknown = EXCLUDE  # si mandan en el json rol: admin general, lo ignora y no da error de validacion
    matricula = fields.Str(required=True)
    especialidades_ids = fields.List(fields.Int(strict=True), required=True)

class RegistroAdministrativoSchema(RegistroUsuarioPorAdminSchema):
    pass