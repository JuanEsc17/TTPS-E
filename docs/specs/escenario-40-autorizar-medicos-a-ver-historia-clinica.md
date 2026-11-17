# WORKFLOW: Escenario 40 – Autorizar médicos para ver la historia clínica
**Versión**: 1.0
**Fecha**: 2026-11-17
**Autor**: Workflow Architect & Software Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-40`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Paciente`, `Médico` |
| **Objetos** | `Historia clínica`, `Autorización de historia clínica`, `Registro de modificaciones`, `Aviso` |
| **Verbos** | `Autorizar médico a historia clínica`, `Registrar modificación` |
| **Estados** | *(No modifica `EstadoEstudio`; gestiona el estado lógico `activa` en `pacientes_medicos_autorizados`)* |

---

## Overview

- **Objetivo**: Permitir al `Paciente` agregar a varios `Médicos` para que cuenten con **autorización de historia clínica**, revocar autorizaciones otorgadas y habilitar que cualquier `Médico` autorizado consulte la **historia clínica** del paciente en el sistema.
- **Contexto**: Originalmente cada `Paciente` quedaba asociado únicamente al `Médico` derivante que realizó su alta (`pacientes.medico_id`), impidiendo que interconsultores u otros especialistas accedieran a su historia clínica. Con el nuevo requerimiento (ADR-002), el `Paciente` mantiene control explícito mediante la tabla `pacientes_medicos_autorizados`, sembrada automáticamente para el médico de alta al crear al paciente (Escenarios 18/19) y extensible a múltiples médicos.
- **Recursos**: `Paciente` (`pacientes`), `Médico` (`medicos`), `Autorización de historia clínica` (`pacientes_medicos_autorizados`), `Registro de modificaciones` (`registro_modificaciones`), `Aviso` (`avisos`).
- **Episodios**:
  1. El `Paciente` consulta el directorio de `Médicos` registrados en el sistema (con especialidad, nombre y matrícula).
  2. El `Paciente` selecciona uno o varios `Médicos` y les otorga **autorización de historia clínica** (o revoca una existente).
  3. El sistema persiste la autorización en `pacientes_medicos_autorizados`, registra el cambio en `registro_modificaciones` (`entidad_tipo = 'paciente'`) y notifica al `Médico` mediante un `Aviso`.
  4. El `Médico` autorizado accede al sistema y visualiza la **historia clínica** y perfil clínico del `Paciente`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` | Selecciona múltiples médicos a autorizar y revoca permisos cuando lo considere necesario. |
| `Médico` | Recibe la notificación de autorización y consulta la `Historia clínica` del paciente autorizado. |
| `router` (`pacientes_router`, `medicos_router`) | Expone endpoints REST para listar médicos, otorgar/revocar autorizaciones y consultar la historia clínica. |
| `service` (`paciente_service`, `medico_service`, `auditoria_service`) | Verifica roles y titularidad, aplica idempotencia en autorizaciones, registra auditoría y emite avisos. |
| `repo` (`paciente_repo`, `medico_repo`, `auditoria_repo`, `usuario_repo`) | Opera sobre `pacientes_medicos_autorizados`, `pacientes`, `medicos`, `registro_modificaciones` y `avisos`. |

---

## Prerequisites

- Para otorgar, listar propias o revocar autorizaciones: usuario autenticado con `Rol.PACIENTE` vinculado a un registro activo en `pacientes`.
- Los `medico_id` indicados deben corresponder a filas válidas en `medicos` con usuario habilitado (`usuarios.activo == True`).
- Para consultar historia clínica: usuario autenticado con `Rol.MEDICO` (o `Rol.GERENTE_MEDICO` dentro del alcance de médico tratante) con vínculo activo en `pacientes_medicos_autorizados` (`activa == True`), o titularidad inicial en `pacientes.medico_id` solo en compatibilidad con registros anteriores a la migración.

---

## Trigger

1. **Directorio de médicos**: `GET /api/v1/medicos?q=&especialidad_id=` (autenticado como `Paciente`).
2. **Listar médicos autorizados**: `GET /api/v1/pacientes/mi-perfil/medicos-autorizados` (autenticado como `Paciente`).
3. **Otorgar autorización múltiple**: `POST /api/v1/pacientes/mi-perfil/medicos-autorizados` (autenticado como `Paciente`).
4. **Revocar autorización**: `DELETE /api/v1/pacientes/mi-perfil/medicos-autorizados/{medico_id}` (autenticado como `Paciente`).
5. **Consultar historia clínica por médico**: `GET /api/v1/pacientes/{paciente_id}/historia-clinica` (autenticado como `Médico`).

---

## Workflow Tree

### STEP 1: Consulta del directorio de `Médicos` disponibles y estado actual
**Actor**: `Paciente` -> `router` -> `service` (`medico_service`) -> `repo` (`medico_repo`, `paciente_repo`)
**Action**:
1. Verifica que el usuario autenticado tenga `Rol.PACIENTE`.
2. Consulta el listado de `Médicos` habilitados (`medicos JOIN usuarios`) junto con sus `especialidades`, excluyendo credenciales sensibles.
3. Marca en la respuesta qué `Médicos` ya poseen fila con `activa == True` en `pacientes_medicos_autorizados` para ese `Paciente`.
**Timeout**: `2s`
**Input**: `usuario_actual`, filtros opcionales `q`, `especialidad_id`.
**Output on SUCCESS**: `{ medicos: [...], medicos_autorizados_activos_ids: [...] }` -> `200 OK`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Rol distinto de `PACIENTE` en el directorio del portal de paciente -> `return 403 Forbidden`.

**Observable states during this step**:
  - **Paciente sees**: Buscador de médicos con nombre, apellido, especialidades, matrícula e indicador de `"Autorizado"` / `"Sin autorización"`.
  - **Database**: Consulta de solo lectura sobre `medicos`, `usuarios`, `medicos_especialidades`, `especialidades` y `pacientes_medicos_autorizados`.
  - **Logs**: `[paciente_service] STEP 1 directorio_medicos_consultado paciente_id=<pid>`

---

### STEP 2: Validación y otorgamiento de autorizaciones a múltiples `Médicos`
**Actor**: `Paciente` -> `router` -> `service` (`paciente_service`, `auditoria_service`) -> `repo` (`paciente_repo`, `medico_repo`, `auditoria_repo`, `usuario_repo`)
**Action**:
1. Valida el payload `{ medicos_ids: list[int], motivo?: str }` (debe contener al menos 1 `medico_id` único).
2. Verifica que todos los `medico_id` existan en `medicos` con usuario activo.
3. Bloquea el registro `Paciente` (`SELECT ... FOR UPDATE`) y obtiene sus autorizaciones activas actuales (`activa == True`).
4. Por cada `medico_id` de `medicos_ids`:
   - Si ya existe fila con `activa == True`: se trata de forma idempotente (no duplica fila gracias al índice único parcial `uq_paciente_medico_activo`).
   - Si no existe autorización activa: inserta en `pacientes_medicos_autorizados` (`paciente_id`, `medico_id`, `otorgada_por_usuario_id = usuario_actual.id`, `activa = True`, `otorgada_en = func.now()`, `revocada_en = None`).
5. Si se otorgó al menos una nueva autorización:
   - Invoca `AuditoriaService.registrar_modificacion(...)` en la misma transacción:
     - `entidad_tipo = EntidadAuditable.PACIENTE`, `entidad_id = paciente.id`, `accion = TipoAccionAuditoria.MODIFICACION`, `usuario_id = usuario_actual.id`, `origen = 'usuario'`
     - `cambios = {"medicos_autorizados_ids": {"anterior": ids_anteriores, "nuevo": ids_finales}}`
     - `motivo = input.motivo or "Autorización de médicos por paciente"`
   - Inserta un `Aviso` para cada `Médico` recién autorizado (`"El paciente <Nombre Apellido> le otorgó autorización para consultar su historia clínica."`).
6. Ejecuta `COMMIT`.
**Timeout**: `3s`
**Input**: `{ medicos_ids: [3, 7], motivo: "Interconsulta hematológica" }`, `usuario_actual`.
**Output on SUCCESS**: `200 OK` / `201 Created` con lista actualizada de autorizaciones activas -> `Paciente` ve confirmación; `Médico` ve `Aviso`.
**Output on FAILURE**:
  - `FAILURE(validation_error)`: `medicos_ids` vacío -> `return 422 Unprocessable Entity` (`LISTA_MEDICOS_VACIA`).
  - `FAILURE(medico_not_found)`: Algún `medico_id` no existe o está inactivo -> `ROLLBACK` y `return 404 Not Found` (`MEDICO_NO_ENCONTRADO`).

**Observable states during this step**:
  - **Paciente sees**: Confirmación `"Se autorizó a N médico(s) a visualizar su historia clínica."` y tarjetas actualizadas.
  - **Médico sees**: Nuevo `Aviso` no leído y aparición del paciente en su listado de `"Pacientes autorizados"`.
  - **Database**: Nuevas filas en `pacientes_medicos_autorizados`, `registro_modificaciones` y `avisos`.
  - **Logs**: `[paciente_service] STEP 2 medicos_autorizados paciente_id=<pid> nuevos=<ids>`

---

### STEP 3: Revocación de autorización a un `Médico`
**Actor**: `Paciente` -> `router` -> `service` (`paciente_service`, `auditoria_service`) -> `repo`
**Action**:
1. Verifica que exista fila en `pacientes_medicos_autorizados` con `paciente_id == paciente.id`, `medico_id == medico_id` y `activa == True` (bloqueo `FOR UPDATE`).
2. Actualiza la fila conservando trazabilidad histórica:
   - `activa = False`
   - `revocada_en = func.now()`
3. Registra en `registro_modificaciones`:
   - `entidad_tipo = EntidadAuditable.PACIENTE`, `entidad_id = paciente.id`, `accion = TipoAccionAuditoria.MODIFICACION`
   - `cambios = {"medicos_autorizados_ids": {"anterior": ids_anteriores, "nuevo": ids_finales}}`
   - `motivo = input.motivo or "Revocación de autorización de historia clínica"`
4. Inserta un `Aviso` informando al `Médico` que su permiso de lectura sobre ese paciente fue revocado y ejecuta `COMMIT`.
**Timeout**: `3s`
**Input**: `medico_id`, opcional `motivo`, `usuario_actual`.
**Output on SUCCESS**: `200 OK` con estado revocado e historial actualizado.
**Output on FAILURE**:
  - `FAILURE(not_found)`: No existe autorización activa para ese `(paciente_id, medico_id)` -> `return 404 Not Found` (`AUTORIZACION_NO_ACTIVA`).

**Observable states during this step**:
  - **Paciente sees**: El médico pasa a estado no autorizado; conserva fecha histórica si se consulta auditoría.
  - **Médico sees**: El paciente desaparece de su acceso a historia clínica y recibe aviso.
  - **Database**: `pacientes_medicos_autorizados.activa = False`, `revocada_en != NULL`; nueva fila en `registro_modificaciones`.
  - **Logs**: `[paciente_service] STEP 3 autorizacion_revocada paciente_id=<pid> medico_id=<mid>`

---

### STEP 4: Consulta de la `Historia clínica` por un `Médico` autorizado
**Actor**: `Médico` -> `router` -> `service` (`paciente_service`) -> `repo` (`paciente_repo`)
**Action**:
1. Verifica `Rol.MEDICO` (o `Rol.GERENTE_MEDICO`) y obtiene su `medico.id`.
2. Consulta `pacientes_medicos_autorizados` buscando `paciente_id == paciente.id AND medico_id == medico.id AND activa == True`.
   - *(Compatibilidad transitoria durante migración de datos históricos sin filas sembradas: solo si la tabla `pacientes_medicos_autorizados` no posee ningún registro para `paciente_id`, se acepta temporalmente `paciente.medico_id == medico.id`.)*
3. Si está autorizado, retorna `paciente.historia_clinica`, datos clínicos básicos (`diagnostico_presuntivo`, `tipo_sospecha`, `sintomas`, `familiares`, `familiograma_pdf_path`) y la nómina de otros médicos actualmente autorizados si corresponde al portal médico.
**Timeout**: `2s`
**Input**: `paciente_id`, `usuario_actual`.
**Output on SUCCESS**: `200 OK` con la `Historia clínica` completa -> END WORKFLOW.
**Output on FAILURE**:
  - `FAILURE(not_found)`: `paciente_id` inexistente -> `return 404 Not Found`.
  - `FAILURE(forbidden)`: El `Médico` no posee fila `activa == True` en `pacientes_medicos_autorizados` (incluye el caso en que haya sido revocada) -> `return 403 Forbidden` (`HISTORIA_CLINICA_NO_AUTORIZADA`).

**Observable states during this step**:
  - **Médico autorizado sees**: Historia clínica transcrita/editada, síntomas SNOMED, patología sospechada y familiograma.
  - **Médico no autorizado / revocado sees**: Pantalla de acceso denegado (`403 Forbidden`).
  - **Database**: Lectura sobre `pacientes_medicos_autorizados`, `pacientes` y tablas clínicas asociadas.
  - **Logs**: `[paciente_service] STEP 4 historia_clinica_consultada paciente_id=<pid> medico_id=<mid>`

---

## State Transitions

*(Este workflow no altera los 14 valores de `EstadoEstudio`; gobierna el ciclo de vida de `PacienteMedicoAutorizado.activa`)*

| Estado Origen | Trigger / Acción | Estado Destino | Auditoría Obligatoria |
|---|---|---|---|
| *(Sin autorización)* | Alta de paciente (Esc. 18/19) | `activa = True` (para `paciente.medico_id`) | `registro_modificaciones` (`paciente`, alta) |
| `activa = False` / inexistente | `POST .../medicos-autorizados` | `activa = True`, `revocada_en = NULL` *(nueva fila si existía revocada previa)* | `registro_modificaciones` (`paciente`, `modificacion`) |
| `activa = True` | `DELETE .../medicos-autorizados/{medico_id}` | `activa = False`, `revocada_en = now()` | `registro_modificaciones` (`paciente`, `modificacion`) |

---

## Handoff Contracts

| Origen | Destino | Payload / Garantía |
|---|---|---|
| Escenario 18 / 19 (Alta de paciente) | `pacientes_medicos_autorizados` | Siembra automáticamente fila `activa = True` para el médico tratante que realiza el alta. |
| Escenario 40 (Autorización múltiple) | Escenario 01 / Escenario 35 / Escenario 37 | Todo médico con `activa == True` puede consultar la historia clínica, grabar/actualizar historia clínica (Esc. 35) y acceder a estudios del paciente según permisos clínicos. |
| Escenario 40 | Escenario 42 (`Registro de modificaciones`) | Cada otorgamiento y revocación queda asentado con el usuario `Paciente` responsable y la lista anterior/nueva de `medicos_autorizados_ids`. |

---

## Cleanup Inventory

- Índice único parcial `uq_paciente_medico_activo(paciente_id, medico_id) WHERE activa` impide condiciones de carrera si el paciente hace doble clic al autorizar el mismo médico simultáneamente.
- La revocación realiza baja lógica (`activa = False`, `revocada_en = now()`) en lugar de `DELETE`, preservando historial completo para auditoría clínica.

---

## Reality Checker Findings

- **Existente en código (`app/src/core/models/perfiles.py`)**: Actualmente `Paciente` solo tiene `medico_id: Mapped[int]` (relación 1:N fija). No existe la tabla ni el modelo `PacienteMedicoAutorizado`.
- **Existente en código (`app/src/core/services/medico_service.py` y `app/src/web/api/medicos.py`)**: El acceso a pacientes y actualización de datos está acoplado a `paciente.medico_id == medico.id` (sin validar `pacientes_medicos_autorizados`).
- **Pendiente de implementación**: Migración Alembic de `pacientes_medicos_autorizados` (con backfill `INSERT INTO pacientes_medicos_autorizados` para pacientes ya existentes a partir de `pacientes.medico_id`), repositorio/servicio y endpoints del portal de paciente.

---

## Test Cases

1. **TC-01 (Autorización múltiple simultánea)**: Paciente autenticado envía `POST .../medicos-autorizados` con `[medico_2_id, medico_3_id]`; ambos obtienen fila `activa = True`, se crea 1 registro en `registro_modificaciones` con `medicos_autorizados_ids`, ambos médicos reciben `Aviso` y ambos obtienen `200 OK` en `GET /api/v1/pacientes/{id}/historia-clinica`.
2. **TC-02 (Idempotencia ante médico ya autorizado)**: Paciente vuelve a enviar `[medico_2_id]`; el sistema retorna `200 OK` sin violar `uq_paciente_medico_activo` ni duplicar filas activas.
3. **TC-03 (Revocación y bloqueo inmediato)**: Paciente revoca a `medico_2_id` (`DELETE .../medicos-autorizados/{medico_2_id}`); la fila pasa a `activa = False` con `revocada_en != NULL`, se audita en `registro_modificaciones`, y una consulta posterior de `medico_2` recibe `403 Forbidden`.
4. **TC-04 (Re-autorización histórica)**: Paciente vuelve a autorizar a `medico_2_id` después de haberlo revocado; se inserta una nueva fila con `activa = True` manteniendo intacta la fila revocada anterior.
5. **TC-05 (Médico no autorizado)**: Un médico `medico_4` sin fila activa intenta consultar `GET /api/v1/pacientes/{id}/historia-clinica`; recibe `403 Forbidden`.
6. **TC-06 (Propiedad del perfil)**: Un paciente `P2` intenta revocar o agregar médicos usando IDs ajenos o endpoints de otro perfil; solo opera sobre su propio `paciente_id` derivado del token JWT.

---

## Assumptions

- Los `Paciente` ven en el directorio únicamente datos profesionales públicos de los `Médicos` (nombre completo, matrícula, especialidades), nunca sus correos privados, teléfonos personales ni métricas de pacientes atendidos.
- Cuando se revoca una autorización, la consulta de historia clínica se bloquea de inmediato para ese médico; si ese médico hubiera solicitado un estudio previo mientras estuvo autorizado, el enlace específico del estudio puede revisarse según política en Open Questions.

---

## Open Questions

- ¿El `Paciente` puede revocar también la autorización del médico derivante original (`pacientes.medico_id`) o este último debe conservar acceso de solo lectura mientras exista al menos un `Estudio` en curso solicitado por él? *(Recomendado: permitir revocar en `pacientes_medicos_autorizados` por principio de autonomía del paciente, manteniendo trazabilidad de quién solicitó cada estudio).*
- ¿El médico autorizado por un paciente para ver su `Historia clínica` también queda habilitado automáticamente para solicitarle un nuevo `Estudio` (Escenario 01) o solo lectura/interconsulta de historia clínica y estudios vinculados?

---

## Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-11-17 | Especificación creada para el Requerimiento 2 y ADR-002 (autorización de múltiples médicos a historia clínica). | Aprobada para guiar futura migración, servicio y UI de paciente/médico. |
