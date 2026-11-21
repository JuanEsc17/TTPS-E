"""Esquemas Marshmallow para el flujo de analisis bioinformatico y reanalisis (Escenarios 15 y 17)."""
from marshmallow import EXCLUDE, Schema, fields, validate


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


class SolicitudReanalisisSchema(Schema):
    """Valida la solicitud de reanalisis de un estudio con nuevos genes (Escenario 17)."""

    class Meta:
        unknown = EXCLUDE

    nuevos_genes_simbolos = fields.List(
        fields.Str(),
        required=False,
        allow_none=False,
        load_default=list,
    )
    genes_ids = fields.List(
        fields.Int(strict=True, validate=validate.Range(min=1)),
        required=False,
        allow_none=False,
        load_default=list,
    )
    nueva_patologia_sospechada_id = fields.Int(
        strict=True,
        validate=validate.Range(min=1),
        required=False,
        allow_none=True,
        load_default=None,
    )
