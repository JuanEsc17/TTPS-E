"""Esquemas Marshmallow para gestion de patologias y busqueda SNOMED."""
from marshmallow import Schema, fields


class SintomaPatologiaSchema(Schema):
    snomed_id = fields.Str(allow_none=True, load_default="")
    descripcion = fields.Str(allow_none=True, load_default="")


class PatologiaSchema(Schema):
    nombre = fields.Str(allow_none=True, load_default="")
    descripcion = fields.Str(allow_none=True, load_default=None)
    sintoma_cardinal = fields.Nested(SintomaPatologiaSchema, allow_none=True, load_default=None)
    sintomas_secundarios = fields.List(fields.Nested(SintomaPatologiaSchema), allow_none=True, load_default=list)
