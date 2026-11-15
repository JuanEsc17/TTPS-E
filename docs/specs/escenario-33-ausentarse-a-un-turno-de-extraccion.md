# WORKFLOW: Escenario 33 – Ausentarse a un turno de extracción
**Versión**: 1.2
**Fecha**: 2026-11-15
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
| **Objetos** | **Muestra** | Modelo `Muestra` (`muestras`: la ausencia de toma de muestra registrada para `turno_id` al finalizar la ventana de 15 minutos del turno confirma inasistencia) |
| **Objetos** | **Mail / Notificación** | Despacho exclusivo por correo electrónico mediante `EmailClient` (`API de Notificaciones por Email`, sin crear filas en tabla `avisos` ni usar Bot de Telegram) |
| **Verbos** | **Sacar turno** | Habilitado nuevamente de la 1.ª a la 4.ª ausencia sin pagar de nuevo |
| **Verbos** | **Pagar presupuesto** | Exigido nuevamente al alcanzar la 5.ª ausencia (`MAX_AUSENCIAS = 5`) |
| **Estados** | **Turno sacado**, **Creado**, **Autorizado**, **Remuestreo requerido** | En ausencias 1..4 mantiene `EstadoEstudio.TURNO_SACADO`; en la 5.ª ausencia pasa a `EstadoEstudio.CREADO` y anula el pago activo si existe |

---

## Overview

- **Objetivo:** Detectar y registrar **automáticamente** la ausencia del **paciente** a un **turno** de extracción una vez transcurridos 15 minutos desde su horario de inicio (`turno.inicio + 15 min`), aplicando la regla de negocio del límite de cinco ausencias (`MAX_AUSENCIAS = 5`) y notificando exclusivamente por mail.
- **Contexto:** El **paciente** pagó el **presupuesto** del **estudio** (o fue **Autorizado** por **obra social**), reservó un **turno** (`EstadoEstudio.TURNO_SACADO`) y no concurre al **centro de extracción** en la fecha y hora pactadas. Ningún usuario administrativo ni administrador general registra inasistencias manualmente por HTTP.
- **Recursos:** **Turno** (`turnos`), contador de ausencias (`Estudio.ausencias`, `MAX_AUSENCIAS = 5`), **estudio** (`estudios`), **pago** (`pagos.anulado`), `EmailClient`.
- **Episodios:**
  1. El **paciente** no concurre al **turno** de extracción y transcurren 15 minutos desde su inicio (`ahora >= turno.inicio + 15 min`) sin que exista una `Muestra` registrada.
  2. El proceso automático (`poetry run flask procesar-ausencias` / `TurnoService.procesar_turnos_vencidos`) detecta el turno vencido, registra la ausencia (`Turno.asistio = False`, `Turno.activo = False`) e incrementa `Estudio.ausencias`.
  3. El sistema permite al **paciente** **sacar turno** nuevamente sin costo adicional mientras acumule de una a cuatro ausencias (`1 <= Estudio.ausencias < 5`).
  4. Al llegar a la quinta ausencia (`Estudio.ausencias == 5`), el sistema hace que el **paciente** pierda el pago (`Pago.anulado = True`, si existe un pago activo).
  5. El sistema devuelve el **estudio** al estado **Creado** (`EstadoEstudio.CREADO`), y el **paciente** debe **pagar presupuesto** de nuevo (reiniciándose `Estudio.ausencias = 0` en el flujo de pagos del Escenario 6).

**Resumen del flujo:** Cuando vence la ventana horaria de un **turno** activo (`ahora >= Turno.inicio + 15 minutos`) sin que exista confirmación de toma de **muestra**, el comando CLI `procesar-ausencias` invoca `TurnoService.procesar_turnos_vencidos()`. Por cada turno elegible, bloquea el `Turno` y el `Estudio` (`SELECT ... FOR UPDATE`), marca `Turno.asistio = False` y `Turno.activo = False`, e incrementa `Estudio.ausencias += 1`.
- **Rama A (`1 <= Estudio.ausencias <= 4`):** El **paciente** conserva su pago vigente (`Pago.anulado == False`); el sistema le envía únicamente un correo electrónico mediante `EmailClient` informando la ausencia registrada y cuántas oportunidades le restan antes de perder el pago (`5 - Estudio.ausencias`), dejándolo habilitado para elegir un nuevo **turno** (`Sacar turno`).
- **Rama B (`Estudio.ausencias == 5 == MAX_AUSENCIAS`):** El **paciente** alcanza la quinta ausencia; si existe un `Pago` vigente en el `Presupuesto` del `Estudio`, el sistema lo marca como perdido (`Pago.anulado = True`), retrocede el `Estudio` a `EstadoEstudio.CREADO` y envía un correo electrónico mediante `EmailClient` informando al **paciente** que perdió el pago por acumular 5 inasistencias y debe abonar nuevamente el **presupuesto** para poder volver a **sacar turno**.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Paciente** (Sujeto LEL) | No concurre al **turno** reservado; recibe correo electrónico y luego saca un nuevo **turno** (ausencias 1 a 4) o debe **pagar presupuesto** nuevamente (ausencia 5). |
| **Comando CLI Automático (`procesar-ausencias`)** (`app/src/__init__.py`) | Expone `poetry run flask procesar-ausencias`, diseñado para ejecutarse periódicamente desde un planificador del sistema operativo / tarea programada invocando `TurnoService.procesar_turnos_vencidos()`. *(No existe endpoint HTTP manual para `ADMINISTRATIVO` ni `ADMIN_GENERAL`).* |
| **Servicio de Turnos** (`app/src/core/services/turno_service.py`) | Ejecuta `procesar_turnos_vencidos` y `registrar_ausencia`, aplica `MAX_AUSENCIAS = 5`, decide entre Rama A (`ausencias < 5`) y Rama B (`ausencias == 5`), anula el `Pago` activo cuando corresponde y despacha el correo por `EmailClient`. |
| **Repositorio de Turnos** (`app/src/core/repos/turno_repo.py`) | Lista IDs de turnos vencidos sin muestra (`listar_ids_turnos_vencidos_sin_procesar`) y actualiza atómicamente `turnos`, `estudios` y `pagos` bajo bloqueo pesimista. |
| **API de Notificaciones por Email** (`app/src/clients/email_client.py`) | Envía el correo al paciente con `Idempotency-Key` determinista (`ausencia-turno-<turno_id>`). No se insertan filas en la tabla `avisos`. |
| **PostgreSQL** (`db`) | Valida `CheckConstraint("ausencias BETWEEN 0 AND 5")` en `estudios` y el índice parcial `uq_turno_activo` en `turnos`. |

---

## Prerequisites

- **Datos existentes en `app/src/core/models/`:**
  - Existe un `Estudio` en estado `EstadoEstudio.TURNO_SACADO` con `0 <= Estudio.ausencias < 5`.
  - Existe un `Turno` asociado a dicho `Estudio` con `activo == True`, `asistio is None` y cuya ventana (`Turno.inicio + 15 min`) ya ha finalizado (`ahora >= Turno.inicio + 15 min`) sin que exista una `Muestra` vinculada a ese `turno_id`.
  - Existe un `Presupuesto` para el `Estudio` con un `Pago` activo (`anulado == False`) o una `Autorizacion` en `ResultadoAutorizacion.AUTORIZADA`.
- **Estado previo del `Estudio`:** `EstadoEstudio.TURNO_SACADO`.

---

## Trigger

- **Comando CLI programado:** `poetry run flask procesar-ausencias` (ejecutado automáticamente cada cierto intervalo mediante cron / Task Scheduler / runner externo).
- **Entrada de Servicio:** `TurnoService.procesar_turnos_vencidos(ahora=..., email_client=...)` detecta todos los turnos con `activo=True`, `asistio IS NULL`, `estudios.estado == TURNO_SACADO`, sin `Muestra` asociada y `inicio <= ahora - 15 min`.

---

## Workflow Tree

### STEP 1: Detección batch y bloqueo transaccional por turno
**Actor**: CLI (`app/src/__init__.py`) -> Servicio (`turno_service.py`) -> Repositorio (`turno_repo.py`)
**Action**:
  1. `TurnoService.procesar_turnos_vencidos(ahora)` calcula `fecha_limite_inicio = fecha_actual - timedelta(minutes=15)` y consulta `TurnoRepo.listar_ids_turnos_vencidos_sin_procesar(fecha_limite_inicio)`.
  2. Por cada `turno_id`, `TurnoService.registrar_ausencia(turno_id, ahora=fecha_actual)` obtiene el `Turno` con su `Paciente -> Usuario` y `Estudio` (`presupuesto -> pagos`, `autorizaciones`) mediante `SELECT ... FOR UPDATE`.
  3. Verifica que `turno.activo == True`, `turno.asistio is None`, `estudio.estado == EstadoEstudio.TURNO_SACADO` y que no exista fila en `muestras` con `turno_id == turno.id`.
  4. Verifica que `estudio.ausencias < MAX_AUSENCIAS` (`5`).
  5. Verifica que la ventana del turno haya finalizado: `ahora >= turno.inicio + timedelta(minutes=15)`.
**Timeout**: `2s` por turno
**Input**: `{ turno_id: 210, ahora: datetime }`
**Output on SUCCESS**: `{ turno: Turno, estudio: Estudio }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(not_found)`: `turno_id` inexistente -> retorna `404` interno en resumen del batch.
  - `FAILURE(invalid_state)`:
    - El `Turno` ya fue cancelado (`activo == False`), ya tiene asistencia registrada (`asistio is not None`), o `estudio.ausencias >= MAX_AUSENCIAS` -> retorna `409` en resumen del batch.
    - El `Estudio` ya no está en `TURNO_SACADO` o ya existe una `Muestra` para ese `turno_id` -> retorna `409` en resumen del batch.
    - El horario del `Turno` aún no finalizó (`ahora < turno.inicio + 15 min`) -> retorna `422` en resumen del batch.

---

### STEP 2: Registro de la ausencia e incremento de `Estudio.ausencias`
**Actor**: Servicio de Turnos (`turno_service.py`) -> Repositorio (`turno_repo.py`)
**Action**:
  1. Marca `turno.asistio = False` y `turno.activo = False` (liberando la restricción `uq_turno_activo` del slot).
  2. Incrementa el contador: `estudio.ausencias = estudio.ausencias + 1`.
  3. Evalúa la condición de bifurcación contra `MAX_AUSENCIAS = 5`:
     - Si `estudio.ausencias < 5` (ausencias 1, 2, 3 o 4) -> GO TO **STEP 3A**.
     - Si `estudio.ausencias == 5` (quinta ausencia) -> GO TO **STEP 3B**.

---

### STEP 3A: Ausencias 1 a 4 – Habilitar nuevo turno y enviar mail por `EmailClient`
**Actor**: Servicio de Turnos (`turno_service.py`) -> `EmailClient` -> PostgreSQL
**Action**:
  1. Mantiene intacto el pago del **paciente** (`Pago.anulado == False`) y el estado del estudio en `EstadoEstudio.TURNO_SACADO`.
  2. Al quedar `turno.activo = False`, el **paciente** queda habilitado para **sacar turno** nuevamente sin costo (`estudio.ausencias < 5`).
  3. Despacha únicamente correo electrónico mediante `EmailClient.enviar_aviso(...)` con `idempotency_key=f"ausencia-turno-{turno.id}"` y `referencia=f"TURNO-{turno.id}-AUSENCIA"`, informando la ausencia `N` de `5` y las oportunidades restantes (`5 - N`). No inserta registros en tabla `avisos`.
  4. Ejecuta `COMMIT`.
**Output on SUCCESS**: `{ turno_id, estudio_id, asistio: False, ausencias_acumuladas: N, max_ausencias: 5, pago_perdido: False, pago_anulado_id: None, estado_estudio: "Turno sacado", puede_sacar_nuevo_turno: True, requiere_nuevo_pago: False }` -> `200`.
**Output on FAILURE**:
  - Fallo de `EmailClient` (`ClienteError`, `OSError`) -> `rollback()` y registra error `502` en `resumen["errores"]` sin afectar los otros turnos del lote.
  - Fallo de BD (`SQLAlchemyError`) -> `rollback()` y registra error `500` en `resumen["errores"]`.

---

### STEP 3B: Quinta ausencia (`ausencias == 5`) – Pérdida del pago, retorno a `Creado` y mail por `EmailClient`
**Actor**: Servicio de Turnos (`turno_service.py`) -> Repositorio (`turno_repo.py`) -> `EmailClient` -> PostgreSQL
**Action**:
  1. Si el `Estudio` posee `Presupuesto` con un `Pago` activo (`anulado == False`), marca el pago vigente como `Pago.anulado = True` (preservando historial financiero, sin borrar la fila). Si era un estudio autorizado por obra social sin `Pago`, `pago_anulado_id = None`.
  2. Cambia el estado del `Estudio` a `EstadoEstudio.CREADO` (`estudio.estado = EstadoEstudio.CREADO`), manteniendo `estudio.ausencias = 5` como evidencia del límite alcanzado (el reinicio a `0` corresponde al Escenario 6 al abonar un nuevo pago).
  3. Despacha únicamente correo electrónico mediante `EmailClient.enviar_aviso(...)` con `idempotency_key=f"ausencia-turno-{turno.id}"` y `referencia=f"TURNO-{turno.id}-AUSENCIA"`, informando que alcanzó las 5 ausencias máximas, su estudio regresó a `Creado` y debe abonar nuevamente el presupuesto para sacar otro turno. No inserta registros en tabla `avisos`.
  4. Ejecuta `COMMIT`.
**Output on SUCCESS**: `{ turno_id, estudio_id, asistio: False, ausencias_acumuladas: 5, max_ausencias: 5, pago_perdido: True (si existia pago) / False, pago_anulado_id: <id|None>, estado_estudio: "Creado", puede_sacar_nuevo_turno: False, requiere_nuevo_pago: True }` -> `200`.
**Output on FAILURE**:
  - Fallo de `EmailClient` (`ClienteError`, `OSError`) -> `rollback()` y registra error `502` en `resumen["errores"]`.
  - Fallo de BD (`SQLAlchemyError`) -> `rollback()` y registra error `500` en `resumen["errores"]`.

---

### ABORT_CLEANUP: Rollback transaccional aislado por turno
**Triggered by**: Error de base de datos o de `EmailClient` en `STEP 2`, `STEP 3A` o `STEP 3B`.
**Actions** (in order):
  1. Ejecutar `db.session.rollback()` para restaurar `turno.asistio = None`, `turno.activo = True`, el valor previo de `estudio.ausencias`, `estudio.estado = EstadoEstudio.TURNO_SACADO` y `pago.anulado = False`.
  2. Aislar la falla en `procesar_turnos_vencidos` agregando el detalle en `resumen["errores"]` sin revertir los turnos ya confirmados en la misma corrida, permitiendo el reintento en la próxima ejecución automática.

---

## State Transitions

```
Turno (turnos):
  [Reservado (activo=True, asistio=None)]
    -- (STEP 2: Turno vencido >= 15 min sin muestra) -->
  [Ausente (activo=False, asistio=False)]

Estudio (estudios.estado + estudios.ausencias) y Pago (pagos.anulado):
  Caso 1 a 4 ausencias (ausencias previas = 0, 1, 2 o 3):
    [EstadoEstudio.TURNO_SACADO, ausencias = k, Pago.anulado = False]
      -- (STEP 2 + STEP 3A) -->
    [EstadoEstudio.TURNO_SACADO (sin turno activo; habilitado para Sacar turno), ausencias = k + 1 (1..4), Pago.anulado = False]

  Caso 5.ª ausencia (ausencias previas = 4):
    [EstadoEstudio.TURNO_SACADO, ausencias = 4, Pago.anulado = False]
      -- (STEP 2 + STEP 3B: llega a MAX_AUSENCIAS = 5) -->
    [EstadoEstudio.CREADO, ausencias = 5, Pago.anulado = True (si existe pago)]
```

---

## Handoff Contracts

### Proceso Automático (`flask procesar-ausencias` / `TurnoService.procesar_turnos_vencidos`)
*(Sin endpoint HTTP manual para `ADMINISTRATIVO` ni `ADMIN_GENERAL`).*

**Resumen devuelto por `TurnoService.procesar_turnos_vencidos(...)`**:
```json
{
  "total_detectados": 1,
  "total_procesados": 1,
  "procesados": [
    {
      "turno_id": 210,
      "estudio_id": 88,
      "asistio": false,
      "ausencias_acumuladas": 2,
      "max_ausencias": 5,
      "pago_perdido": false,
      "pago_anulado_id": null,
      "estado_estudio": "Turno sacado",
      "puede_sacar_nuevo_turno": true,
      "requiere_nuevo_pago": false
    }
  ],
  "errores": []
}
```

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Primera ausencia (`ausencias: 0 -> 1`) y re-agendamiento | `procesar_turnos_vencidos` sobre estudio con `ausencias=0` | `turno.asistio=False`, `turno.activo=False`, `estudio.ausencias=1`, `estudio.estado == TURNO_SACADO`, `pago.anulado=False`, envía mail por `EmailClient` sin filas en `avisos`, paciente saca nuevo turno (`201`) sin pagar de nuevo. |
| `TC-02`: Cuarta ausencia (`ausencias: 3 -> 4`) mantiene estudio listo para nuevo turno | `procesar_turnos_vencidos` sobre estudio con `ausencias=3` | `estudio.ausencias=4`, `pago.anulado=False`, `estudio.estado == TURNO_SACADO`, habilitado para su 5.° turno sin volver a pagar. |
| `TC-03`: Quinta ausencia (`ausencias: 4 -> 5`) hace perder el pago y vuelve a `Creado` | `procesar_turnos_vencidos` sobre estudio con `ausencias=4` | `turno.asistio=False`, `estudio.ausencias=5`, `pago.anulado=True`, `estudio.estado == CREADO`, envía mail informando pérdida del pago. |
| `TC-04`: Quinta ausencia sin `Pago` (autorizado por obra social) y bloqueo de nuevo turno | `procesar_turnos_vencidos` con `ausencias=4` sin `Pago` + intento de `POST /api/v1/estudios/{eid}/turnos` | `pago_perdido=False`, `pago_anulado_id=None`, `estudio.estado == CREADO`; intentar sacar nuevo turno rechaza con `409 Conflict`. |
| `TC-05`: Rechazo si existe `Muestra` o el estudio ya avanzó | `procesar_turnos_vencidos` y `registrar_ausencia` con `Muestra` o `estado == LISTA_PARA_RETIRAR` | No detecta el turno en batch; `registrar_ausencia` retorna `409 Conflict`; no incrementa `ausencias`. |
| `TC-06`: Ventana exacta de 15 min, idempotencia y aislamiento por turno ante fallo de mail | `< 15 min`, exactamente `= 15 min` con fallo en `EmailClient`, y reintento posterior | `< 15 min` se ignora (`422`); fallo en `EmailClient` revierte (`rollback`) solo el turno fallido (`502`); al reintentar se procesa una sola vez sin duplicados. |
| `TC-07`: Comando CLI `procesar-ausencias` y ausencia de endpoint HTTP manual | Ejecución de `flask procesar-ausencias` y `POST /api/v1/turnos/{id}/registrar-ausencia` con roles `ADMINISTRATIVO` / `ADMIN_GENERAL` | Endpoint HTTP manual retorna `404`; comando CLI procesa el turno vencido (`Procesados: 1`) y envía el correo por `EmailClient`. |

*(Nota: el reinicio `ausencias = 0` al abonar nuevamente el presupuesto corresponde al Escenario 6 – Pagar un estudio particular).*

---

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada verificando `Turno`, `Estudio`, `Pago` y `MAX_AUSENCIAS = 5` en `app/src/core/models/`. | Aprobada. |
| 2026-11-15 | Eliminado el `Bot de Telegram` y tabla `avisos` para notificaciones de inasistencia (despacho exclusivo vía `EmailClient`), ventana exacta `+15 min` y método batch `procesar_turnos_vencidos`. | Actualizada v1.1. |
| 2026-11-15 | Removido endpoint manual HTTP para `ADMINISTRATIVO`/`ADMIN_GENERAL`; el registro de ausencia pasa a ejecutarse exclusivamente de forma automática vía `flask procesar-ausencias` (`app/src/__init__.py`) -> `TurnoService.procesar_turnos_vencidos()`. | Actualizada v1.2. |
