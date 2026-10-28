# WORKFLOW: Escenario 6 – Pagar un estudio particular
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-6`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Paciente` |
| **Objetos** | `Estudio`, `Presupuesto`, `Cupón`, `API de cupones`, `Aviso` |
| **Verbos** | `Pagar presupuesto`, `Sacar turno` *(habilitado tras el pago)* |
| **Estados** | `Creado` *(permanece en `Creado` con pago vigente hasta que el paciente ejecuta `Sacar turno` y pasa a `Turno sacado`)* |

---

## Overview

- **Objetivo**: Registrar el pago particular en un único pago (simulado) del `Presupuesto` de un `Estudio`, permitiendo opcionalmente aplicar un `Cupón` de descuento validado contra la `API de cupones`, dejando asentado el movimiento financiero en `pagos` (`TipoPago.PARTICULAR`) y habilitando al `Paciente` para `Sacar turno`.
- **Contexto**: El `Paciente` realiza el `Estudio` de forma particular (o decidió abonarlo de forma particular), el `Estudio` se encuentra en estado `Creado` (`EstadoEstudio.CREADO`) y cuenta con su `Presupuesto` emitido por el `Administrativo`. El pago se realiza en un solo pago (no en cuotas) y por ahora es simulado, pero debe quedar obligatoriamente registrado a nivel financiero en la tabla `pagos`. Si el `Paciente` había perdido un pago anterior por acumular 5 ausencias a turnos (`Pago.anulado == True` y `Estudio.estado == EstadoEstudio.CREADO`), este flujo le permite volver a pagar para habilitar nuevamente `Sacar turno`.
- **Recursos**: `Estudio` en estado `Creado`, `Presupuesto` emitido, medio de pago simulado, `Cupón` opcional (código numérico o PDF con QR, ver Escenario 30), `API de cupones`, tabla `pagos`.
- **Episodios**:
  1. El `Paciente` selecciona la opción de pago particular para su `Estudio` con `Presupuesto` emitido y, si posee un `Cupón` asignado por su `Médico`, lo ingresa o sube para aplicar el descuento.
  2. El `Paciente` confirma y completa el pago simulado en un solo pago por el monto resultante.
  3. El sistema valida la vigencia del `Cupón` en la `API de cupones` (si se aplicó), registra el movimiento financiero en la tabla `pagos` (`TipoPago.PARTICULAR`, `anulado = False`), reinicia `estudio.ausencias = 0` (si venía de un ciclo previo anulado por 5 ausencias) y avisa a la `API de cupones` para vencer el `Cupón`.
  4. El `Estudio` queda con pago vigente (`anulado = False`) y habilitado para que el `Paciente` pueda `Sacar turno` (Escenario 7).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` | Sujeto LEL que abona el `Presupuesto` en un solo pago simulado y opcionalmente aplica un `Cupón`. |
| `API de cupones` | Objeto LEL externo que valida si el `Cupón` está vigente y lo vence al ser utilizado. |
| `router` (`pagos_router`) | Capa HTTP Flask (`POST /api/v1/estudios/{estudio_id}/pagos`). Verifica autenticación del `Paciente` y formato del payload. |
| `service` (`economia_service`) | Capa de negocio que verifica la existencia de `Presupuesto`, ausencia de pago activo previo, vigencia del `Cupón`, cálculo del monto neto y registro del `Pago`. |
| `repo` (`economia_repo`, `estudio_repo`, `usuario_repo`) | Capa de acceso a datos SQLAlchemy sobre `estudios`, `presupuestos`, `pagos`, `cupones`, `avisos`. |
| `clients` (`cupones_client`, `notificacion_client`) | Clientes HTTP hacia `API de cupones` y servicio de correo/avisos. |
| `PostgreSQL` | Base de datos relacional donde se persiste el registro financiero en `pagos`. |

---

## Prerequisites

- El usuario autenticado tiene `Usuario.rol == Rol.PACIENTE`, `debe_cambiar_password == False` y es titular del `Estudio` (`estudio.paciente.usuario_id == usuario_actual.id`).
- El `Estudio` (`estudios.id == estudio_id`) existe y se encuentra en `estudio.estado == EstadoEstudio.CREADO`.
- Existe un `Presupuesto` emitido para el `Estudio` (`estudio.presupuesto is not None`).
- No existe ningún registro en `pagos` para ese `presupuesto_id` con `anulado == False` (si hubo un pago anterior que se perdió por 5 ausencias, dicho pago tiene `anulado == True`).

---

## Trigger

El `Paciente` visualiza el `Presupuesto` de su `Estudio` en su panel, opcionalmente ingresa el código o QR de un `Cupón`, y presiona `"Pagar presupuesto"`:
- **Endpoint HTTP**: `POST /api/v1/estudios/{estudio_id}/pagos` (autenticado con rol `paciente`).

---

## Workflow Tree

### STEP 1: Validación de titularidad del `Paciente`, estado `Creado`, `Presupuesto` y ausencia de pago activo
**Actor**: `router` (`pagos_router`) -> `service` (`economia_service`) -> `repo` (`estudio_repo`, `economia_repo`)
**Action**:
1. Verifica que el usuario autenticado tenga `Usuario.rol == Rol.PACIENTE`.
2. Carga el `Estudio` con `SELECT ... FOR UPDATE` junto con su `Presupuesto` y su lista de `pagos`.
3. Verifica que `estudio.paciente.usuario_id == usuario_actual.id`.
4. Verifica que `estudio.estado == EstadoEstudio.CREADO`.
5. Verifica que `estudio.presupuesto is not None`.
6. Comprueba que no exista ningún `Pago` en `estudio.presupuesto.pagos` con `anulado == False`.
**Timeout**: `2s`
**Input**: `estudio_id`, `codigo_cupon` (opcional), `monto_confirmado_usd` (opcional), `usuario_actual`.
**Output on SUCCESS**: `Estudio` y `Presupuesto` listos para pago -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no es `Rol.PACIENTE` o no es titular del `Estudio` -> `return 403 Forbidden` (`code: "FORBIDDEN_NOT_OWNER"`).
  - `FAILURE(not_found)`: `estudio_id` no existe -> `return 404 Not Found` (`code: "ESTUDIO_NO_ENCONTRADO"`).
  - `FAILURE(validation_error)`: El `Estudio` aún no tiene `Presupuesto` emitido -> `return 422 Unprocessable Entity` (`{"ok": false, "error": "El estudio aún no posee un presupuesto emitido para abonar", "code": "SIN_PRESUPUESTO", "retryable": false}`).
  - `FAILURE(conflict)`: Ya existe un `Pago` activo (`anulado == False`) para este `Presupuesto`, o el `Estudio` no está en estado `Creado` -> `return 409 Conflict` (`{"ok": false, "error": "El presupuesto de este estudio ya se encuentra pagado", "code": "PAGO_YA_REGISTRADO", "retryable": false}`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Spinner `"Procesando pago..."`.
  - **Operator sees**: Transacción iniciada sobre `estudios` y `presupuestos`.
  - **Database**: Lectura `FOR UPDATE` en `estudios`, `presupuestos` y `pagos`.
  - **Logs**: `[economia_service] STEP 1 pago particular iniciado estudio_id=<id> paciente_id=<pid>`

---

### STEP 2: Validación de `Cupón` con `API de cupones` y cálculo de importes (Condicional)
**Actor**: `service` (`economia_service`) -> `repo` (`economia_repo`) + `clients` (`cupones_client`)
**Action**:
- **Rama 2A (Sin cupón)**:
  - `descuento_cupon_usd = Decimal("0.00")`
  - `monto_usd = presupuesto.monto_total_usd`
  - Pasa directo a `STEP 3`.
- **Rama 2B (Con `codigo_cupon` — Escenario 30)**:
  1. Busca el `Cupón` en la tabla `cupones` por `codigo == input.codigo_cupon`.
  2. Verifica que exista, que `cupon.usado == False` y que haya sido asignado a este `Paciente` (`cupon.paciente_id == estudio.paciente_id`).
  3. Consulta a la `API de cupones` (`GET /api/v1/cupones/{codigo}/vigencia`) si el `Cupón` continúa vigente.
  4. Calcula:
     - `descuento_cupon_usd = round(presupuesto.monto_total_usd * (cupon.descuento_porcentaje / Decimal("100")), 2)`
     - `monto_usd = max(Decimal("0.00"), presupuesto.monto_total_usd - descuento_cupon_usd)`
**Timeout**: `5s` (con 2 reintentos con backoff de `1s` y `2s` hacia la `API de cupones`).
**Input**: `Presupuesto`, `codigo_cupon` (opcional), `estudio.paciente_id`.
**Output on SUCCESS**: `monto_usd`, `descuento_cupon_usd`, entidad `Cupon` (si aplica) -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(validation_error)`: El `Cupón` no existe, pertenece a otro `Paciente`, ya figura `usado == True` o la `API de cupones` informa `vigente: false` -> `return 422 Unprocessable Entity` (`{"ok": false, "error": "El cupón ingresado no es válido, no está asignado a este paciente o ha vencido", "code": "CUPON_INVALIDO_O_VENCIDO", "retryable": false}`).
  - `FAILURE(transient_external_error)` / `FAILURE(timeout)`: La `API de cupones` no responde tras 3 intentos -> `return 502 Bad Gateway` (`code: "CUPONES_API_UNAVAILABLE", "retryable": true`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: `"Validando cupón de descuento..."` (si ingresó cupón).
  - **Operator sees**: Consulta saliente a `API de cupones`.
  - **Database**: Lectura en `cupones`.
  - **Logs**: `[cupones_client] STEP 2 cupon=<codigo> descuento_usd=<desc> monto_final_usd=<monto>`

---

### STEP 3: Registro financiero del `Pago`, vencimiento del `Cupón` en `API de cupones` y habilitación para `Sacar turno`
**Actor**: `service` (`economia_service`) -> `repo` (`economia_repo`, `estudio_repo`) + `clients` (`cupones_client`) -> `PostgreSQL`
**Action**:
1. Inserta una fila en la tabla `pagos`:
   - `presupuesto_id = presupuesto.id`
   - `tipo = TipoPago.PARTICULAR`
   - `monto_usd = monto_usd`
   - `cupon_id = cupon.id if cupon else None`
   - `descuento_cupon_usd = descuento_cupon_usd`
   - `cobertura_obra_social_usd = Decimal("0.00")`
   - `anulado = False`
   - `fecha = func.now()`
2. Si el `Estudio` tenía `ausencias > 0` (por haber vuelto a `Creado` tras 5 ausencias en un ciclo previo) o tenía `obra_social_id` sin usar, reinicia `estudio.ausencias = 0`. El `Estudio` permanece en `EstadoEstudio.CREADO` (según el LEL, `Estado: Creado -> El paciente paga el presupuesto y puede sacar turno. El estudio pasa a Turno sacado cuando el paciente saca el turno`), quedando habilitado por tener un `Pago` activo (`anulado == False`).
3. Si se utilizó un `Cupón`:
   - Marca `cupon.usado = True` y `cupon.usado_en = func.now()`.
   - Envía notificación a la `API de cupones` (`POST /api/v1/cupones/{codigo}/consumir`) para vencer el `Cupón` externamente.
4. Crea un `Aviso` en `avisos` para el `Paciente` (`"Pago registrado por USD <monto_usd>. Ya puede solicitar su turno de extracción."`).
5. Ejecuta `session.commit()`.
**Timeout**: `5s`
**Input**: `Estudio`, `Presupuesto`, `monto_usd`, `descuento_cupon_usd`, `Cupon` (opcional).
**Output on SUCCESS**: `Pago` persistido (`pago.id`) y `Estudio` habilitado para `Sacar turno` -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(transient_external_error)`: La `API de cupones` falla al vencer el cupón tras 2 reintentos -> `GO TO ABORT_CLEANUP` (`return 502 Bad Gateway`, `code: "CUPON_CONSUME_FAILED"`, `retryable: true`).
  - `FAILURE(db_error)` / `FAILURE(timeout)`: Error al confirmar en `PostgreSQL` -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Comprobante `"Pago registrado exitosamente"` y botón `"Sacar turno de extracción"` habilitado.
  - **Operator sees**: Nuevo movimiento financiero en el tablero/listado de `pagos` (`tipo = 'particular'`, `anulado = False`).
  - **Database**: Fila insertada en `pagos`; si hubo cupón, `cupones.usado = True` y `cupones.usado_en != NULL`; `estudios.ausencias = 0`; fila en `avisos`.
  - **Logs**: `[economia_repo] STEP 3 pago_id=<pid> presupuesto_id=<pr_id> monto_usd=<monto> cupon_id=<cid>`

---

### ABORT_CLEANUP: Reversión del pago particular
**Triggered by**: Fallo al vencer el cupón en `API de cupones` o fallo de base de datos en `STEP 3`.
**Actions**:
  1. Ejecutar `session.rollback()` revirtiendo la inserción en `pagos`, la actualización en `cupones` y `avisos`.
  2. Registrar el error en logs y retornar respuesta HTTP `502` / `503` con `retryable: true`.
**What customer (`Paciente`) sees**: Mensaje de error indicando que el pago no pudo ser procesado y que puede reintentar sin que su cupón haya quedado inutilizado.
**What operator sees**: Log de error; 0 registros duplicados o inconsistentes en `pagos`.

---

## State Transitions

```
[Estudio.estado = CREADO ("Creado"), Presupuesto emitido, sin Pago activo (anulado=False)]
   |
   |-- (STEP 1-3 tienen éxito sin Cupón)
   |       --> Pago creado (tipo = TipoPago.PARTICULAR, monto_usd = monto_total_usd, anulado = False)
   |       --> Estudio.ausencias = 0
   |       --> Estudio.estado = EstadoEstudio.CREADO (con Pago activo -> habilitado para Sacar turno)
   |
   |-- (STEP 1-3 tienen éxito con Cupón vigente)
   |       --> Cupon.usado = True (y vencido en API de cupones)
   |       --> Pago creado (tipo = TipoPago.PARTICULAR, descuento_cupon_usd > 0, anulado = False)
   |       --> Estudio.estado = EstadoEstudio.CREADO (con Pago activo -> habilitado para Sacar turno)
   |
   +-- (Cualquier fallo en STEP 1-3 -> ABORT_CLEANUP)
           --> [Sin Pago activo, Cupon.usado permanece False]
```

---

## Handoff Contracts

### 1. Frontend Paciente -> Backend (`router` -> `service`)
**Endpoint**: `POST /api/v1/estudios/{estudio_id}/pagos`
**Payload**:
```json
{
  "codigo_cupon": "DESC-25-OFF",
  "simulacion_confirmada": true
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "pago_id": 104,
    "estudio_id": 101,
    "presupuesto_id": 33,
    "tipo": "particular",
    "monto_presupuesto_usd": "560.00",
    "descuento_cupon_usd": "140.00",
    "monto_usd": "420.00",
    "cupon_id": 4,
    "anulado": false,
    "estado_estudio": "Creado",
    "habilitado_sacar_turno": true
  }
}
```
**Failure response** (`403` / `404` / `409` / `422` / `502`):
```json
{
  "ok": false,
  "error": "El cupón ingresado no es válido, no está asignado a este paciente o ha vencido",
  "code": "CUPON_INVALIDO_O_VENCIDO",
  "retryable": false
}
```
**Timeout**: `10s`
**ON FAILURE**: Rollback transaccional mediante `ABORT_CLEANUP`.

---

### 2. Backend (`cupones_client`) -> `API de cupones`
**Endpoints**:
- `GET /api/v1/cupones/{codigo}/vigencia`
- `POST /api/v1/cupones/{codigo}/consumir`
**Payload** (en `POST /consumir`):
```json
{
  "codigo": "DESC-25-OFF",
  "usado_en": "2026-10-28T17:00:00Z"
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "codigo": "DESC-25-OFF",
  "vigente": false,
  "usado": true
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "El cupón ya fue utilizado o expiró",
  "code": "VOUCHER_EXPIRED",
  "retryable": false
}
```
**Timeout**: `5s` (hasta 3 intentos con backoff `1s`, `2s`).
**ON FAILURE**: Si `retryable == false`, rechazar con `422 Unprocessable Entity`; si `retryable == true` y agota reintentos, ejecutar `ABORT_CLEANUP` y devolver `502 Bad Gateway`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Registro en `pagos` (`TipoPago.PARTICULAR`) | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Actualización `cupones.usado = True` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Reinicio `estudios.ausencias = 0` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Registro en `avisos` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `.ai/2-Glosario_LEL.md`, no existe un estado llamado `"Pagado"` dentro de los 14 estados de `EstadoEstudio`. El LEL define en `Estado: Creado`: *"El paciente paga el presupuesto y puede sacar turno. El estudio pasa a Turno sacado cuando el paciente saca el turno"*. | High | State Transitions & STEP 3 | Se respeta estrictamente el LEL y `app/src/core/models/enums.py`: el `Estudio` permanece en `EstadoEstudio.CREADO` con un registro `Pago` activo (`anulado = False`), lo que habilita `Sacar turno` en el Escenario 7. |
| RC-2 | En `app/src/core/models/economia.py`, `Pago` soporta múltiples filas por `presupuesto_id` (`pagos: Mapped[list["Pago"]]`), donde los pagos perdidos por 5 ausencias tienen `anulado = True` y el pago vigente tiene `anulado = False`. | Low | STEP 1 & STEP 3 | Documentado el filtro `anulado == False` para determinar si el estudio tiene un pago particular vigente. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path pago particular sin cupón** | `POST /api/v1/estudios/{id}/pagos` con `{"codigo_cupon": null}` por el `Paciente` titular. | Retorna `201 Created`; crea `Pago` con `tipo = TipoPago.PARTICULAR`, `monto_usd == presupuesto.monto_total_usd`, `anulado = False`; `habilitado_sacar_turno == True`. |
| **TC-02: Happy path pago particular aplicando cupón vigente (Escenario 30)** | `POST /api/v1/estudios/{id}/pagos` con `{"codigo_cupon": "DESC-25-OFF"}` asignado al paciente y vigente en `API de cupones`. | Retorna `201 Created`; aplica el porcentaje de descuento en `descuento_cupon_usd`, marca `Cupon.usado = True` y notifica el vencimiento a la `API de cupones`. |
| **TC-03: Nuevo pago tras perder el pago anterior por 5 ausencias (Escenario 33)** | `POST /api/v1/estudios/{id}/pagos` en un estudio que volvió a `Creado` con `ausencias == 5` y un `Pago` previo con `anulado == True`. | Retorna `201 Created`; crea un nuevo `Pago` con `anulado = False` y reinicia `Estudio.ausencias = 0`. |
| **TC-04: Intento de pagar dos veces un mismo presupuesto activo** | Segunda llamada a `POST /api/v1/estudios/{id}/pagos` cuando ya existe un `Pago` con `anulado == False`. | Retorna `409 Conflict` (`code: "PAGO_YA_REGISTRADO"`); no crea un segundo pago. |
| **TC-05: Intento de aplicar cupón vencido o asignado a otro paciente** | `POST /api/v1/estudios/{id}/pagos` con un `codigo_cupon` cuyo `paciente_id` es distinto o vencido en `API de cupones`. | Retorna `422 Unprocessable Entity` (`code: "CUPON_INVALIDO_O_VENCIDO"`); 0 registros en `pagos`. |
| **TC-06: Intento de pagar un estudio sin presupuesto emitido** | `POST /api/v1/estudios/{id}/pagos` cuando `estudio.presupuesto is None`. | Retorna `422 Unprocessable Entity` (`code: "SIN_PRESUPUESTO"`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El pago particular es simulado en un solo pago, por lo que no hay pasarela bancaria externa real; el sistema registra directamente el movimiento financiero al confirmar el paciente. | `.ai/1-Entrevista.md` líneas 63-64, 185-186, 355-357 y `.ai/2-Glosario_LEL.md` (`Verbo: Pagar presupuesto`). | Bajo. |

## Open Questions

- Si el `Paciente` sube el PDF del cupón con QR en lugar de escribir el código numérico, ¿el frontend decodifica el QR para enviar `codigo_cupon` o envía el PDF al backend? *(En `economia.py` línea 37, `Cupon.codigo` almacena tanto el código numérico como el contenido del QR, por lo que el contrato unifica ambos en `codigo_cupon`).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/economia.py` y `estudios.py`. | Marcada como `Approved`. |
