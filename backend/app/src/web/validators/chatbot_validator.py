"""Esquemas Marshmallow para consultas al chatbot sobre patologias."""
from marshmallow import EXCLUDE, Schema, fields


class ConsultaChatbotSchema(Schema):
    """Valida los tipos de entrada de una consulta al chatbot (Escenario 25)."""

    class Meta:
        unknown = EXCLUDE

    pregunta = fields.Str(allow_none=True, load_default="")
    patologia_id = fields.Int(strict=True, required=False, allow_none=True, load_default=None)
    conversacion_id = fields.Str(required=False, allow_none=True, load_default=None)
