"""Esquemas Marshmallow para el flujo de analisis bioinformatico (Escenario 15)."""
from marshmallow import EXCLUDE, Schema, fields


class CargaDatosCrudosSchema(Schema):
    """Valida el cuerpo JSON opcional para carga de datos crudos ACTG."""

    class Meta:
        unknown = EXCLUDE

    nombre_archivo = fields.Str(required=False, allow_none=True, load_default=None)
    contenido_actg = fields.Str(required=False, allow_none=True, load_default="")


class RegistroAnalisisSchema(Schema):
    """Valida la lista de variantes seleccionadas al finalizar el analisis."""

    class Meta:
        unknown = EXCLUDE

    variantes_ids = fields.List(
        fields.Int(strict=True),
        required=True,
        allow_none=False,
    )
