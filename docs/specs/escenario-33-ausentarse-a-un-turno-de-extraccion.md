# WORKFLOW: Escenario 33 – Ausentarse a un turno de extracción
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-33`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Paciente** | `Usuario` (`rol = Rol.PACIENTE`) + `Paciente` (`pacientes.id`) |
| **Objetos** | **Turno** | Modelo `Turno` (tabla `turnos`: `id`, `centro_id`, `paciente_id`, `estudio_id`, `inicio`, `activo`, `asistio`) |
| **Objetos** | **Estudio** | Modelo `Estudio` (tabla `estudios`: `id`, `estado`, `ausencias` con `CheckConstraint("ausencias BETWEEN 0 AND 5")`) y constante `MAX_AUSENCIAS = 5` en `reglas.py` |
| **Objetos** | **Presupuesto** | Modelo `Presupuesto` (`presupuestos`) y modelo `Pago` (`pagos`: `id`, `presupuesto_id`, `anulado`) |
| **Objetos** | **Centro de extracción** | Modelo `CentroExtraccion` (`centros_extraccion`) |
| **Objetos** | **Bot de Telegram** | Canal por el cual el **centro de extracción** informa cuando sí se tomó la **muestra** (su ausencia al cierre del turno determina la inasistencia) |
| **Objetos** | **Aviso** | Modelo `Aviso` (`avisos`: notificación en app y por mail al **paciente**) |
| **Verbos** | **Sacar turno** | Habilitado nuevamente de la 1.ª a la 4.ª ausencia sin pagar de nuevo |
| **Verbos** | **Pagar presupuesto** | Exigido nuevamente al alcanzar la 5.ª ausencia (`MAX_AUSENCIAS = 5`) |
| **Estados** | **Turno sacado**, **Creado**, **Autorizado**, **Remuestreo requerido** | En ausencias 1..4 habilita nuevo turno; en la 5.ª ausencia pasa a `EstadoEstudio.CREADO` y anula el pago |

---

## Overview

- **Objetivo:** Registrar la ausencia del **paciente** a un **turno** de extracción y aplicar la regla de negocio del límite de cinco ausencias (`MAX_AUSENCIAS = 5`).
- **Contexto:** El **paciente** pagó el **presupuesto** del **estudio** (o fue **Autorizado** por **obra social**), reservó un **turno** (`EstadoEstudio.TURNO_SACADO`) y no concurre al **centro de extracción** en la fecha y hora pactadas.
- **Recursos:** **Turno** (`turnos`), contador de ausencias (`Estudio.ausencias`, `MAX_AUSENCIAS = 5`), **estudio** (`estudios`), **pago** (`pagos.anulado`).
- **Episodios:**
  1. El **paciente** no concurre al **turno** de extracción.
  2. El sistema registra la ausencia (`Turno.asistio = False`, `Turno.activo = False`, e incrementa `Estudio.ausencias`).
  3. El sistema permite al **paciente** **sacar turno** nuevamente sin costo adicional mientras acumule de una a cuatro ausencias (`1 <= Estudio.ausencias < 5`).
  4. Al llegar a la quinta ausencia (`Estudio.ausencias == 5`), el sistema hace que el **paciente** pierda el pago (`Pago.anulado = True`).
  5. El sistema devuelve el **estudio** al estado **Creado** (`EstadoEstudio.CREADO`), y el **paciente** debe **pagar presupuesto** de nuevo (reiniciándose el contador `Estudio.ausencias = 0` al registrar el nuevo pago para el nuevo ciclo de turnos).

**Resumen del flujo:** Cuando vence la ventana horaria de un **turno** activo (`Turno.inicio + 15 minutos`, o al procesarse el cierre de turnos vencidos / endpoint de registro de inasistencia) sin que se haya recibido confirmación de toma de **muestra** por el **bot de Telegram**, el servicio de turnos bloquea el `Turno` y el `Estudio` (`SELECT ... FOR UPDATE`), marca `Turno.asistio = False` y `Turno.activo = False`, e incrementa `Estudio.ausencias += 1`.
- **Rama A (`1 <= Estudio.ausencias <= 4`):** El **paciente** conserva su pago vigente (`Pago.anulado == False`); el sistema le envía un `Aviso` informando la ausencia registrada y cuántas oportunidades le restan antes de perder el pago (`5 - Estudio.ausencias`), dejándolo habilitado para elegir un nuevo **turno** (`Sacar turno`).
- **Rama B (`Estudio.ausencias == 5 == MAX_AUSENCIAS`):** El **paciente** alcanza la quinta ausencia; el sistema marca el pago vigente como perdido (`Pago.anulado = True`), retrocede el `Estudio` a `EstadoEstudio.CREADO` y notifica al **paciente** que perdió el pago por acumular 5 inasistencias y que debe abonar nuevamente el **presupuesto** para poder volver a **sacar turno**.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Paciente** (Sujeto LEL) | No concurre al **turno** reservado; luego saca un nuevo **turno** (ausencias 1 a 4) o debe **pagar presupuesto** nuevamente (ausencia 5). |
| **Scheduler / Proceso de Turnos o Endpoint de Inasistencia** (`app/src/routers/turnos.py`) | Detecta turnos cuyo horario `inicio + 15 min` ya expiró con `asistio IS NULL` y `Estudio.estado == EstadoEstudio.TURNO_SACADO` (o recibe el disparo explícito `POST /api/turnos/{turno_id}/registrar-ausencia`). |
| **Servicio de Turnos** (`app/src/services/turno_service.py`) | Aplica la lógica de negocio de `MAX_AUSENCIAS = 5`, decide entre la Rama A (`ausencias < 5`) y la Rama B (`ausencias == 5`), anula el `Pago` cuando corresponde y genera los `Aviso` para el **paciente**. |
| **Repositorio de Turnos y Economía** (`app/src/repos/turno_repo.py`, `economia_repo.py`) | Actualiza atómicamente `turnos`, `estudios`, `pagos` y `avisos` bajo bloqueo pesimista. |
| **PostgreSQL** (`db`) | Valida `CheckConstraint("ausencias BETWEEN 0 AND 5")` en `estudios` y el índice parcial `uq_turno_activo` en `turnos`. |

---

## Prerequisites

- **Datos existentes en `app/src/core/models/`:**
  - Existe un `Estudio` en estado `EstadoEstudio.TURNO_SACADO` con `0 <= Estudio.ausencias < 5`.
  - Existe un `Turno` asociado a dicho `Estudio` con `activo == True`, `asistio is None` y cuya ventana (`Turno.inicio + 15 min`) ya ha transcurrido sin que exista una `Muestra` vinculada a ese `turno_id`.
  - Existe un `Presupuesto` para el `Estudio` con un `Pago` activo (`anulado == False`) o una `Autorizacion` en `ResultadoAutorizacion.AUTORIZADA`.
- **Estado previo del `Estudio`:** `EstadoEstudio.TURNO_SACADO`.

---

## Trigger

- **Evento temporal / Endpoint HTTP:**
  - Ejecución automática del job de cierre de turnos vencidos o invocación a `POST /api/turnos/{turno_id}/registrar-ausencia` una vez superada la hora de finalización del **turno** (`Turno.inicio + 15 minutos`) sin recepción de mensaje del **bot de Telegram**.

---

## Workflow Tree

### STEP 1: Verificación de turno vencido sin muestra tomada y bloqueo transaccional
**Actor**: Router / Scheduler (`turnos.py`) -> Servicio de Turnos (`turno_service.py`) -> Repositorio (`turno_repo.py`)
**Action**:
  1. Obtiene el `Turno` (`turno_id`) y su `Estudio` asociado mediante `SELECT ... FOR UPDATE NOWAIT`.
  2. Verifica que `turno.activo == True`, `turno.asistio is None`, que no exista fila en `muestras` con `turno_id == turno.id` y que `estudio.estado == EstadoEstudio.TURNO_SACADO`.
  3. Verifica que `estudio.ausencias < MAX_AUSENCIAS` (`5`).
**Timeout**: `2s`
**Input**: `{ turno_id: 210, timestamp_actual: datetime }`
**Output on SUCCESS**: `{ turno: Turno, estudio: Estudio, presupuesto: Presupuesto | null }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(invalid_state)`:
    - El `Turno` ya fue cancelado (`activo == False`) o ya tiene asistencia registrada (`asistio is not None`) -> retornar `409 Conflict` (`TURNO_YA_PROCESADO`).
    - El `Estudio` ya pasó a `EstadoEstudio.LISTA_PARA_RETIRAR` porque llegó el aviso del **bot de Telegram** -> retornar `409 Conflict` (`MUESTRA_YA_TOMADA`).
    - El horario del `Turno` aún no ha transcurrido (`now() < turno.inicio + 15 min`) -> retornar `422 Unprocessable Entity` (`TURNO_AUN_EN_CURSO`).
  - `FAILURE(conflict)`: Bloqueo concurrente sobre el `Turno` o `Estudio` (por ejemplo, está procesándose simultáneamente un mensaje del **bot de Telegram**) -> retornar `409 Conflict` (`OPERACION_CONCURRENTE`, `retryable=True`).
  - `FAILURE(not_found)`: `turno_id` inexistente -> retornar `404 Not Found`.

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: Turno vencido en proceso de actualización.
  - Operator sees: Verificación de inasistencia para `turno_id=210`.
  - Database: Filas en `turnos` y `estudios` bloqueadas en la transacción actual.
  - Logs: `[turno_service] step=1_verificar_inasistencia turno_id=210 estudio_id=88 ausencias_previas=<n>`

---

### STEP 2: Registro de la ausencia e incremento de `Estudio.ausencias`
**Actor**: Servicio de Turnos (`turno_service.py`) -> Repositorio (`turno_repo.py`)
**Action**:
  1. Marca `turno.asistio = False` y `turno.activo = False` (liberando la restricción `uq_turno_activo` del slot).
  2. Incrementa el contador: `estudio.ausencias = estudio.ausencias + 1`.
  3. Evalúa la condición de bifurcación contra `MAX_AUSENCIAS = 5`:
     - Si `estudio.ausencias < 5` (ausencias 1, 2, 3 o 4) -> GO TO **STEP 3A**.
     - Si `estudio.ausencias == 5` (quinta ausencia) -> GO TO **STEP 3B**.
**Timeout**: `2s`
**Input**: `{ turno: Turno, estudio: Estudio }`
**Output on SUCCESS**:
  - Si `estudio.ausencias in (1, 2, 3, 4)` -> GO TO STEP 3A
  - Si `estudio.ausencias == 5` -> GO TO STEP 3B
**Output on FAILURE**:
  - `FAILURE(validation_error / constraint)`: Intento de incrementar `ausencias > 5` violando `CheckConstraint("ausencias BETWEEN 0 AND 5")` -> `ABORT_CLEANUP` (`rollback`) -> retornar `409 Conflict`.

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: Actualización en curso.
  - Operator sees: `turno.asistio = False` y nuevo valor de `estudio.ausencias`.
  - Database: En memoria de la transacción SQLAlchemy: `turnos.asistio = False`, `turnos.activo = False`, `estudios.ausencias = N`.
  - Logs: `[turno_service] step=2_ausencia_computada turno_id=210 estudio_id=88 nuevas_ausencias=<N>`

---

### STEP 3A: Ausencias 1 a 4 – Habilitar nuevo turno sin perder el pago
**Actor**: Servicio de Turnos (`turno_service.py`) -> Repositorio (`turno_repo.py`) -> PostgreSQL
**Action**:
  1. Mantiene intacto el pago del **paciente** (`Pago.anulado == False`).
  2. Habilita al **paciente** para **sacar turno** nuevamente (el `Estudio` no tiene ningún `Turno` con `activo == True`, por lo que el paciente puede reservar un nuevo slot que mantendrá/llevará el estudio a `EstadoEstudio.TURNO_SACADO`).
  3. Inserta un `Aviso` (`CanalAviso.APP` y `CanalAviso.MAIL`) para `estudio.paciente.usuario_id` informando que se registró la ausencia N° `estudio.ausencias` de `5` y que puede **sacar turno** nuevamente sin costo, recordándole que a la 5.ª ausencia perderá el pago.
  4. Ejecuta `COMMIT`.
**Timeout**: `3s`
**Input**: `{ estudio_id: 88, ausencias: 1..4, pago_anulado: False }`
**Output on SUCCESS**: `{ estudio_id: 88, estado: EstadoEstudio.TURNO_SACADO, ausencias: N, pago_perdido: False, puede_sacar_nuevo_turno: True }` -> Retornar `200 OK` (FIN DEL WORKFLOW – RAMA A).
**Output on FAILURE**:
  - `FAILURE(database_error)`: Falla el `COMMIT` -> ejecutar `ABORT_CLEANUP` (`rollback`).

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: Aviso en pantalla y por mail: "No asististe a tu turno de extracción (Ausencia `N` de 5). Podés sacar un nuevo turno sin cargo. Recordá que al llegar a 5 ausencias perderás el pago.". El botón **Sacar turno** queda habilitado.
  - Operator sees: `estudios.ausencias = N` (`1..4`), `turnos.asistio = False`, `pagos.anulado = False`.
  - Database:
    - `turnos`: `asistio = False`, `activo = False`.
    - `estudios`: `ausencias = N` (`1 <= N <= 4`), `updated_at = now()`.
    - `pagos`: sin cambios (`anulado = False`).
    - `avisos`: nueva fila para el paciente.
  - Logs: `[turno_repo] step=3A_commit_ausencia_parcial estudio_id=88 ausencias=<N> pago_anulado=false`

---

### STEP 3B: Quinta ausencia (`ausencias == 5`) – Pérdida del pago y retorno a estado `Creado`
**Actor**: Servicio de Turnos (`turno_service.py`) -> Repositorio (`turno_repo.py`, `economia_repo.py`) -> PostgreSQL
**Action**:
  1. Localiza el `Pago` activo (`anulado == False`) asociado al `Presupuesto` del `Estudio` y lo marca como `Pago.anulado = True` (el **paciente** pierde el pago).
  2. Cambia el estado del `Estudio` a `EstadoEstudio.CREADO` (`estudio.estado = EstadoEstudio.CREADO`), manteniendo `estudio.ausencias = 5` como evidencia del límite alcanzado (nota: cuando el **paciente** realice el nuevo pago del **presupuesto**, el servicio de pagos reiniciará `estudio.ausencias = 0` para habilitar el nuevo ciclo de hasta 5 turnos respetando `CheckConstraint("ausencias BETWEEN 0 AND 5")`).
  3. Inserta un `Aviso` (`CanalAviso.APP` y `CanalAviso.MAIL`) para `estudio.paciente.usuario_id` informando que alcanzó las 5 ausencias máximas permitidas (`MAX_AUSENCIAS = 5`), por lo que perdió el pago abonado, su **estudio** volvió al estado **Creado** y debe **pagar presupuesto** nuevamente para poder sacar otro **turno**.
  4. Ejecuta `COMMIT`.
**Timeout**: `3s`
**Input**: `{ estudio_id: 88, ausencias: 5 }`
**Output on SUCCESS**: `{ estudio_id: 88, estado: EstadoEstudio.CREADO, ausencias: 5, pago_perdido: True, requiere_nuevo_pago: True }` -> Retornar `200 OK` (FIN DEL WORKFLOW – RAMA B).
**Output on FAILURE**:
  - `FAILURE(database_error)`: Falla la actualización de `pagos` o `estudios` -> ejecutar `ABORT_CLEANUP` (`rollback`).

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: El **estudio** figura en estado **Creado**, con alerta destacada: "Acumulaste 5 ausencias a turnos de extracción. Perdiste el pago anterior y debés abonar nuevamente el presupuesto para sacar un nuevo turno.". El botón **Sacar turno** queda bloqueado hasta que registre un nuevo pago.
  - Operator sees: `estudios.estado = 'Creado'`, `estudios.ausencias = 5`, `pagos.anulado = True`.
  - Database:
    - `turnos`: `asistio = False`, `activo = False`.
    - `pagos`: `anulado = True` en el pago activo del presupuesto del estudio.
    - `estudios`: `estado = EstadoEstudio.CREADO`, `ausencias = 5`, `updated_at = now()`.
    - `avisos`: nueva fila notificando la pérdida del pago y el retorno a `Creado`.
  - Logs: `[turno_repo] step=3B_quinta_ausencia_pago_anulado estudio_id=88 ausencias=5 nuevo_estado='Creado' pago_id=<pid>`

---

### ABORT_CLEANUP: Rollback transaccional ante fallo al procesar la ausencia
**Triggered by**: Error de base de datos o violación de restricción en `STEP 2`, `STEP 3A` o `STEP 3B`.
**Actions** (in order):
  1. Ejecutar `db.session.rollback()` para restaurar `turno.asistio = None`, `turno.activo = True`, el valor previo de `estudio.ausencias`, `estudio.estado = EstadoEstudio.TURNO_SACADO` y `pago.anulado = False`.
  2. Registrar error en logs para que el job o el operador reintente el procesamiento del turno vencido.
**What customer/actor (**Paciente**) sees**: Sin cambios parciales ni inconsistentes (no se le descuenta una oportunidad ni se le anula el pago sin que toda la transacción haya confirmado).
**What operator sees**: Log `ERROR` con `turno_id` y `estudio_id` pendiente de reprocesamiento.

---

## State Transitions

```
Turno (turnos):
  [Reservado (activo=True, asistio=None)]
    -- (STEP 2: Paciente no concurre al turno) -->
  [Ausente (activo=False, asistio=False)]

Estudio (estudios.estado + estudios.ausencias) y Pago (pagos.anulado):
  Caso 1 a 4 ausencias (ausencias previas = 0, 1, 2 o 3):
    [EstadoEstudio.TURNO_SACADO, ausencias = k, Pago.anulado = False]
      -- (STEP 2 + STEP 3A) -->
    [EstadoEstudio.TURNO_SACADO (sin turno activo; habilitado para Sacar turno), ausencias = k + 1 (1..4), Pago.anulado = False]
      -- (Paciente vuelve a Sacar turno) -->
    [EstadoEstudio.TURNO_SACADO (con nuevo Turno activo=True), ausencias = k + 1]

  Caso 5.ª ausencia (ausencias previas = 4):
    [EstadoEstudio.TURNO_SACADO, ausencias = 4, Pago.anulado = False]
      -- (STEP 2 + STEP 3B: llega a MAX_AUSENCIAS = 5) -->
    [EstadoEstudio.CREADO, ausencias = 5, Pago.anulado = True]
      -- (Paciente vuelve a Pagar presupuesto) -->
    [EstadoEstudio.CREADO, ausencias = 0, nuevo Pago con anulado = False]
```

---

## Handoff Contracts

### Sistema / Operador -> Backend: Registrar ausencia a turno vencido
**Endpoint**: `POST /api/turnos/{turno_id}/registrar-ausencia`
**Payload**: `{}`
**Success response – Rama A (1 a 4 ausencias)** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "turno_id": 210,
    "estudio_id": 88,
    "asistio": false,
    "ausencias_acumuladas": 2,
    "max_ausencias": 5,
    "pago_perdido": false,
    "estado_estudio": "Turno sacado",
    "puede_sacar_nuevo_turno": true,
    "requiere_nuevo_pago": false
  }
}
```
**Success response – Rama B (5.ª ausencia)** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "turno_id": 214,
    "estudio_id": 88,
    "asistio": false,
    "ausencias_acumuladas": 5,
    "max_ausencias": 5,
    "pago_perdido": true,
    "pago_anulado_id": 301,
    "estado_estudio": "Creado",
    "puede_sacar_nuevo_turno": false,
    "requiere_nuevo_pago": true
  }
}
```
**Failure response** (`404` / `409` / `422` / `500`):
```json
{
  "ok": false,
  "error": "El turno ya fue procesado o la muestra ya fue tomada en el centro de extracción.",
  "code": "TURNO_YA_PROCESADO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: No incrementar `Estudio.ausencias` ni modificar `Pago.anulado`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Cambio `turnos.asistio = False`, `turnos.activo = False` | Step 2 | `ABORT_CLEANUP` | `db.session.rollback()` |
| Incremento de `estudios.ausencias` y cambio de `estudios.estado` | Step 2 / Step 3B | `ABORT_CLEANUP` | `db.session.rollback()` |
| Marcación `pagos.anulado = True` | Step 3B | `ABORT_CLEANUP` | `db.session.rollback()` |
| Fila en `avisos` | Step 3A / Step 3B | `ABORT_CLEANUP` | `db.session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | `Estudio` en `app/src/core/models/estudios.py` define `ausencias: Mapped[int] = mapped_column(Integer, default=0)` y `CheckConstraint("ausencias BETWEEN 0 AND 5")`, y `reglas.py` define `MAX_AUSENCIAS = 5`. | High | STEP 2, STEP 3B | La especificación respeta estrictamente el tope `5` del `CheckConstraint`. Al llegar a `5`, el estudio pasa a `EstadoEstudio.CREADO` y cuando el paciente abona el nuevo pago se reinicia `ausencias = 0`. |
| RC-2 | `Pago` en `app/src/core/models/economia.py` tiene el docstring: `"Registro financiero. Si el paciente pierde el pago por 5 ausencias, se marca anulado."` y el campo `anulado: Mapped[bool] = mapped_column(Boolean, default=False)`. | Low | STEP 3B | En la 5.ª ausencia no se borra la fila de `pagos` (`DELETE` prohibido para preservar auditoría financiera), sino que se actualiza `Pago.anulado = True`. |
| RC-3 | `Turno` en `app/src/core/models/turnos.py` define `activo: Mapped[bool]` (con índice único parcial `uq_turno_activo` cuando `activo` es verdadero) y `asistio: Mapped[Optional[bool]]` (`# None hasta que pasa el turno; False = ausente`). | Medium | STEP 2 | Al registrar la ausencia se setea `asistio = False` y `activo = False` para liberar el slot y permitir nuevas reservas. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Primera ausencia (`ausencias: 0 -> 1`) | `POST /api/turnos/{id}/registrar-ausencia` sobre un estudio con `ausencias=0` | `turno.asistio=False`, `turno.activo=False`, `estudio.ausencias=1`, `estudio.estado == EstadoEstudio.TURNO_SACADO`, `pago.anulado=False`, paciente habilitado para sacar nuevo turno. |
| `TC-02`: Cuarta ausencia (`ausencias: 3 -> 4`) | `POST /api/turnos/{id}/registrar-ausencia` sobre un estudio con `ausencias=3` | `estudio.ausencias=4`, `pago.anulado=False`, `estudio.estado == EstadoEstudio.TURNO_SACADO`, el paciente aún puede sacar su 5.° turno sin volver a pagar. |
| `TC-03`: Quinta ausencia (`ausencias: 4 -> 5`) hace perder el pago y vuelve a `Creado` | `POST /api/turnos/{id}/registrar-ausencia` sobre un estudio con `ausencias=4` | `turno.asistio=False`, `estudio.ausencias=5`, `pago.anulado=True`, `estudio.estado == EstadoEstudio.CREADO`, se crea `Aviso` informando la pérdida del pago. |
| `TC-04`: Intento de sacar turno tras la 5.ª ausencia sin pagar de nuevo | El paciente con `estudio.estado == EstadoEstudio.CREADO` y `pago.anulado == True` intenta reservar un nuevo turno | El servicio de turnos rechaza con `409 Conflict` (`PAGO_REQUERIDO`) hasta que exista un nuevo `Pago` con `anulado == False`. |
| `TC-05`: Nuevo pago tras 5.ª ausencia reinicia `ausencias = 0` | El paciente abona nuevamente el presupuesto de un estudio que había vuelto a `Creado` con `ausencias = 5` | Se crea una nueva fila en `pagos` con `anulado=False` (la anterior conserva `anulado=True` en el historial financiero) y `estudio.ausencias` se reinicia a `0`. |
| `TC-06`: Rechazo si el turno ya tuvo asistencia confirmada por Telegram | `POST /api/turnos/{id}/registrar-ausencia` cuando el estudio ya está en `EstadoEstudio.LISTA_PARA_RETIRAR` o existe `Muestra` para ese `turno_id` | Retorna `409 Conflict` (`MUESTRA_YA_TOMADA`); no incrementa `ausencias`. |
| `TC-07`: Idempotencia ante doble ejecución sobre el mismo turno | Llamar dos veces seguidas a `POST /api/turnos/{id}/registrar-ausencia` para el mismo `turno_id` | La segunda llamada retorna `409 Conflict` (`TURNO_YA_PROCESADO`) y `estudio.ausencias` se incrementa una sola vez. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Cuando el **paciente** falta de 1 a 4 veces, el `Estudio` permanece en `EstadoEstudio.TURNO_SACADO` (sin turno activo vigente) o listo para reasignar un nuevo `Turno`, ya que el LEL solo define transición de vuelta a `Creado` en la 5.ª ausencia. | Verificado en `.ai/2-Glosario_LEL.md` (`Estado: Turno sacado`: "Si el paciente falta de una a cuatro veces, saca otro turno. Si el paciente falta cinco veces, el estudio vuelve a Creado"). | Bajo. |
| A2 | Al pagar nuevamente el **presupuesto** tras haber vuelto a `Creado` por 5 ausencias, `Estudio.ausencias` se reinicia a `0` para que el `CheckConstraint("ausencias BETWEEN 0 AND 5")` permita el nuevo ciclo de turnos. | Verificado en `app/src/core/models/estudios.py` (línea 47: `CheckConstraint("ausencias BETWEEN 0 AND 5")`). | Si no se reiniciara a `0` al volver a pagar, una ausencia ulterior violaría el `CheckConstraint`. |

## Open Questions

- ¿Cuántos minutos de tolerancia después de `Turno.inicio + 15 min` debe esperar el proceso automático antes de marcar `Turno.asistio = False` en caso de demora del mensaje del **bot de Telegram**? *(Se recomienda una ventana de gracia configurable, por ejemplo 30 minutos después de finalizado el turno).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada verificando `Turno`, `Estudio`, `Pago` y `MAX_AUSENCIAS = 5` en `app/src/core/models/`. | Aprobada. |
