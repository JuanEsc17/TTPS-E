# ADR-002: Autorización Múltiple de Médicos sobre Historia Clínica y Vinculación Automática de Estudios Familiares

## Status
Accepted (2026-11-17)

## Context
El diseño original contemplaba una relación `1:N` única (`pacientes.medico_id`) para definir qué médico podía ver la historia clínica del paciente, y registraba `Familiar` en el familiograma únicamente como texto descriptivo (`nombre`, `parentesco`, `diagnostico_previo`) sin vínculo relacional con otros pacientes o estudios del sistema.

Los nuevos requerimientos establecen:
1. El **paciente** puede agregar a varios **médicos** para que tengan autorización para ver su **historia clínica**.
2. Si un **familiar** presente en el **familiograma** se realiza un estudio, automáticamente debe vincularse con la tabla de estudios del paciente original, y el **médico** debe poder ver desde el estudio de `X` el estudio del familiar `X'`.

## Decision
1. **Autorización múltiple de historia clínica (`pacientes_medicos_autorizados`):**
   - Se conserva `pacientes.medico_id` como referencia histórica al médico derivante que dio de alta al paciente.
   - Se introduce la tabla `pacientes_medicos_autorizados` con estado lógico (`activa`, `otorgada_en`, `revocada_en`) e índice único parcial `uq_paciente_medico_activo(paciente_id, medico_id) WHERE activa`.
   - Al dar de alta al paciente (Escenario 1), se inserta automáticamente la autorización inicial para el médico derivante. Posteriormente el paciente puede agregar o revocar autorización a múltiples médicos (Escenario 40).
   - **Trade-off considerado:** Se descartó almacenar una lista de IDs en un array JSON sobre `pacientes` por perder integridad referencial con `medicos`, dificultar consultas inversas ("¿de qué pacientes tengo historia clínica autorizada?") y perder trazabilidad temporal de otorgamientos/revocaciones.

2. **Vinculación automática de estudios familiares (`familiares.dni` + `familiares.paciente_vinculado_id` + `estudios_familiares_vinculados`):**
   - Se agregan `apellido`, `dni` (nullable, indexado) y `paciente_vinculado_id` (FK nullable a `pacientes.id`) en `familiares`.
   - Se crea la tabla asociativa simétrica `estudios_familiares_vinculados(estudio_origen_id, estudio_relacionado_id, familiar_id, parentesco)`.
   - Al crear un paciente, actualizar sus familiares o dar de alta un estudio, el servicio busca coincidencias determinísticas por `dni` (`Familiar.dni == Paciente.dni`) o vínculo existente (`Familiar.paciente_vinculado_id == Paciente.id`) y crea automáticamente los registros de vinculación entre todos los estudios del paciente original y los estudios del familiar.
   - **Trade-off considerado:** Se descartó vincular automáticamente solo por `nombre` (cadena libre), ya que homónimos generarían falsos positivos graves con filtración de datos genéticos sensibles. Si `Familiar.dni` no fue cargado originalmente, se ofrece vinculación asistida confirmada por el médico, mientras que con `dni` la vinculación es 100% automática.
   - **Seguridad:** Cuando un médico autorizado consulta el estudio `X`, recibe acceso de solo lectura contextual hacia el estudio familiar `X'` vinculado a través de la relación explícita en `estudios_familiares_vinculados`, quedando auditable cada acceso y vínculo.

## Consequences
- **Positivas:** Control de acceso granular y uniforme sobre `historia_clinica`; trazabilidad genealógica directa entre estudios de familiares desde la vista médica sin duplicar información clínica.
- **Negativas / Trade-offs:** Exige que el formulario de familiares promueva la carga del `dni` cuando el paciente lo conozca para garantizar la vinculación 100% automática.
