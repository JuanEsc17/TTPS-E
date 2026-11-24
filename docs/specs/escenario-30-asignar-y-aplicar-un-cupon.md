# WORKFLOW: Escenario 30 – Asignar y aplicar un cupón
**Versión**: 1.2
**Fecha**: 2026-11-24
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-30`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Gerente médico** | `Usuario` (`rol = Rol.GERENTE_MEDICO`) + `Medico` (`Cupon.gerente_id`) |
| **Sujetos** | **Médico** | `Usuario` (`rol = Rol.MEDICO` o `Rol.GERENTE_MEDICO`) + `Medico` (`Cupon.medico_id`, médico tratante) |
| **Sujetos** | **Paciente** | `Usuario` (`rol = Rol.PACIENTE`) + `Paciente` (`Cupon.paciente_id`, `Estudio.paciente_id`) |
| **Objetos** | **Cupón** | Modelo `Cupon` (tabla `cupones`) |
| **Objetos** | **Presupuesto** | Modelo `Presupuesto` (tabla `presupuestos`), `Pago` (`pagos`) y `Cuota` (`cuotas`) |
| **Objetos** | **Estudio** | Modelo `Estudio` (tabla `estudios`) |
| **Objetos** | **Obra social** | Modelo `ObraSocial` (tabla `obras_sociales`: `porcentaje_cobertura`) |
| **Objetos** | **API de cupones** | Cliente HTTP externo (`app/src/clients/cupones_client.py`): `asignar_cupon_a_medico`, `asignar_cupon_a_paciente` y `canjear_cupon` (este último valida vigencia y uso, y vence el cupón) |
| **Objetos** | **API de MercadoPago** | Pasarela externa (`mercadopago_client.py`) cuando el pago particular se abona en un pago o en cuotas |
| **Verbos** | **Pagar presupuesto** | Acción del **paciente** que abona el **presupuesto** aplicando el **cupón** y habilita **sacar turno** |
| **Estados** | **Creado**, **Autorizado** | `EstadoEstudio.CREADO` (pago particular) o `EstadoEstudio.AUTORIZADO` (copago remanente con **obra social**) |

---

## Overview

- **Objetivo:** Entregar un **cupón** a un **paciente** y que este lo utilice al pagar el **presupuesto** de su **estudio**, acumulando el descuento con la cobertura de su **obra social** si corresponde.
- **Contexto:** Existe un **cupón** creado (Escenario 29) y un **paciente** con un **estudio** que cuenta con **presupuesto** emitido pendiente de pago.
- **Recursos:** **Cupón** (`cupones`), **paciente** (`pacientes`), **presupuesto** (`presupuestos`), **pago** (`pagos`), **obra social** (`obras_sociales`), **API de cupones**.
- **Episodios:**
  1. El **médico** asigna el **cupón** al **paciente** (habiendo sido previamente asignado el cupón al **médico** por el **gerente médico**).
  2. El **paciente** aplica el **cupón** (mediante código numérico o archivo PDF/QR) al pagar el **presupuesto**.
  3. El sistema verifica que el **cupón** pertenezca al **paciente**, no esté usado y no haya vencido (`vigente_hasta`).
  4. El sistema aplica el descuento, que se acumula con la cobertura de la **obra social**, y registra financieramente el pago en la tabla `pagos`.
  5. Cuando **MercadoPago** confirma el pago (`approved`), el sistema canjea el **cupón** en la **API de cupones** para que venza y marca `cupones.usado = True`.

**Resumen del flujo:** El escenario tiene dos etapas sobre `Cupon`:
1. **Asignación (`STEP 1`):** El **gerente médico** asigna un **cupón** disponible a un **médico** (`PATCH /api/v1/cupones/{cupon_id}/asignar-medico`). Después, el **médico** lo asigna a su **paciente** (`PATCH /api/v1/cupones/{cupon_id}/asignar-paciente`). En los dos casos primero se llama a la **API de cupones** y después se actualiza la base local.
2. **Aplicación en el pago (`STEP 2` a `STEP 5`, integrado con Escenario 06):** El **paciente** inicia el pago (`POST /api/v1/estudios/{estudio_id}/pagos` con `codigo_cupon` y `cantidad_cuotas >= 1`). El servicio bloquea el **cupón** (`FOR UPDATE`) y verifica que sea del **paciente**, que no esté usado y que no haya vencido. Calcula el monto neto acumulando la cobertura de la **obra social** y el descuento del **cupón** (con tope en el 100% del presupuesto) **antes de dividir en cuotas**, y crea el `Pago` (`PENDIENTE`) con su preferencia de **MercadoPago**. **El cupón no se consume todavía.** Recién cuando llega el webhook `approved` se invoca `POST /canjear_cupon` y se marca `usado = True`, `usado_en = now()`. Así un checkout abandonado no quema el cupón (ADR-001).
---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Gerente médico** (Sujeto LEL) | Asigna un **cupón** creado a un **médico** tratante (si no fue asignado durante el Escenario 29). |
| **Médico** (Sujeto LEL) | Asigna uno de sus **cupones** disponibles a un **paciente** que atiende. |
| **Paciente** (Sujeto LEL) | Aplica el **cupón** (código o QR) en el momento de **pagar presupuesto**. |
| **Router HTTP** (`app/src/web/api/cupones.py` / `app/src/web/api/pagos.py`) | Valida sesión, rol (`GERENTE_MEDICO`, `MEDICO`, `PACIENTE`) y estructura de los payloads. |
| **Servicio de Cupones y Pagos** (`app/src/core/services/cupon_service.py` / `economia_service.py`) | Reglas de asignación, cálculo del descuento acumulado, coordinación con la **API de cupones** y **MercadoPago**, atomicidad. |
| **Cliente API de Cupones** (`app/src/clients/cupones_client.py`) | `POST /asignar_cupon_a_medico`, `POST /asignar_cupon_a_paciente`, `POST /canjear_cupon` (header `X-API-Key`). |
| **Repositorio** (`app/src/core/repos/cupon_repo.py` / `economia_repo.py`) | Lee y actualiza `cupones`, `presupuestos`, `pagos`, `cuotas`, `estudios` y `obras_sociales` con bloqueo `FOR UPDATE`. |
| **PostgreSQL** (`db`) | Garantiza integridad referencial y aislamiento transaccional. |

---

## Prerequisites

- **Sesión y Rol:**
  - Para asignar a un **médico**: sesión activa con `Rol.GERENTE_MEDICO`.
  - Para asignar a un **paciente**: sesión activa con `Rol.MEDICO` (o `Rol.GERENTE_MEDICO` actuando como médico tratante).
  - Para aplicar el **cupón** al pagar: sesión activa con `Rol.PACIENTE` (`Usuario.debe_cambiar_password == False`).
- **Datos existentes en `app/src/core/models/`:**
  - Existe una fila en `cupones` con `usado == False`.
  - Existe una fila en `pacientes` vinculada al **médico** tratante (`pacientes.medico_id == medicos.id` o un `Estudio` de ese paciente con `estudios.medico_id == medicos.id`).
  - Existe un `Estudio` del **paciente** con un `Presupuesto` emitido en la tabla `presupuestos` (`presupuestos.estudio_id == estudios.id`) que aún no posee un `Pago` activo (`pagos.anulado == False`).
- **Estado previo del `Estudio`:**
  - `Estudio.estado == EstadoEstudio.CREADO` (para pago particular) o `Estudio.estado == EstadoEstudio.AUTORIZADO` (cuando existe cobertura parcial de **obra social** y el paciente abona el copago aplicando el **cupón**).

---

## Trigger

1. **Asignación:** El **gerente médico** asigna el **cupón** a un **médico** (`PATCH /api/v1/cupones/{cupon_id}/asignar-medico`). El **médico** lo asigna a un **paciente** (`PATCH /api/v1/cupones/{cupon_id}/asignar-paciente`).
2. **Aplicación al pagar:** El **paciente** envía `POST /api/v1/estudios/{estudio_id}/pagos` con `codigo_cupon` y `cantidad_cuotas`. La confirmación llega por `POST /api/v1/webhooks/mercadopago`.

---

## Workflow Tree

### STEP 1: Asignación del cupón al médico y del médico al paciente
**Actor**: **Gerente médico** / **Médico** -> Router (`cupones.py`) -> `cupon_service` -> `cupones_client` + `cupon_repo`

**1A – Gerente médico asigna a médico** (`PATCH /api/v1/cupones/{cupon_id}/asignar-medico`, body `{ "medico_id": 12 }`):
  1. Verifica que `cupon.gerente_id == gerente.id`, `cupon.medico_id IS NULL`, `cupon.usado == False` y que exista el `medico_id`.
  2. Llama a `cupones_client.asignar_cupon_a_medico(gerente_id=str(gerente.id), medico_id=str(medico.id), codigo=cupon.codigo)`.
  3. Actualiza `cupones.medico_id` y hace `COMMIT`.

**1B – Médico asigna a paciente** (`PATCH /api/v1/cupones/{cupon_id}/asignar-paciente`, body `{ "paciente_id": 45 }`):
  1. Verifica que `cupon.medico_id == medico_actual.id`, `cupon.paciente_id IS NULL`, `cupon.usado == False` y `cupon.vigente_hasta > now()`. También verifica que el **paciente** esté vinculado al **médico** y que **no tenga otro cupón** registrado (regla de la API: un cupón por paciente por grupo, aunque esté usado).
  2. Llama a `cupones_client.asignar_cupon_a_paciente(medico_id=str(medico.id), paciente_id=str(paciente.id), codigo=cupon.codigo)`.
  3. Actualiza `cupones.paciente_id`, crea un `Aviso` (`CanalAviso.APP`) para el **paciente** y hace `COMMIT`.

**Timeout**: `15s` (llamada externa). Sin reintentos automáticos.
**Output on SUCCESS**: `200 OK` con el cupón actualizado.
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Gerente que no emitió el cupón, o médico que no es su titular -> `403` (`CUPON_NO_PERTENECE_AL_MEDICO`). Paciente no atendido por el médico -> `403` (`PACIENTE_NO_VINCULADO`).
  - `FAILURE(not_found)`: `cupon_id`, `medico_id` o `paciente_id` inexistentes -> `404` (`CUPON_NO_ENCONTRADO` / `MEDICO_NO_ENCONTRADO` / `PACIENTE_NO_ENCONTRADO`).
  - `FAILURE(invalid_state)`: Cupón usado, ya asignado o vencido -> `409` (`CUPON_YA_ASIGNADO_O_USADO`). Paciente con cupón previo (local o `409` de la API) -> `409` (`PACIENTE_YA_TIENE_CUPON`).
  - `FAILURE(external)`: API con timeout o conexión fallida -> `503`; API con 5xx -> `502` (`CUPONES_API_NO_DISPONIBLE`, retryable). API con 400/404 -> `502` (`CUPONES_API_RECHAZO`).
  - `FAILURE(database_error)` después de que la API aceptó la asignación -> `rollback`, log `CRITICAL CUPON_DESYNC_ALERT` y `500` (`DB_ERROR`).
---

### STEP 2: Inicio de pago del presupuesto y bloqueo local del cupón
**Actor**: **Paciente** -> Router (`pagos.py`) -> Servicio (`pago_service.py`) -> Repositorio (`economia_repo.py`)
**Action**: El **paciente** solicita pagar el **presupuesto** de su `estudio_id` indicando `codigo_cupon`. El repositorio verifica que el `Estudio` pertenezca al **paciente**, que esté en `EstadoEstudio.CREADO` (o `EstadoEstudio.AUTORIZADO`), que exista `Presupuesto` emitido sin un `Pago` activo (`anulado == False`), y obtiene el `Cupon` por `codigo` con `SELECT ... FOR UPDATE NOWAIT` verificando que `cupon.paciente_id == paciente.id` y `cupon.usado == False`.
**Timeout**: `2s`
**Input**:
```json
{
  "estudio_id": 88,
  "paciente_autenticado_id": 45,
  "codigo_cupon": "EXOMA-2026-88412",
  "cantidad_cuotas": 3 
}
```
**Output on SUCCESS**: `{ estudio: Estudio, presupuesto: Presupuesto, cupon: Cupon }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El `Estudio` no pertenece al **paciente** autenticado, o el `Cupon` está asignado a otro `paciente_id` -> retornar `403 Forbidden` (`CUPON_AJENO` o `ESTUDIO_AJENO`).
  - `FAILURE(invalid_state)`:
    - El `Estudio` no tiene `Presupuesto` emitido -> retornar `409 Conflict` (`PRESUPUESTO_NO_EMITIDO`).
    - Ya existe un `Pago` con `anulado == False` para ese `Presupuesto` -> retornar `409 Conflict` (`PRESUPUESTO_YA_PAGADO`).
    - El `Cupon` tiene `usado == True` -> retornar `409 Conflict` (`CUPON_YA_UTILIZADO`).
  - `FAILURE(conflict)`: Otra transacción concurrente está intentando usar el mismo `Cupon` o pagar el mismo `Presupuesto` (`LockNotAvailable`) -> retornar `409 Conflict` (`OPERACION_EN_CURSO`, `retryable=True`).
  - `FAILURE(validation_error)`: `codigo_cupon` no existe en la tabla `cupones` -> retornar `404 Not Found` (`CUPON_NO_ENCONTRADO`).

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: Botón de pago deshabilitado con estado "Validando cupón y procesando pago...".
  - Operator sees: Transacción iniciada sobre `cupones` y `presupuestos`.
  - Database: Lectura con bloqueo de fila sobre `cupones`; sin escrituras aún.
  - Logs: `[pago_service] step=2_validacion_previa estudio_id=88 cupon_codigo=EXOMA-2026-88412`

---

### STEP 3: Validación de vigencia del cupón (sin consumirlo)
**Actor**: Servicio (`economia_service.py`)
**Action**: Verifica `cupon.vigente_hasta > now()`. **No llama a `canjear_cupon` todavía**, porque eso vence el cupón y el pago todavía no está confirmado. La **API de cupones** no tiene un endpoint de consulta por código. La validación definitiva la hace `canjear_cupon` en `STEP 5`.
**Output on SUCCESS**: `{ cupon, descuento_porcentaje }` -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(invalid_state)`: `vigente_hasta <= now()` -> `409` (`CUPON_NO_VIGENTE`, `retryable=False`), sin crear `Pago`.
---

### STEP 4: Cálculo del descuento acumulado y creación del Pago pendiente
**Actor**: Servicio (`economia_service.py`) -> `economia_repo` + `mercadopago_client` (ver Escenario 06, STEP 3)
**Action**:
  1. `cobertura_obra_social_usd = round(monto_total_usd * porcentaje_cobertura / 100, 2)` (`0.00` si es particular).
  2. `descuento_bruto_usd = round(monto_total_usd * cupon.descuento_porcentaje / 100, 2)`
     `descuento_cupon_usd = min(descuento_bruto_usd, monto_total_usd - cobertura_obra_social_usd)`
     `monto_usd = max(0.00, monto_total_usd - cobertura_obra_social_usd - descuento_cupon_usd)`
  3. Divide `monto_usd` en `cantidad_cuotas` e inserta `Pago` (`estado = PENDIENTE`, `cupon_id`, `descuento_cupon_usd`, `cobertura_obra_social_usd`) y las `Cuotas`. Después crea la preferencia de **MercadoPago** para la cuota #1.
  4. Si `monto_usd == 0.00` (cobertura + cupón llegan al 100%): no pasa por **MercadoPago** y va directo a `STEP 5`.
**Output on SUCCESS**: `201` con `{ pago_id, init_point, cuotas, descuento_cupon_usd, ... }`. El cupón sigue `usado = False`.
**Output on FAILURE**: Los del Escenario 06, STEP 3 (MercadoPago o base de datos), con `rollback`. El cupón no se toca.

---

### STEP 5: Confirmación del pago y canje del cupón
**Actor**: **MercadoPago** -> `POST /api/v1/webhooks/mercadopago` -> `economia_service` -> `cupones_client` + `economia_repo` (ver Escenario 06, STEP 4)
**Action**: Cuando el webhook verifica el pago `approved` de la cuota #1 (o cuando el monto es `0.00` en `STEP 4`):
  1. Si `pago.cupon_id` existe y `cupon.usado == False`: llama a `cupones_client.canjear_cupon(paciente_id=str(paciente.id), codigo=cupon.codigo)`.
  2. Marca `cupones.usado = True` y `usado_en = now()`, actualiza `Pago`/`Cuota` según el Escenario 06 y hace `COMMIT`.
  3. Es idempotente: si `cupon.usado == True` (webhook duplicado), no vuelve a canjear.
**Output on SUCCESS**: `200 OK` a **MercadoPago**. El **paciente** queda habilitado para **Sacar turno**.
**Output on FAILURE**:
  - `FAILURE(transient)`: API de cupones con timeout o 5xx -> `rollback` y `503` a **MercadoPago** para que reintente el webhook.
  - `FAILURE(cupón rechazado por la API: 400 vencido / 409 ya usado)`: el pago ya fue cobrado con descuento, así que **no se revierte**. Se marca `usado = True` igual y se emite log `CRITICAL VOUCHER_DESYNC_ALERT` para conciliación.

---

### ABORT_CLEANUP: Reversión ante fallo en STEP 5 tras consumir cupón en API externa
**Triggered by**: Error de base de datos en `STEP 5` después de que `STEP 4` consumió el **cupón** en la **API de cupones**.
**Actions** (in order):
  1. `db.session.rollback()`.
  2. Si `canjear_cupon` ya respondió OK pero falla el `COMMIT`: el reintento del webhook vuelve a llamar a `canjear_cupon`, que responde `409` (ya usado). Ese `409` se toma como "ya canjeado" y se marca `usado = True` localmente. La **API de cupones** no ofrece `/restaurar`.
  3. Cualquier otra inconsistencia: log `CRITICAL VOUCHER_DESYNC_ALERT` con `cupon_id`, `codigo`, `paciente_id` y `estudio_id`.
**What customer/actor (**Paciente**) sees**: Mensaje de error indicando que el pago no pudo completarse y que no se realizó ningún cargo; su cupón permanece asignado.
**What operator sees**: Alerta `VOUCHER_DESYNC_ALERT` o confirmación de compensación exitosa en logs.

---

## State Transitions

```
Cupon (cupones / estado en la API):
  [Disponible (medico_id=NULL, paciente_id=NULL) / "disponible"]
    -- (STEP 1A) --> [Asignado a Médico / "medico"]
    -- (STEP 1B) --> [Asignado a Paciente / "paciente"]
    -- (STEP 4: pago creado PENDIENTE) --> [Asignado a Paciente (sin cambios)]
    -- (STEP 5: webhook approved + canjear_cupon) --> [Usado (usado=True, usado_en=now()) / "usado"]

Pago (pagos):
  [Inexistente]
    -- (STEP 5 exitoso) --> [Registrado (anulado=False, cupon_id=<C>, descuento_cupon_usd=<D>, cobertura_obra_social_usd=<OS>, monto_usd=<M>)]

Estudio (estudios.estado):
  [EstadoEstudio.CREADO] -- (Pago particular con cupón registrado en `pagos`) --> [EstadoEstudio.CREADO (con pago activo -> habilitado para Sacar turno -> pasará a EstadoEstudio.TURNO_SACADO)]
  [EstadoEstudio.AUTORIZADO] -- (Copago con cupón registrado en `pagos`) --> [EstadoEstudio.AUTORIZADO (habilitado para Sacar turno -> pasará a EstadoEstudio.TURNO_SACADO)]
```

---

## Handoff Contracts

### 1A. Gerente médico -> Backend: `PATCH /api/v1/cupones/{cupon_id}/asignar-medico`
**Payload**: `{ "medico_id": 12 }` -> **200**: `{ "ok": true, "data": { "id": 105, "codigo": "53399388", "medico_id": 12, "paciente_id": null, "usado": false, ... } }`

### 1B. Médico -> Backend: `PATCH /api/v1/cupones/{cupon_id}/asignar-paciente`
**Payload**: `{ "paciente_id": 45 }` -> **200**: `{ "ok": true, "data": { "id": 105, "codigo": "53399388", "medico_id": 12, "paciente_id": 45, "usado": false, ... } }`
**Failure**: `{ "ok": false, "error": "...", "code": "PACIENTE_YA_TIENE_CUPON", "retryable": false }`

### 2. Paciente -> Backend: `POST /api/v1/estudios/{estudio_id}/pagos`
**Payload**: `{ "cantidad_cuotas": 3, "codigo_cupon": "53399388" }`
**201**: `{ "ok": true, "data": { "pago_id": 301, "estado": "pendiente", "monto_total_presupuesto_usd": 500.00, "cobertura_obra_social_usd": 200.00, "descuento_cupon_usd": 125.00, "monto_usd": 175.00, "cupon_id": 105, "init_point": "https://...", "cuotas": [...] } }`

### 3. Backend (`cupones_client`) -> API de cupones (header `X-API-Key`)
| Operación | Endpoint | Payload | OK |
|---|---|---|---|
| Asignar a médico | `POST /asignar_cupon_a_medico` | `{ "p_gerente_id": "4", "p_medico_id": "12", "p_codigo": "53399388" }` | `200 true` |
| Asignar a paciente | `POST /asignar_cupon_a_paciente` | `{ "p_medico_id": "12", "p_paciente_id": "45", "p_codigo": "53399388" }` | `200 true` (`409` si el paciente ya tiene cupón) |
| Canjear | `POST /canjear_cupon` | `{ "p_paciente_id": "45", "p_codigo": "53399388" }` | `200 true` (`400` vencido, `409` ya usado) |
**Timeout**: `15s`. Sin reintentos automáticos de escritura.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Asignación en la **API de cupones** (1A/1B) | Step 1 | — | Sin desasignación en la API: log `CRITICAL CUPON_DESYNC_ALERT` si falla el commit local |
| `Pago` `PENDIENTE` + `Cuotas` | Step 4 | `rollback` | `db.session.rollback()` |
| Canje en la **API de cupones** | Step 5 | — | Sin `/restaurar`: el reintento del webhook trata el `409` como "ya canjeado" |
---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | El modelo `Pago` en `app/src/core/models/economia.py` ya incluye `cupon_id`, `descuento_cupon_usd` y `cobertura_obra_social_usd`, soportando de forma nativa la acumulación entre descuento de **cupón** y cobertura de **obra social**. | Low | STEP 4, STEP 5 | La especificación mapea exactamente los 3 importes (`monto_usd`, `descuento_cupon_usd`, `cobertura_obra_social_usd`) sobre `Pago`. |
| RC-2 | El LEL establece que `EstadoEstudio` solo pasa a `Turno sacado` cuando el **paciente** reserva el **turno** (`Sacar turno`), no al pagar. | Medium | State Transitions, STEP 5 | Confirmado: el pago con cupón inserta en `pagos` (`anulado = False`) y habilita la acción `Sacar turno`, manteniendo `Estudio.estado` en `Creado` (o `Autorizado`) hasta que el paciente elija su turno. |
| RC-3 | Si la suma de `ObraSocial.porcentaje_cobertura` + `Cupon.descuento_porcentaje` supera el `100%`, el monto a pagar no debe ser negativo. | Medium | STEP 4 | Se especificó `descuento_cupon_usd = min(descuento_bruto_usd, remanente_tras_os)` y `monto_usd >= 0.00`. |
| RC-4 | La **API de cupones** real no tiene `/vigencia`, `/consumir` ni `/restaurar`. Expone `asignar_cupon_a_medico`, `asignar_cupon_a_paciente` y `canjear_cupon`, y permite un solo cupón por paciente por grupo. | High | STEP 1, 3, 4, 5, ABORT_CLEANUP, Handoff | La vigencia se valida en local con `vigente_hasta` y el canje se hace en el webhook `approved` (Esc. 06 v2.0, ADR-001). Se agregó `PACIENTE_YA_TIENE_CUPON`. |
| RC-5 | La v1.1 se contradecía: el resumen canjeaba en el webhook y el STEP 4 consumía antes del pago. | High | STEP 4, STEP 5 | Unificado: se canjea solo en el webhook `approved`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01` | Gerente asigna su cupón disponible a un médico | `200`, llama a `asignar_cupon_a_medico`, `cupones.medico_id` seteado |
| `TC-02` | Médico titular asigna el cupón a su paciente | `200`, llama a `asignar_cupon_a_paciente`, `paciente_id` seteado, crea `Aviso` |
| `TC-03` | Médico que no es titular intenta asignar | `403 CUPON_NO_PERTENECE_AL_MEDICO`, no llama a la API |
| `TC-04` | Paciente que ya tiene un cupón (local o `409` de la API) | `409 PACIENTE_YA_TIENE_CUPON` |
| `TC-05` | Pago particular de 500 USD con cupón de 20% | `201`, `Pago PENDIENTE` con `descuento_cupon_usd=100.00` y `monto_usd=400.00`. Cupón **sigue** `usado=False` y **no** se llama a `canjear_cupon` |
| `TC-06` | Obra social 40% + cupón 25% sobre 500 USD | `cobertura=200.00`, `descuento=125.00`, `monto_usd=175.00` |
| `TC-07` | Obra social 80% + cupón 50% sobre 500 USD | `cobertura=400.00`, `descuento=100.00` (tope), `monto_usd=0.00` -> canje directo sin MercadoPago |
| `TC-08` | `codigo_cupon` asignado a otro paciente | `403 CUPON_AJENO`, sin `Pago` |
| `TC-09` | Cupón con `vigente_hasta` vencido | `409 CUPON_NO_VIGENTE`, sin `Pago` |
| `TC-10` | Cupón con `usado=True` | `409 CUPON_YA_UTILIZADO` |
| `TC-11` | Webhook `approved` de un pago con cupón | Llama a `canjear_cupon` y marca `usado=True` y `usado_en` |
| `TC-12` | Webhook `approved` duplicado | No vuelve a llamar a `canjear_cupon` |
| `TC-13` | Webhook `approved` con la API de cupones caída | `503` a MercadoPago, rollback, cupón sigue `usado=False` |
| `TC-14` | Webhook `approved` y la API responde `409` (ya usado) | Marca `usado=True` y log `VOUCHER_DESYNC_ALERT`. El pago no se revierte |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Cuando el **paciente** sube el PDF con QR o ingresa el código numérico, el frontend o el router extrae el `codigo` unificado (`Cupon.codigo`) para procesarlo. | Verificado en `app/src/core/models/economia.py` (`codigo: Mapped[str] = mapped_column(String(80), unique=True) # codigo numerico o contenido del QR`). | Bajo; ambos formatos se normalizan sobre `Cupon.codigo`. |
| A2 | La acumulación de descuento de **cupón** y **obra social** se calcula sobre el `monto_total_usd` del `Presupuesto`, truncando el descuento al saldo remanente para que el monto a pagar nunca sea menor que `0.00 USD`. | Verificado en `.ai/2-Glosario_LEL.md` ("se acumula con la cobertura de la obra social") y `.ai/3-Escenarios.md#Escenario-30`. | Bajo. |

## Open Questions

- Si un **paciente** aplica un **cupón** en un pago y posteriormente pierde el pago por faltar 5 veces al turno de extracción (`Pago.anulado = True`, Escenario 33), ¿el **cupón** permanece definitivamente vencido (`usado = True`)? *(Se asume que sí: el cupón ya fue consumido en el pago anulado y no se rehabilita).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada alineada con `Cupon`, `Presupuesto`, `Pago` y `ObraSocial` en `app/src/core/models/economia.py`. | Aprobada. |
| 2026-11-17 | Adaptada al flujo de pago en cuotas con `MercadoPago` (Esc. 06 v2.0): descuento prorrateado antes de generar cuotas y consumo del cupón diferido al webhook `approved`. | Actualizada a v1.1. |
| 2026-11-24 | La spec usaba `/external/vouchers/*` (vigencia, consumir, restaurar), que no existen en la API real, y se contradecía sobre cuándo consumir el cupón. | Actualizada a v1.2: endpoints reales, canje en el webhook `approved`, vigencia local, un cupón por paciente y rutas `/api/v1`. |