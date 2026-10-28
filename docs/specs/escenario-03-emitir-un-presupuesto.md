# WORKFLOW: Escenario 3 – Emitir un presupuesto
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-3`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Administrativo`, `Paciente` |
| **Objetos** | `Estudio`, `Gen`, `Presupuesto`, `Obra social`, `API de obras sociales`, `Aviso` |
| **Verbos** | `Pagar presupuesto` *(habilitado a continuación)* |
| **Estados** | `Creado`, `Pendiente de autorización` |

---

## Overview

- **Objetivo**: Determinar el costo en dólares del `Estudio` de exoma clínico solicitado (incluyendo la extracción en un único pago) y registrar el `Presupuesto` correspondiente para que el `Paciente` lo abone de forma particular o se tramite la autorización por su `Obra social`.
- **Contexto**: El `Médico` dio de alta un `Estudio` de exoma clínico (en estado `Creado`) y el `Administrativo` del laboratorio central debe emitir su `Presupuesto`. Según el LEL y `app/src/core/models/reglas.py`, el precio fijo es de **500 USD hasta 5 genes** (`PRECIO_BASE_USD = 500`, `GENES_INCLUIDOS = 5`) y **30 USD por cada gen adicional** (`PRECIO_GEN_ADICIONAL_USD = 30`).
- **Recursos**: `Estudio` (`estudio_id`), cantidad total de `Genes` asociados en `estudios_genes`, función de dominio `calcular_precio(cantidad_genes)`, `Obra social` (si el estudio/paciente utiliza cobertura), `Presupuesto`.
- **Episodios**:
  1. El `Administrativo` consulta el `Estudio` pendiente de presupuestar y la cantidad total de `Genes` asociados a él.
  2. El sistema calcula el precio base de hasta cinco `Genes` (`500 USD`).
  3. El sistema agrega el costo correspondiente a los `Genes` adicionales (`30 USD` por cada `Gen` por encima de 5).
  4. El sistema registra el `Presupuesto` asociado al `Estudio`. Si el `Estudio` se tramita por `Obra social` (`estudio.obra_social_id != None`), el `Estudio` pasa a `Pendiente de autorización` y se registra la solicitud en `autorizaciones` (`ResultadoAutorizacion.PENDIENTE`); si es particular, permanece en `Creado` a la espera del pago del `Paciente`, y se notifica al `Paciente` mediante `Aviso` y correo electrónico.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Administrativo` | Sujeto LEL del laboratorio central que emite el `Presupuesto` del `Estudio`. |
| `Paciente` | Sujeto LEL que recibe la notificación del `Presupuesto` emitido para pagar o aguardar la autorización de su `Obra social`. |
| `router` (`presupuestos_router`) | Capa HTTP Flask (`POST /api/v1/estudios/{estudio_id}/presupuesto`). Verifica sesión activa y rol `Rol.ADMINISTRATIVO`. |
| `service` (`economia_service`) | Capa de negocio que cuenta los `Genes` del `Estudio`, invoca `calcular_precio(cantidad_genes)`, consulta la cobertura de la `Obra social` y persiste el `Presupuesto`. |
| `repo` (`economia_repo`, `estudio_repo`) | Capa de acceso a datos SQLAlchemy sobre `estudios`, `estudios_genes`, `presupuestos`, `obras_sociales`, `autorizaciones`, `avisos`. |
| `clients` (`obras_sociales_client`, `notificacion_client`) | Clientes HTTP hacia la `API de obras sociales` (para consultar porcentaje de cobertura y registrar el trámite externo si aplica) y servicio de notificaciones. |
| `PostgreSQL` | Base de datos relacional con restricción `UNIQUE(estudio_id)` en la tabla `presupuestos`. |

---

## Prerequisites

- El usuario autenticado tiene sesión activa y `Usuario.rol == Rol.ADMINISTRATIVO`.
- Existe el `Estudio` (`estudios.id == estudio_id`) en estado `EstadoEstudio.CREADO`.
- El `Estudio` tiene al menos 1 `Gen` asociado en la tabla `estudios_genes`.
- No existe aún ningún registro en `presupuestos` para ese `estudio_id` (`presupuestos.estudio_id` es `UNIQUE`).

---

## Trigger

El `Administrativo` selecciona un `Estudio` en estado `Creado` sin presupuesto en su bandeja de trámites y acciona `"Emitir presupuesto"`:
- **Endpoint HTTP**: `POST /api/v1/estudios/{estudio_id}/presupuesto` (autenticado con rol `administrativo`).

---

## Workflow Tree

### STEP 1: Validación de rol del `Administrativo` y estado del `Estudio`
**Actor**: `router` (`presupuestos_router`) -> `service` (`economia_service`) -> `repo` (`estudio_repo`, `economia_repo`)
**Action**:
1. Verifica que el usuario autenticado tenga `Usuario.rol == Rol.ADMINISTRATIVO`.
2. Obtiene el `Estudio` por `estudio_id` (con bloqueo de fila `SELECT ... FOR UPDATE` para prevenir emisión concurrente por dos administrativos).
3. Verifica que `estudio.estado == EstadoEstudio.CREADO` y que `estudio.presupuesto is None`.
4. Cuenta la cantidad de filas en `estudios_genes` para `estudio_id` (`cantidad_genes`). Verifica que `cantidad_genes >= 1`.
**Timeout**: `2s`
**Input**: `estudio_id`, `usuario_actual` (`Administrativo`), `obra_social_id` opcional en payload si se actualiza en este paso.
**Output on SUCCESS**: `Estudio` bloqueado en transacción y `cantidad_genes >= 1` -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario autenticado no tiene `Rol.ADMINISTRATIVO` -> `return 403 Forbidden` (`code: "FORBIDDEN_ROLE"`).
  - `FAILURE(not_found)`: `estudio_id` no existe -> `return 404 Not Found` (`code: "ESTUDIO_NO_ENCONTRADO"`).
  - `FAILURE(conflict)`: El `Estudio` ya tiene un `Presupuesto` emitido (`estudio.presupuesto is not None`) -> `return 409 Conflict` (`{"ok": false, "error": "El estudio ya posee un presupuesto emitido", "code": "PRESUPUESTO_YA_EMITIDO", "retryable": false}`).
  - `FAILURE(invalid_state)`: `estudio.estado != EstadoEstudio.CREADO` -> `return 409 Conflict` (`code: "ESTADO_ESTUDIO_INVALIDO"`).
  - `FAILURE(validation_error)`: `cantidad_genes == 0` -> `return 422 Unprocessable Entity` (`code: "ESTUDIO_SIN_GENES"`).

**Observable states during this step**:
  - **Customer/Actor (`Administrativo`) sees**: Spinner `"Calculando presupuesto..."`.
  - **Operator sees**: Transacción iniciada sobre `estudios`.
  - **Database**: Lectura con `FOR UPDATE` sobre `estudios` y conteo en `estudios_genes`.
  - **Logs**: `[economia_service] STEP 1 iniciado estudio_id=<id> administrativo_id=<uid> cantidad_genes=<n>`

---

### STEP 2: Cálculo del monto con `calcular_precio` y consulta a `API de obras sociales` (si aplica)
**Actor**: `service` (`economia_service`) -> `reglas.calcular_precio` + `clients` (`obras_sociales_client`)
**Action**:
1. Invoca `calcular_precio(cantidad_genes)` de `app/src/core/models/reglas.py`:
   - `extra = max(0, cantidad_genes - 5)`
   - `monto_total_usd = Decimal("500") + Decimal("30") * extra`
2. Si `estudio.obra_social_id is not None`:
   - Consulta la `API de obras sociales` (`GET /api/v1/obras-sociales/{rnos}`) para refrescar el `porcentaje_cobertura` en la tabla local `obras_sociales` y, si la API externa recibe el alta de solicitud de autorización (nombre del paciente + fecha, según comentario en `economia.py` línea 91), envía `POST /api/v1/autorizaciones` para obtener `solicitud_externa_id`.
**Timeout**: `5s` (con 2 reintentos de `1s` y `2s` hacia la `API de obras sociales`).
**Input**: `cantidad_genes`, `estudio.obra_social` (opcional), `estudio.paciente`.
**Output on SUCCESS**: `monto_total_usd`, `porcentaje_cobertura` (si hay obra social) y `solicitud_externa_id` (opcional) -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(transient_external_error)` / `FAILURE(timeout)`: Si la `API de obras sociales` falla al consultar cobertura, usa el `porcentaje_cobertura` almacenado en la copia local `obras_sociales` (`ObraSocial.porcentaje_cobertura`) y deja `solicitud_externa_id = None` para gestión telefónica/manual del `Administrativo` (según `.ai/1-Entrevista.md` línea 183), registrando un warning en logs sin abortar la emisión del presupuesto.

**Observable states during this step**:
  - **Customer/Actor (`Administrativo`) sees**: Desglose calculado (`500 USD` base + `30 USD x extra`).
  - **Operator sees**: Cálculo aritmético ejecutado; consulta opcional a `API de obras sociales`.
  - **Database**: Posible actualización de `obras_sociales.porcentaje_cobertura`.
  - **Logs**: `[economia_service] STEP 2 monto_total_usd=<monto> cantidad_genes=<n> obra_social_id=<os_id>`

---

### STEP 3: Persistencia del `Presupuesto`, transición de estado (si tiene `Obra social`) y `Aviso` al `Paciente`
**Actor**: `service` (`economia_service`) -> `repo` (`economia_repo`, `estudio_repo`, `usuario_repo`) -> `PostgreSQL`
**Action**:
1. Inserta una fila en la tabla `presupuestos`:
   - `estudio_id = estudio.id`
   - `emitido_por_id = usuario_actual.id` (`Administrativo`)
   - `cantidad_genes = cantidad_genes`
   - `monto_total_usd = monto_total_usd`
2. Evalúa la modalidad de financiación del `Estudio`:
   - **Si `estudio.obra_social_id is not None`**:
     - Cambia `estudio.estado = EstadoEstudio.PENDIENTE_AUTORIZACION` (`"Pendiente de autorizacion"`).
     - Inserta una fila inicial en `autorizaciones` con `estudio_id = estudio.id`, `resultado = ResultadoAutorizacion.PENDIENTE`, `solicitud_externa_id = solicitud_externa_id`.
   - **Si `estudio.obra_social_id is None` (Pago particular)**:
     - Mantiene `estudio.estado = EstadoEstudio.CREADO` (a la espera del pago particular o de que el paciente seleccione obra social).
3. Inserta un `Aviso` en `avisos` para el `Paciente` (`usuario_id = estudio.paciente.usuario_id`, `canal = CanalAviso.APP` y `CanalAviso.MAIL`) informando que el `Presupuesto` de `monto_total_usd` USD ya está disponible.
4. Ejecuta `session.commit()`.
**Timeout**: `4s`
**Input**: `estudio`, `emitido_por_id`, `cantidad_genes`, `monto_total_usd`, `solicitud_externa_id`
**Output on SUCCESS**: `Presupuesto` persistido -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(conflict)`: `IntegrityError` en `presupuestos.estudio_id` -> `session.rollback()` -> `return 409 Conflict` (`code: "PRESUPUESTO_YA_EMITIDO"`).
  - `FAILURE(db_error)` / `FAILURE(timeout)`: Error de base de datos -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Administrativo`) sees**: Confirmación `"Presupuesto #<id> emitido por USD <monto>"`.
  - **Actor (`Paciente`) sees**: `Aviso` en su panel y detalle del `Presupuesto` (con opción de `"Pagar presupuesto"` si es particular o estado `"Pendiente de autorización"` si es por `Obra social`).
  - **Database**: Fila creada en `presupuestos`; si hay `Obra social`, fila en `autorizaciones` (`resultado = PENDIENTE`) y `estudios.estado = EstadoEstudio.PENDIENTE_AUTORIZACION`; fila en `avisos`.
  - **Logs**: `[economia_repo] STEP 3 presupuesto_id=<pid> estudio_id=<eid> monto_usd=<monto> estado_estudio=<estado>`

---

### ABORT_CLEANUP: Reversión de emisión de presupuesto
**Triggered by**: Fallo de base de datos en `STEP 3`.
**Actions**:
  1. Ejecutar `session.rollback()` revirtiendo la inserción en `presupuestos`, `autorizaciones`, `avisos` y cualquier cambio en `estudios.estado`.
  2. Retornar `500 Internal Server Error` / `503 Service Unavailable` con `retryable: true`.
**What customer (`Administrativo`) sees**: Mensaje de error al emitir el presupuesto; el estudio continúa en la bandeja de pendientes para reintentar.
**What operator sees**: Log de error transaccional; `Estudio` permanece en `EstadoEstudio.CREADO` sin `Presupuesto`.

---

## State Transitions

```
[Estudio.estado = CREADO, sin Presupuesto]
   |-- (STEP 1-3 tienen éxito y estudio.obra_social_id IS NULL [Particular])
   |       --> Presupuesto creado (monto_total_usd = 500 + 30 * max(0, cantidad_genes - 5))
   |       --> Estudio.estado permanece en EstadoEstudio.CREADO ("Creado")
   |
   |-- (STEP 1-3 tienen éxito y estudio.obra_social_id IS NOT NULL [Obra social])
   |       --> Presupuesto creado (monto_total_usd = 500 + 30 * max(0, cantidad_genes - 5))
   |       --> Autorizacion creada (resultado = ResultadoAutorizacion.PENDIENTE)
   |       --> Estudio.estado pasa a EstadoEstudio.PENDIENTE_AUTORIZACION ("Pendiente de autorizacion")
   |
   +-- (Cualquier fallo en STEP 1-3)
           --> [Estudio.estado = CREADO, sin Presupuesto]
```

---

## Handoff Contracts

### 1. Frontend Administrativo -> Backend (`router` -> `service`)
**Endpoint**: `POST /api/v1/estudios/{estudio_id}/presupuesto`
**Payload**:
```json
{
  "obra_social_id": 5
}
```
*(Nota: `obra_social_id` es opcional en el body si ya fue establecido en el `Estudio`, o permite confirmar si el trámite va por `Obra social` o `null` para particular).*
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "presupuesto_id": 33,
    "estudio_id": 101,
    "emitido_por_id": 12,
    "cantidad_genes": 7,
    "precio_base_usd": "500.00",
    "genes_adicionales": 2,
    "costo_adicional_usd": "60.00",
    "monto_total_usd": "560.00",
    "estado_estudio": "Pendiente de autorizacion",
    "porcentaje_cobertura_obra_social": "80.00"
  }
}
```
**Failure response** (`403` / `404` / `409` / `422`):
```json
{
  "ok": false,
  "error": "El estudio ya posee un presupuesto emitido",
  "code": "PRESUPUESTO_YA_EMITIDO",
  "retryable": false
}
```
**Timeout**: `8s`
**ON FAILURE**: Rollback transaccional mediante `ABORT_CLEANUP`.

---

### 2. Backend (`obras_sociales_client`) -> `API de obras sociales`
**Endpoint**: `GET /api/v1/obras-sociales` / `POST /api/v1/solicitudes-autorizacion`
**Payload** (cuando se notifica solicitud de autorización a la API de obras sociales):
```json
{
  "rnos": "115404",
  "paciente_nombre": "Juan Pérez",
  "paciente_dni": "40123456",
  "fecha": "2026-10-28",
  "monto_total_usd": "560.00"
}
```
**Success response** (`200 OK` / `201 Created`):
```json
{
  "ok": true,
  "solicitud_externa_id": "OS-2026-00981",
  "porcentaje_cobertura": "80.00"
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Servicio externo de obras sociales no disponible",
  "code": "OBRAS_SOCIALES_API_DOWN",
  "retryable": true
}
```
**Timeout**: `5s`
**ON FAILURE**: Usar los datos de la tabla local `obras_sociales` (`Copia local de la API de obras sociales`) y continuar con `solicitud_externa_id = null`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Registro en `presupuestos` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Registro en `autorizaciones` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Cambio de `estudios.estado` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Registro en `avisos` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/reglas.py`, la función `calcular_precio(cantidad_genes: int) -> Decimal` ya está implementada con `PRECIO_BASE_USD = Decimal("500")`, `GENES_INCLUIDOS = 5` y `PRECIO_GEN_ADICIONAL_USD = Decimal("30")`. | Low | STEP 2 | Se invoca directamente `calcular_precio` en `economia_service`. |
| RC-2 | En `app/src/core/models/economia.py`, `Presupuesto` tiene `estudio_id` con `unique=True`, `emitido_por_id` (`ForeignKey("usuarios.id")`), `cantidad_genes` y `monto_total_usd` (`Numeric(10, 2)`). | Low | STEP 3 | Coincidencia exacta de columnas y tipos. |
| RC-3 | En `app/src/core/models/economia.py`, `Autorizacion` incluye el campo `solicitud_externa_id` con el comentario: *"Id que devuelve la API de obras sociales al dar de alta el estudio (nombre del paciente + fecha); la obra social autoriza o rechaza desde su propia web"*. | Low | STEP 2 & STEP 3 | Documentado el registro de `Autorizacion` con `ResultadoAutorizacion.PENDIENTE` y `solicitud_externa_id`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path estudio con hasta 5 genes (particular)** | `POST /api/v1/estudios/{id}/presupuesto` por un `Administrativo` en un estudio particular con 4 genes. | Retorna `201 Created`; `Presupuesto.cantidad_genes == 4`, `Presupuesto.monto_total_usd == Decimal("500.00")`; `Estudio.estado == EstadoEstudio.CREADO`. |
| **TC-02: Happy path estudio con exactamente 5 genes** | `POST /api/v1/estudios/{id}/presupuesto` en un estudio con 5 genes. | Retorna `201 Created`; `Presupuesto.monto_total_usd == Decimal("500.00")`. |
| **TC-03: Happy path estudio con más de 5 genes (ej. 8 genes)** | `POST /api/v1/estudios/{id}/presupuesto` en un estudio con 8 genes (5 base + 3 adicionales). | Retorna `201 Created`; `Presupuesto.cantidad_genes == 8`, `Presupuesto.monto_total_usd == Decimal("590.00")` (`500 + 3 * 30`). |
| **TC-04: Estudio con obra social pasa a Pendiente de autorización** | `POST /api/v1/estudios/{id}/presupuesto` en un estudio con `obra_social_id != None` y 6 genes. | Retorna `201 Created`; `Presupuesto.monto_total_usd == Decimal("530.00")`; `Estudio.estado == EstadoEstudio.PENDIENTE_AUTORIZACION`; se crea fila en `autorizaciones` con `resultado = ResultadoAutorizacion.PENDIENTE`. |
| **TC-05: Intento de emitir presupuesto duplicado para el mismo estudio** | Segunda llamada a `POST /api/v1/estudios/{id}/presupuesto` sobre un estudio que ya tiene presupuesto. | Retorna `409 Conflict` (`code: "PRESUPUESTO_YA_EMITIDO"`); no altera el presupuesto existente. |
| **TC-06: Usuario sin rol Administrativo** | `POST /api/v1/estudios/{id}/presupuesto` invocado por un `Médico` o `Paciente`. | Retorna `403 Forbidden` (`code: "FORBIDDEN_ROLE"`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Todos los `Genes` en `estudios_genes` (sean `PATOLOGIA`, `MANUAL` o `HALLAZGO_SECUNDARIO`) se contabilizan en `Presupuesto.cantidad_genes` para la fórmula `500 USD hasta 5 genes + 30 USD por gen adicional`. | `.ai/2-Glosario_LEL.md` (`Objeto: Estudio`) y `app/src/core/models/economia.py` (`Presupuesto.cantidad_genes`). | Bajo. |
| A2 | Si el `Paciente` no tenía `obra_social_id` al crearse el estudio, puede seleccionarla antes de pagar (pasando el estudio de `Creado` a `Pendiente de autorización`), o bien informarse al emitir el presupuesto. | `.ai/2-Glosario_LEL.md` (`Estado: Creado` -> `El estudio pasa a Pendiente de autorización si el paciente elige obra social`). | Bajo. |

## Open Questions

- ¿Puede el `Paciente` cambiar de modalidad `Obra social` a `Particular` si su `Obra social` demora en responder mientras está en `Pendiente de autorización`?

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/economia.py` y `reglas.py`. | Marcada como `Approved`. |
