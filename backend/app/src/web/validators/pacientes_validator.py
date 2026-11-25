"""Esquemas Marshmallow para alta de pacientes (Escenarios 1 y 19)."""
from marshmallow import EXCLUDE, Schema, fields, pre_load, validate


class FamiliarInputSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    parentesco = fields.Str(required=True, validate=validate.Length(min=1, max=60))
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=150))
    diagnostico_previo = fields.Str(required=False, allow_none=True, load_default=None)
    sintomas_snomed_ids = fields.List(fields.Str(), required=False, load_default=list)
    dni = fields.Str(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Regexp(r"^\d{7,10}$", error="El DNI del familiar debe tener entre 7 y 10 digitos numericos."),
    )

class AltaPacienteSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    dni = fields.Str(
        required=True,
        validate=validate.Regexp(r"^\d{7,10}$", error="El DNI debe tener entre 7 y 10 digitos numericos."),
    )
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    apellido = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    telefono = fields.Str(required=True, validate=validate.Length(min=1, max=30))
    email = fields.Email(required=True)
    fecha_nacimiento = fields.Date(required=True)
    diagnostico_presuntivo_id = fields.Int(required=True, strict=True)
    historia_clinica = fields.Str(required=True, validate=validate.Length(min=1))
    tipo_sospecha = fields.Str(
        required=True,
        validate=validate.OneOf(["clinica", "familiar"]),
    )
    responsable_nombre = fields.Str(required=False, allow_none=True, load_default=None)
    responsable_dni = fields.Str(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Regexp(r"^\d{7,10}$", error="El DNI del responsable debe tener entre 7 y 10 digitos numericos."),
    )
    sintomas_snomed_ids = fields.List(
        fields.Str(),
        required=True,
        validate=validate.Length(min=1),
    )
    sin_informacion_familiar = fields.Bool(required=False, load_default=False)
    familiares = fields.List(fields.Nested(FamiliarInputSchema), required=False, load_default=list)

    @pre_load
    def normalizar(self, data: dict, **kwargs: object) -> dict:
        if not isinstance(data, dict):
            return data
        limpio = dict(data)
        for campo in ("dni", "nombre", "apellido", "telefono", "email", "historia_clinica", "tipo_sospecha"):
            if isinstance(limpio.get(campo), str):
                limpio[campo] = limpio[campo].strip()
        return limpio

class GestionarFamiliaresSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    familiares = fields.List(fields.Nested(FamiliarInputSchema), required=True)


class AutorizarMedicosSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    medicos_ids = fields.List(fields.Int(strict=True), required=True)
    motivo = fields.Str(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Length(max=500),
    )

    @pre_load
    def normalizar(self, data: dict, **kwargs: object) -> dict:
        if not isinstance(data, dict):
            return data
        limpio = dict(data)
        if isinstance(limpio.get("motivo"), str):
            limpio["motivo"] = limpio["motivo"].strip() or None
        return limpio


class RevocarAutorizacionSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    motivo = fields.Str(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Length(max=500),
    )

    @pre_load
    def normalizar(self, data: dict, **kwargs: object) -> dict:
        if not isinstance(data, dict):
            return data
        limpio = dict(data)
        if isinstance(limpio.get("motivo"), str):
            limpio["motivo"] = limpio["motivo"].strip() or None
        return limpio