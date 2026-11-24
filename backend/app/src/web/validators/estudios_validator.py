"""Esquemas Marshmallow para alta de estudios de exoma (Escenario 2)."""
from marshmallow import EXCLUDE, Schema, fields


class AltaEstudioSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    paciente_id = fields.Int(required=True, strict=True)
    patologia_sospechada_id = fields.Int(required=True, strict=True)
    quiere_hallazgos_secundarios = fields.Bool(required=False, load_default=False)
    obra_social_id = fields.Int(required=False, allow_none=True, load_default=None, strict=True)
    genes_patologia_simbolos = fields.List(fields.Str(), required=False, load_default=list)
    genes_manuales_simbolos = fields.List(fields.Str(), required=False, load_default=list)