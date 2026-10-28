# WORKFLOW: Escenario 8 – Cancelar un turno de extracción
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-8`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Paciente`, `Médico` *(explícitamente prohibido en el LEL: "El médico no puede cancelar un turno")* |
| **Objetos** | `Turno`, `Centro de extracción`, `Estudio`, `Aviso` |
| **Verbos** | `Cancelar turno`, `Sacar turno` *(habilitado nuevamente tras cancelar)* |
| **Estados** | `Turno sacado`, `Autorizado`, `Creado`, `Remuestreo requerido` |

---

## Overview

- **Objetivo**: Permitir al `Paciente` cancelar un `Turno` de extracción previamente asignado antes de que se tome la `Muestra`, liberando el horario de 15 minutos en el `Centro de extracción` (`Turno.activo = False`) sin computar ausencia y permitiendo que el `Paciente` pueda volver a `Sacar turno`.
- **Contexto**: El `Paciente` tiene un `Turno` de extracción registrado y activo (`Turno.activo == True`, `Turno.asistio is None`) y su `Estudio` se encuentra en estado `Turno sacado` (`EstadoEstudio.TURNO_SACADO`). Por definición estricta del LEL (`Sujeto: Médico` y `Verbo: Cancelar turno`), **solo el `Paciente`** puede cancelar el `Turno`; el `Médico` (ni otros roles) no puede cancelar un `Turno`.
- **Recursos**: `Turno` de extracción (`turno_id`), `Estudio` asociado (`estudio_id`).
- **Episodios**:
  1. El `Paciente` solicita cancelar su `Turno` de extracción activo.
  2. El sistema valida que quien solicita la cancelación sea el `Paciente` titular, que el `Turno` esté activo y que la `Muestra` aún no haya sido tomada, y registra la cancelación marcando `Turno.activo = False` (sin incrementar `estudio.ausencias`).
  3. El sistema restaura el `Estudio` a su estado habilitado previo (`Autorizado` si fue autorizado por obra social, `Remuestreo requerido` si proviene de un remuestreo, o `Creado` con pago vigente si fue pago particular) para que el `Paciente` pueda solicitar un nuevo `Turno` (Escenario 7), y el slot liberado vuelve a estar disponible en el `Centro de extracción`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` | Único Sujeto LEL autorizado a ejecutar `Cancelar turno` sobre su propio `Turno` activo. |
| `router` (`turnos_router`) | Capa HTTP Flask (`POST /api/v1/turnos/{turno_id}/cancelar` o `DELETE /api/v1/estudios/{estudio_id}/turnos/{turno_id}`). Verifica sesión y que el rol sea exclusivamente `Rol.PACIENTE`. |
| `service` (`turno_service`) | Capa de negocio que verifica titularidad, comprueba que el turno esté activo y no consumido, marca `turno.activo = False` y determina el estado de retorno del `Estudio`. |
| `repo` (`turno_repo`, `estudio_repo`, `usuario_repo`) | Capa de acceso a datos SQLAlchemy sobre `turnos`, `estudios`, `autorizaciones`, `muestras`, `avisos`. |
| `PostgreSQL` | Base de datos relacional donde al pasar `turnos.activo = False` se libera automáticamente la restricción del índice parcial único `uq_turno_activo`. |

---

## Prerequisites

- El usuario autenticado tiene sesión activa y `Usuario.rol == Rol.PACIENTE` (cualquier intento de un `Médico` u otro rol debe ser rechazado con `403 Forbidden`).
- Existe el `Turno` (`turnos.id == turno_id`) con `turno.activo == True` y `turno.asistio is None`.
- El `Turno` pertenece al `Paciente` autenticado (`turno.paciente.usuario_id == usuario_actual.id`).
- El `Estudio` asociado (`turno.estudio`) se encuentra en `estudio.estado == EstadoEstudio.TURNO_SACADO`.

---

## Trigger

El `Paciente` visualiza su `Turno` vigente en la plataforma y presiona `"Cancelar turno"`:
- **Endpoint HTTP**: `POST /api/v1/turnos/{turno_id}/cancelar` (autenticado con rol `paciente`).

---

## Workflow Tree

### STEP 1: Validación de rol (`Rol.PACIENTE` exclusivo), titularidad y estado activo del `Turno`
**Actor**: `router` (`turnos_router`) -> `service` (`turno_service`) -> `repo` (`turno_repo`, `estudio_repo`)
**Action**:
1. Verifica que `usuario_actual.rol == Rol.PACIENTE`. Si `usuario_actual.rol in (Rol.MEDICO, Rol.GERENTE_MEDICO)` u otro rol, rechaza inmediatamente cumpliendo la regla del LEL (*"El médico no puede cancelar un turno"*).
2. Carga el `Turno` (`turnos.id == turno_id`) y su `Estudio` asociado con `SELECT ... FOR UPDATE`.
3. Verifica que `turno.paciente.usuario_id == usuario_actual.id`.
4. Verifica que `turno.activo == True` y `turno.asistio is None`.
5. Verifica que `estudio.estado == EstadoEstudio.TURNO_SACADO` y que no exista una `Muestra` ya tomada para este `turno_id`.
**Timeout**: `2s`
**Input**: `turno_id`, `usuario_actual`
**Output on SUCCESS**: `Turno` y `Estudio` bloqueados en transacción -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario es un `Médico` (`Rol.MEDICO` / `Rol.GERENTE_MEDICO`), otro rol, o es un `Paciente` distinto del titular del turno -> `return 403 Forbidden` (`{"ok": false, "error": "Solo el paciente titular puede cancelar su turno de extracción. El médico no puede cancelar un turno.", "code": "FORBIDDEN_CANCELAR_TURNO", "retryable": false}`).
  - `FAILURE(not_found)`: `turno_id` no existe -> `return 404 Not Found` (`code: "TURNO_NO_ENCONTRADO"`).
  - `FAILURE(conflict)` / `FAILURE(invalid_state)`: El `Turno` ya estaba cancelado (`turno.activo == False`), o ya fue registrado como asistido/ausente (`turno.asistio is not None`), o el `Estudio` ya avanzó a `Lista para retirar` -> `return 409 Conflict` (`{"ok": false, "error": "El turno ya fue cancelado o ya fue procesado y no puede cancelarse", "code": "TURNO_NO_CANCELABLE", "retryable": false}`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Spinner `"Cancelando turno..."`.
  - **Operator sees**: Solicitud de cancelación en curso.
  - **Database**: Lectura `FOR UPDATE` sobre `turnos` y `estudios`.
  - **Logs**: `[turno_service] STEP 1 cancelar_turno iniciado turno_id=<tid> paciente_id=<pid>`

---

### STEP 2: Registro de la cancelación (`Turno.activo = False`) y restauración de estado del `Estudio`
**Actor**: `service` (`turno_service`) -> `repo` (`turno_repo`, `estudio_repo`, `usuario_repo`) -> `PostgreSQL`
**Action**:
1. Marca `turno.activo = False` (manteniendo `turno.asistio = None` y sin modificar `estudio.ausencias`).
2. Determina el estado habilitado al que retorna el `Estudio` para que el `Paciente` pueda solicitar un nuevo `Turno`:
   - Si el `Estudio` tiene alguna `Muestra` previa descartada (`any(m.motivo_descarte is not None for m in estudio.muestras)` y ninguna muestra vigente) -> `estudio.estado = EstadoEstudio.REMUESTREO_REQUERIDO` (`"Remuestreo requerido"`).
   - De lo contrario, si el `Estudio` tiene una `Autorizacion` con `resultado == ResultadoAutorizacion.AUTORIZADA` -> `estudio.estado = EstadoEstudio.AUTORIZADO` (`"Autorizado"`).
   - De lo contrario (estudio con pago particular vigente en `pagos`) -> `estudio.estado = EstadoEstudio.CREADO` (`"Creado"`).
3. Inserta un `Aviso` en `avisos` para el `Paciente` (`"Su turno del <inicio> fue cancelado. Ya puede solicitar un nuevo turno de extracción."`).
4. Ejecuta `session.commit()`.
**Timeout**: `3s`
**Input**: `Turno`, `Estudio`
**Output on SUCCESS**: `Turno` cancelado (`activo = False`), slot liberado en `uq_turno_activo` y `Estudio` listo para reservar nuevo turno -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(db_error)` / `FAILURE(timeout)`: Error al confirmar en `PostgreSQL` -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Confirmación `"Turno cancelado correctamente. Puede seleccionar un nuevo turno cuando lo desee"` y botón `"Sacar turno"` nuevamente activo.
  - **Operator sees**: El horario `(centro_id, inicio)` vuelve a aparecer como libre en la agenda del `Centro de extracción`.
  - **Database**: `turnos.activo = False`, `turnos.asistio = NULL`; `estudios.ausencias` sin cambios; `estudios.estado` en `AUTORIZADO`, `CREADO` o `REMUESTREO_REQUERIDO`; fila en `avisos`.
  - **Logs**: `[turno_repo] STEP 2 turno_id=<tid> cancelado activo=False estudio_id=<eid> estado_restaurado=<estado>`

---

### ABORT_CLEANUP: Reversión de cancelación fallida
**Triggered by**: Fallo de base de datos en `STEP 2`.
**Actions**:
  1. Ejecutar `session.rollback()` manteniendo `turno.activo = True` y `estudio.estado = EstadoEstudio.TURNO_SACADO`.
  2. Retornar respuesta HTTP `500` / `503` con `retryable: true`.
**What customer (`Paciente`) sees**: Mensaje de error indicando que no se pudo cancelar el turno en este momento y que puede reintentar.
**What operator sees**: Log de error; el turno continúa activo sin inconsistencias.

---

## State Transitions

```
[Estudio.estado = TURNO_SACADO ("Turno sacado"), Turno.activo = True, Turno.asistio = None]
   |
   |-- (Médico u otro rol intenta cancelar en STEP 1)
   |       --> [403 Forbidden FORBIDDEN_CANCELAR_TURNO — Turno sigue activo]
   |
   |-- (Paciente titular cancela en STEP 1-2)
   |       --> Turno.activo = False (slot liberado en uq_turno_activo)
   |       --> Estudio.ausencias permanece igual (no suma inasistencia)
   |       --> Estudio.estado pasa a:
   |             - AUTORIZADO (si fue autorizado por Obra social)
   |             - REMUESTREO_REQUERIDO (si venía de un remuestreo)
   |             - CREADO (si fue pagado de forma particular)
   |           [En todos los casos queda habilitado para Sacar turno nuevamente]
   |
   +-- (Fallo de BD en STEP 2 -> ABORT_CLEANUP)
           --> [Permanece en TURNO_SACADO con Turno.activo = True]
```

---

## Handoff Contracts

### 1. Frontend Paciente -> Backend (`router` -> `service`)
**Endpoint**: `POST /api/v1/turnos/{turno_id}/cancelar`
**Payload**:
```json
{}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "turno_id": 501,
    "estudio_id": 101,
    "centro_id": 14,
    "inicio": "2026-11-02T09:15:00",
    "activo": false,
    "estado_estudio": "Autorizado",
    "ausencias": 0,
    "puede_sacar_nuevo_turno": true
  }
}
```
**Failure response** (`403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "Solo el paciente titular puede cancelar su turno de extracción. El médico no puede cancelar un turno.",
  "code": "FORBIDDEN_CANCELAR_TURNO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Rollback transaccional mediante `ABORT_CLEANUP`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Cambio `turnos.activo = False` | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Cambio `estudios.estado` | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Registro en `avisos` | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/turnos.py`, `Turno.activo` tiene el comentario explícito `# False si se cancelo`, y el índice único parcial `uq_turno_activo` filtra por `WHERE activo`. Al pasar `activo = False`, el mismo paciente u otro paciente puede reservar ese mismo `(centro_id, inicio)` sin colisión de clave única. | Low | STEP 2 | 100% alineado con el diseño de `turnos.py`. |
| RC-2 | En `.ai/2-Glosario_LEL.md` (`Sujeto: Médico` y `Verbo: Cancelar turno`), se establece explícitamente que *"El médico no puede cancelar un turno"*. | Low | STEP 1 & Test Cases | Cubierto con validación explícita de rol y caso de prueba `TC-04`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path Paciente cancela su turno activo (estudio por obra social)** | `POST /api/v1/turnos/{id}/cancelar` por el `Paciente` titular de un estudio autorizado por obra social. | Retorna `200 OK`; `Turno.activo == False`; `Estudio.estado == EstadoEstudio.AUTORIZADO`; `Estudio.ausencias == 0`. |
| **TC-02: Happy path Paciente cancela su turno y luego saca uno nuevo en el mismo horario liberado** | `POST /api/v1/turnos/{id}/cancelar` seguido de `POST /api/v1/estudios/{eid}/turnos` para el mismo `(centro_id, inicio)`. | Ambas llamadas tienen éxito (`200 OK` y `201 Created`); se crea una segunda fila en `turnos` con `activo = True` sin violar `uq_turno_activo`. |
| **TC-03: Happy path Paciente cancela turno de un estudio en remuestreo** | `POST /api/v1/turnos/{id}/cancelar` cuando el estudio tenía una muestra previa descartada. | Retorna `200 OK`; `Turno.activo == False`; `Estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO`. |
| **TC-04: Médico intenta cancelar el turno de su paciente (Regla LEL)** | `POST /api/v1/turnos/{id}/cancelar` invocado con credenciales de `Rol.MEDICO` o `Rol.GERENTE_MEDICO`. | Retorna `403 Forbidden` (`code: "FORBIDDEN_CANCELAR_TURNO"`); `Turno.activo` sigue en `True`. |
| **TC-05: Otro paciente intenta cancelar un turno ajeno** | `POST /api/v1/turnos/{id}/cancelar` invocado por otro usuario con `Rol.PACIENTE`. | Retorna `403 Forbidden` (`code: "FORBIDDEN_CANCELAR_TURNO"`). |
| **TC-06: Intento de cancelar un turno ya cancelado o con muestra ya tomada** | `POST /api/v1/turnos/{id}/cancelar` cuando `turno.activo == False` o `estudio.estado == EstadoEstudio.LISTA_PARA_RETIRAR`. | Retorna `409 Conflict` (`code: "TURNO_NO_CANCELABLE"`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Cancelar un turno antes de la extracción no cuenta como ausencia (`estudio.ausencias` no se incrementa) ni anula el pago del paciente. | `.ai/2-Glosario_LEL.md` (`Verbo: Cancelar turno`) y `.ai/3-Escenarios.md` (Escenario 8 vs Escenario 33). | Bajo. |

## Open Questions

- ¿Existe una antelación mínima en minutos antes de `turno.inicio` para permitir la cancelación, o puede cancelarse mientras no haya pasado la hora del turno ni se haya tomado la muestra? *(En esta spec se permite mientras `turno.activo == True`, `turno.asistio is None` y no se haya registrado la muestra).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/turnos.py` y `estudios.py`. | Marcada como `Approved`. |
