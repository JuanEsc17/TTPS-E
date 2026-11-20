# WORKFLOW: Escenario 6 – Pagar un estudio particular
**Versión**: 2.0
**Fecha**: 2026-11-17
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-6`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Paciente`, `Administrativo` *(consulta posterior de cuotas)* |
| **Objetos** | `Estudio`, `Presupuesto`, `API de MercadoPago`, `Cuota`, `Cupón`, `API de cupones`, `Registro de modificaciones`, `Aviso` |
| **Verbos** | `Pagar presupuesto`, `Pagar cuota`, `Sacar turno` *(habilitado al confirmarse pago único o cuota 1)*, `Registrar modificación` |
| **Estados** | `Creado` *(permanece en `Creado` con pago vigente hasta que el paciente ejecuta `Sacar turno` y pasa a `Turno sacado`)* |

---

## Overview

- **Objetivo**: Iniciar y confirmar el pago particular del `Presupuesto` de un `Estudio` en **un solo pago o en cuotas** a través de **MercadoPago**, aplicando opcionalmente un `Cupón` de descuento validado contra la `API de cupones`, generando el registro financiero en `pagos` y el cronograma en `cuotas`, y habilitando al `Paciente` para `Sacar turno` una vez confirmado el pago único o la primera cuota.
- **Contexto**: El `Paciente` realiza el `Estudio` de forma particular, el `Estudio` se encuentra en estado `Creado` (`EstadoEstudio.CREADO`) y cuenta con su `Presupuesto` emitido por el `Administrativo`. Conforme a los nuevos requerimientos y al [ADR-001](../ADRs/ADR-001-pagos-en-cuotas-mercadopago.md), el pago simulado previo se reemplaza por integración real con la `API de MercadoPago` (Checkout Pro + Webhook), admitiendo `cantidad_cuotas >= 1` (por ejemplo `1, 3, 6, 12`). Si el `Paciente` perdió un pago previo por acumular 5 ausencias (`Pago.anulado == True`), puede iniciar un nuevo plan de pago.
- **Recursos**: `Estudio` en estado `Creado`, `Presupuesto` emitido, `API de MercadoPago` (`mercadopago_client`), tabla `pagos`, tabla `cuotas`, `Cupón` opcional (Escenario 30), tabla `registro_modificaciones`.
- **Episodios**:
  1. El `Paciente` selecciona el pago particular para su `Estudio` con `Presupuesto` emitido, elige si abona en 1 pago o en `N` `Cuotas` (ej. `1, 3, 6, 12`) y opcionalmente ingresa un `Cupón`.
  2. El sistema valida la vigencia del `Cupón` en la `API de cupones` (sin consumirlo todavía), calcula el monto neto y crea el registro `Pago` (`estado = PENDIENTE`), las `N` filas en `cuotas` y la preferencia en la `API de MercadoPago` para el pago único o la primera `Cuota`.
  3. El `Paciente` completa el pago en el checkout de `MercadoPago`.
  4. Al recibir el webhook de `MercadoPago` y verificar el pago aprobado (`GET /v1/payments/{id}`), el sistema marca la `Cuota` #1 como `pagada`, actualiza el `Pago` (`pagado` si `N == 1`, `parcial` si `N > 1`), consume el `Cupón` en la `API de cupones` (si aplicó), reinicia `estudio.ausencias = 0` si correspondía (registrándolo en `registro_modificaciones`), y habilita al `Paciente` para `Sacar turno` (Escenario 7).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` | Sujeto LEL que elige modalidad (1 pago o `N` cuotas), aplica un `Cupón` opcional y completa el pago en `MercadoPago`. |
| `API de MercadoPago` | Pasarela externa que emite el `init_point` de Checkout Pro, procesa el cobro y envía el webhook `payment`. |
| `API de cupones` | Objeto LEL externo que valida la vigencia del `Cupón` y lo vence cuando el pago es confirmado por `MercadoPago`. |
| `router` (`pagos_router`, `webhooks_router`) | Capa HTTP Flask (`POST /api/v1/estudios/{estudio_id}/pagos` y `POST /api/v1/webhooks/mercadopago`). |
| `service` (`economia_service`, `auditoria_service`) | Capa de negocio que arma el plan de `Cuotas`, coordina `MercadoPago` y `API de cupones`, procesa webhooks de forma idempotente y audita cambios en `Estudio`. |
| `repo` (`economia_repo`, `estudio_repo`, `auditoria_repo`, `usuario_repo`) | Capa de acceso a datos SQLAlchemy sobre `estudios`, `presupuestos`, `pagos`, `cuotas`, `cupones`, `registro_modificaciones`, `avisos`. |
| `clients` (`mercadopago_client`, `cupones_client`, `notificacion_client`) | Clientes HTTP (`httpx`) hacia `API de MercadoPago`, `API de cupones` y correo/avisos. |
| `PostgreSQL` | Base de datos relacional que garantiza integridad transaccional del `Pago` y su plan de `Cuotas`. |

---

## Prerequisites

- El usuario autenticado tiene `Usuario.rol == Rol.PACIENTE`, `debe_cambiar_password == False` y es titular del `Estudio` (`estudio.paciente.usuario_id == usuario_actual.id`).
- El `Estudio` (`estudios.id == estudio_id`) existe y está en `estudio.estado == EstadoEstudio.CREADO`.
- Existe un `Presupuesto` emitido para el `Estudio` (`estudio.presupuesto is not None`).
- No existe ningún registro en `pagos` para ese `presupuesto_id` con `anulado == False` y `estado in (EstadoPago.PAGADO, EstadoPago.PARCIAL)`. (Si existía un `Pago` previo en estado `PENDIENTE` o `RECHAZADO` de un checkout abandonado o fallido, puede reemplazarse o reintentarse).
- Variables de entorno configuradas: `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_WEBHOOK_SECRET`.

---

## Trigger

1. **Inicio de pago y creación de preferencia**: El `Paciente` presiona `"Pagar con MercadoPago"` eligiendo `cantidad_cuotas` y `codigo_cupon` opcional -> `POST /api/v1/estudios/{estudio_id}/pagos`.
2. **Confirmación asíncrona de MercadoPago**: `MercadoPago` invoca `POST /api/v1/webhooks/mercadopago` al completarse el pago en Checkout Pro.

---

## Workflow Tree

### STEP 1: Validación de titularidad, estado `Creado`, `Presupuesto` y `cantidad_cuotas`
**Actor**: `router` (`pagos_router`) -> `service` (`economia_service`) -> `repo` (`estudio_repo`, `economia_repo`)
**Action**:
1. Verifica que el usuario autenticado tenga `Usuario.rol == Rol.PACIENTE` y `estudio.paciente.usuario_id == usuario_actual.id`.
2. Bloquea el `Estudio` (`SELECT ... FOR UPDATE`) y verifica `estudio.estado == EstadoEstudio.CREADO` y `estudio.presupuesto is not None`.
3. Valida `cantidad_cuotas` (`int >= 1` y dentro del máximo permitido configurado en `configuracion`, ej. `1..12`).
4. Comprueba que no exista ningún `Pago` vigente ya confirmado (`anulado == False` y `estado in (EstadoPago.PAGADO, EstadoPago.PARCIAL)`). Si existe un `Pago` previo en `PENDIENTE` o `RECHAZADO` sin cuotas pagadas, lo marca `anulado = True` / cancelado antes de emitir el nuevo plan.
**Timeout**: `2s`
**Input**: `estudio_id`, `cantidad_cuotas`, `codigo_cupon` (opcional), `usuario_actual`.
**Output on SUCCESS**: `Estudio`, `Presupuesto` y `cantidad_cuotas` validados -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: No es `Rol.PACIENTE` o no es titular -> `return 403 Forbidden` (`code: "FORBIDDEN_NOT_OWNER"`).
  - `FAILURE(not_found)`: `estudio_id` inexistente -> `return 404 Not Found` (`code: "ESTUDIO_NO_ENCONTRADO"`).
  - `FAILURE(validation_error)`: Sin `Presupuesto` (`SIN_PRESUPUESTO`) o `cantidad_cuotas` fuera del rango permitido (`CANTIDAD_CUOTAS_INVALIDA`) -> `return 422 Unprocessable Entity`.
  - `FAILURE(conflict)`: Ya existe un `Pago` activo confirmado (`PAGADO` o `PARCIAL` con `anulado == False`) -> `return 409 Conflict` (`code: "PAGO_YA_REGISTRADO"`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Indicador `"Preparando pago en MercadoPago..."`.
  - **Operator (`Administrativo`) sees**: Sin cambios aún en cuotas activas.
  - **Database**: Lectura `FOR UPDATE` sobre `estudios`, `presupuestos` y `pagos`.
  - **Logs**: `[economia_service] STEP 1 pago_mercadopago_iniciado estudio_id=<id> cuotas=<n>`

---

### STEP 2: Validación previa del `Cupón` y cálculo de cuotas
**Actor**: `service` (`economia_service`) -> `repo` (`economia_repo`) + `clients` (`cupones_client`)
**Action**:
1. Si `codigo_cupon` fue informado:
   - Verifica en `cupones` que exista, `cupon.usado == False` y `cupon.paciente_id == estudio.paciente_id`.
   - Consulta vigencia en `API de cupones` (`GET /cupones?estado=paciente...` o validación vigente); **no lo consume todavía** para evitar perder el cupón si el paciente abandona el checkout de `MercadoPago`.
   - Calcula `descuento_cupon_usd = round(presupuesto.monto_total_usd * (cupon.descuento_porcentaje / 100), 2)`.
   - Calcula `monto_neto_usd = max(Decimal("0.00"), presupuesto.monto_total_usd - descuento_cupon_usd)`.
2. Si no hay cupón: `descuento_cupon_usd = Decimal("0.00")` y `monto_neto_usd = presupuesto.monto_total_usd`.
3. Si `monto_neto_usd == Decimal("0.00")` (cupón 100%): registra directamente el `Pago` en estado `PAGADO` (`1` cuota en `0.00` pagada), consume el cupón y habilita `Sacar turno` sin pasar por `MercadoPago`.
4. De lo contrario, divide `monto_neto_usd` en `cantidad_cuotas` partes iguales (`monto_cuota_base = round(monto_neto_usd / cantidad_cuotas, 2)`, ajustando la diferencia de centavos en la cuota 1 para que la suma exacta sea `monto_neto_usd`), con `fecha_vencimiento` mensual (`hoy` para cuota 1, `+30 días * (i - 1)` o mismo día del mes siguiente para cuotas `2..N`).
**Timeout**: `5s`
**Input**: `Presupuesto`, `cantidad_cuotas`, `codigo_cupon` (opcional).
**Output on SUCCESS**: `monto_neto_usd`, `descuento_cupon_usd`, lista de `N` montos y vencimientos de `Cuota` -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(validation_error)`: `Cupón` inválido, ajeno, usado o vencido -> `return 422 Unprocessable Entity` (`code: "CUPON_INVALIDO_O_VENCIDO"`).
  - `FAILURE(transient_external_error)`: `API de cupones` no disponible tras 2 reintentos -> `return 502 Bad Gateway` (`code: "CUPONES_API_UNAVAILABLE", "retryable": true`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Resumen del plan (`N` cuotas de `$X`, vencimientos y descuento aplicado).
  - **Operator (`Administrativo`) sees**: Sin plan definitivo aún.
  - **Database**: Lectura de `cupones`.
  - **Logs**: `[economia_service] STEP 2 plan_calculado monto_neto=<monto> cuotas=<n> cupon=<cod>`

---

### STEP 3: Persistencia del `Pago` y `Cuotas` en estado `PENDIENTE` y creación de preferencia en `MercadoPago`
**Actor**: `service` (`economia_service`) -> `repo` (`economia_repo`) + `clients` (`mercadopago_client`) -> `PostgreSQL`
**Action**:
1. Inserta en `pagos` (`presupuesto_id`, `tipo = TipoPago.PARTICULAR`, `medio_pago = MedioPago.MERCADOPAGO`, `estado = EstadoPago.PENDIENTE`, `cantidad_cuotas`, `monto_usd = monto_neto_usd`, `cupon_id`, `descuento_cupon_usd`, `anulado = False`, `mp_external_reference = f"estudio:{estudio.id}:pago:{uuid}"`).
2. Inserta las `N` filas en `cuotas`: `pago_id`, `numero_cuota = 1..N`, `monto_usd = monto_cuota_i`, `fecha_vencimiento`, `estado = EstadoCuota.PENDIENTE`.
3. Invoca `MercadoPagoClient.crear_preferencia` (`POST /checkout/preferences`) por el monto de la **Cuota #1** (que equivale al total si `N == 1`), enviando `external_reference = f"pago:{pago.id}:cuota:{cuota_1.id}"`, `notification_url` del webhook y `back_urls`.
4. Guarda `mp_preference_id` en `pagos` y en `cuotas` (Cuota #1), y ejecuta `session.commit()`.
5. Retorna `201 Created` con `init_point` para que el frontend redirija al `Paciente` a `MercadoPago`.
**Timeout**: `8s` (hasta 2 reintentos ante 5xx/timeout de MercadoPago).
**Input**: `Pago`, lista de `Cuota`, datos del `Estudio`.
**Output on SUCCESS**: `{ pago_id, mp_preference_id, init_point, cuotas: [...] }` -> Aguarda webhook en `STEP 4`
**Output on FAILURE**:
  - `FAILURE(external_api_error)` / `FAILURE(timeout)`: La `API de MercadoPago` falla tras reintentos -> `GO TO ABORT_CLEANUP` (`session.rollback()`) -> `return 502 Bad Gateway` (`code: "MERCADOPAGO_UNAVAILABLE", "retryable": true`).
  - `FAILURE(db_error)`: Error de base de datos -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Redirección al checkout oficial de `MercadoPago` (`init_point`).
  - **Operator (`Administrativo`) sees**: Plan de pago y `N` cuotas en estado `pendiente` en su panel de cuotas (Escenario 39).
  - **Database**: Fila en `pagos` (`estado = 'pendiente'`), `N` filas en `cuotas` (`estado = 'pendiente'`).
  - **Logs**: `[mercadopago_client] STEP 3 preferencia_creada pago_id=<pid> mp_preference_id=<pref>`

---

### STEP 4: Recepción de Webhook de `MercadoPago`, verificación del pago y habilitación para `Sacar turno`
**Actor**: `API de MercadoPago` -> `router` (`POST /api/v1/webhooks/mercadopago`) -> `service` (`economia_service`, `auditoria_service`) -> `clients` (`mercadopago_client`, `cupones_client`) -> `repo`
**Action**:
1. Valida la firma HMAC `x-signature` usando `MERCADOPAGO_WEBHOOK_SECRET`. Si el evento no es de tipo `payment`, responde `200 OK` ignorándolo.
2. Consulta a la `API de MercadoPago` (`GET /v1/payments/{mp_payment_id}`) el estado verificado del pago y su `external_reference`.
3. Bloquea `Cuota`, `Pago` y `Estudio` (`SELECT ... FOR UPDATE`):
   - **Idempotencia**: Si la `Cuota` #1 ya tiene `estado == EstadoCuota.PAGADA` y `mp_payment_id == payment.id`, retorna `200 OK` sin duplicar efectos.
4. Evalúa `payment.status`:
   - **Si `payment.status == "approved"`**:
     - Marca `cuota_1.estado = EstadoCuota.PAGADA`, `cuota_1.mp_payment_id = payment.id`, `cuota_1.mp_status_detail = payment.status_detail`, `cuota_1.pagada_en = now()`.
     - Actualiza `pago.mp_payment_id = payment.id` y `pago.estado = EstadoPago.PAGADO` (si `cantidad_cuotas == 1`) o `EstadoPago.PARCIAL` (si `cantidad_cuotas > 1`).
     - Si `pago.cupon_id is not None`: verifica vigencia, marca `cupon.usado = True`, `cupon.usado_en = now()` e invoca `cupones_client.canjear_cupon` (`POST /canjear_cupon`). *(Si el cupón ya fue usado por otra carrera concurrente, aborta/rechaza según política o registra alerta crítica financiera).*
     - Si `estudio.ausencias > 0` (por ciclo previo perdido tras 5 ausencias), reinicia `estudio.ausencias = 0` y registra la modificación en `registro_modificaciones` (`entidad_tipo = 'estudio'`, `origen = 'webhook_mercadopago'`, `cambios = {"ausencias": {"anterior": 5, "nuevo": 0}}`).
     - Crea `Aviso` (`CanalAviso.APP` y `CanalAviso.MAIL`) para el `Paciente` informando que el pago/cuota 1 fue aprobado y ya puede `Sacar turno`.
   - **Si `payment.status in ("rejected", "cancelled")`**:
     - Marca `cuota_1.estado = EstadoCuota.RECHAZADA`, `cuota_1.mp_payment_id = payment.id`, `cuota_1.mp_status_detail = payment.status_detail`, y `pago.estado = EstadoPago.RECHAZADO`.
     - Crea `Aviso` al `Paciente` informando el rechazo para que reintente.
   - **Si `payment.status in ("in_process", "pending")`**:
     - Mantiene `PENDIENTE` registrando `mp_payment_id` y `mp_status_detail`.
5. Ejecuta `session.commit()` y responde `200 OK` a `MercadoPago`.
**Timeout**: `8s`
**Input**: Webhook JSON `{ type: "payment", data: { id: "9876543210" } }` + header `x-signature`.
**Output on SUCCESS**: `200 OK`; si `approved`, `habilitado_sacar_turno = True` -> `WORKFLOW COMPLETE` (cuotas `2..N` continúan en Escenario 38).
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Firma `x-signature` inválida -> `return 401 Unauthorized` (`code: "INVALID_MERCADOPAGO_SIGNATURE"`).
  - `FAILURE(transient_external_error)`: Fallo al consultar `GET /v1/payments/{id}` o consumir `Cupón` -> `GO TO ABORT_CLEANUP` -> `return 503 Service Unavailable` para que `MercadoPago` reintente el webhook con backoff.

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Confirmación de pago exitoso en su panel, detalle de cuotas restantes (si `N > 1`) y botón `"Sacar turno de extracción"` habilitado.
  - **Operator (`Administrativo`) sees**: En su vista de cuotas (Escenario 39), la cuota #1 aparece `pagada` con `mp_payment_id`, y las cuotas `2..N` en `pendiente` con sus fechas de vencimiento.
  - **Database**: `pagos.estado` (`pagado` o `parcial`), `cuotas` #1 `pagada`, `cupones.usado` (si aplicó), `registro_modificaciones` (si cambió `ausencias`), `avisos`.
  - **Logs**: `[economia_service] STEP 4 webhook_mercadopago payment_id=<id> status=<status> pago_id=<pid>`

---

### ABORT_CLEANUP: Reversión de creación de pago o procesamiento de webhook
**Triggered by**: Fallo de `API de MercadoPago`, `API de cupones` o `PostgreSQL` en `STEP 3` o `STEP 4`.
**Actions**:
  1. Ejecutar `session.rollback()` para revertir inserciones parciales en `pagos`, `cuotas`, `cupones`, `registro_modificaciones` y `avisos`.
  2. Si falló en `STEP 4` después de consumir externamente un `Cupón` pero antes del `commit`, invocar compensación o emitir alerta `CRITICAL` (`VOUCHER_DESYNC_ALERT`).
  3. Retornar `502`/`503` con `retryable: true` (a `MercadoPago` para que reintente el webhook, o al `Paciente` para reintentar generar preferencia).
**What customer (`Paciente`) sees**: Mensaje de error permitiendo reintentar sin quedar con un cupón consumido sin pago.
**What operator sees**: Log estructurado con `estudio_id`, `pago_id` y `mp_payment_id`.

---

## State Transitions

```
Pago (pagos.estado) & Cuota #1 (cuotas.estado):
  [Sin Pago activo]
    -- (STEP 1-3: Paciente inicia pago en 1 o N cuotas) --> [Pago: PENDIENTE, Cuotas 1..N: PENDIENTE]
    -- (STEP 4: Webhook MercadoPago status='approved' & N=1) --> [Pago: PAGADO, Cuota 1: PAGADA] -> (Habilita Sacar turno)
    -- (STEP 4: Webhook MercadoPago status='approved' & N>1) --> [Pago: PARCIAL, Cuota 1: PAGADA, Cuotas 2..N: PENDIENTE] -> (Habilita Sacar turno)
    -- (STEP 4: Webhook MercadoPago status='rejected') --> [Pago: RECHAZADO, Cuota 1: RECHAZADA] -> (No habilita turno)
```

---

## Handoff Contracts

### 1. Frontend Paciente -> Backend (`POST /api/v1/estudios/{estudio_id}/pagos`)
**Payload**:
```json
{
  "cantidad_cuotas": 3,
  "codigo_cupon": "53399388"
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
    "medio_pago": "mercadopago",
    "estado": "pendiente",
    "cantidad_cuotas": 3,
    "monto_presupuesto_usd": "560.00",
    "descuento_cupon_usd": "112.00",
    "monto_neto_usd": "448.00",
    "mp_preference_id": "123456789-abcdef-1234",
    "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=123456789-abcdef-1234",
    "cuotas": [
      { "cuota_id": 201, "numero_cuota": 1, "monto_usd": "149.34", "fecha_vencimiento": "2026-11-17", "estado": "pendiente" },
      { "cuota_id": 202, "numero_cuota": 2, "monto_usd": "149.33", "fecha_vencimiento": "2026-12-17", "estado": "pendiente" },
      { "cuota_id": 203, "numero_cuota": 3, "monto_usd": "149.33", "fecha_vencimiento": "2027-01-17", "estado": "pendiente" }
    ]
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

### 2. MercadoPago -> Backend (`POST /api/v1/webhooks/mercadopago`)
**Headers**: `x-signature`, `x-request-id`
**Payload**:
```json
{
  "type": "payment",
  "action": "payment.created",
  "data": { "id": "9876543210" }
}
```
**Success response** (`200 OK`): `{"ok": true}`
**Failure response** (`401` / `503`): `{"ok": false, "code": "INVALID_MERCADOPAGO_SIGNATURE"}`

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Filas en `pagos` y `cuotas` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Registro en `registro_modificaciones` | STEP 4 | `ABORT_CLEANUP` | `session.rollback()` |
| Registro en `avisos` | STEP 4 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/economia.py`, `Pago` actualmente solo tiene `tipo`, `monto_usd`, `cupon_id`, `descuento_cupon_usd`, `cobertura_obra_social_usd`, `anulado` y `fecha`; no existen aún la tabla `cuotas` ni los campos `mp_preference_id`, `mp_payment_id`, `estado`, `medio_pago`, `cantidad_cuotas`, ni el cliente `mercadopago_client.py`. | High | `DER.md`, STEP 3 & STEP 4 | Documentado como brecha SDD en `docs/DER.md` y [ADR-001](../ADRs/ADR-001-pagos-en-cuotas-mercadopago.md) para implementar antes de codificar este flujo. |
| RC-2 | El LEL define que el `Estudio` permanece en `EstadoEstudio.CREADO` hasta que el `Paciente` reserva turno (`Turno sacado`). | Medium | State Transitions | Se mantiene `Estudio.estado == CREADO` al confirmarse el pago/cuota 1, habilitando `Sacar turno` en Escenario 7. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path 1 pago vía MercadoPago** | `POST /api/v1/estudios/{id}/pagos` con `cantidad_cuotas=1` + webhook `payment` `approved`. | Se crea `Pago(PENDIENTE)` y 1 `Cuota`; al llegar el webhook pasa a `Pago.estado == PAGADO`, `Cuota.estado == PAGADA` y `habilitado_sacar_turno == True`. |
| **TC-02: Happy path plan en 3 cuotas vía MercadoPago** | `POST /api/v1/estudios/{id}/pagos` con `cantidad_cuotas=3` + webhook `approved` para Cuota 1. | Se crean 3 `Cuotas` con vencimientos mensuales; tras el webhook `Cuota #1 == PAGADA`, `Cuotas #2..3 == PENDIENTE`, `Pago.estado == PARCIAL` y el paciente puede `Sacar turno`. |
| **TC-03: Pago en cuotas aplicando cupón vigente (Escenario 30)** | `POST /api/v1/estudios/{id}/pagos` con `cantidad_cuotas=3` y `codigo_cupon` de 20% sobre 500 USD. | El descuento (`100 USD`) se aplica antes del prorrateo (`400 USD / 3`), el cupón sigue sin vencer hasta el webhook `approved`, momento en que se consume en `API de cupones`. |
| **TC-04: Pago rechazado por MercadoPago** | Webhook `payment` con `status="rejected"`. | `Cuota #1 == RECHAZADA`, `Pago.estado == RECHAZADO`, el paciente NO puede sacar turno y puede reintentar. |
| **TC-05: Idempotencia ante webhook duplicado de MercadoPago** | Llegan dos webhooks idénticos `approved` para el mismo `mp_payment_id`. | Ambos retornan `200 OK`; no se duplican `Cuotas`, `Avisos` ni consumo de `Cupón`. |
| **TC-06: Firma de webhook inválida** | `POST /api/v1/webhooks/mercadopago` con `x-signature` adulterado. | Retorna `401 Unauthorized` (`INVALID_MERCADOPAGO_SIGNATURE`) sin modificar base de datos. |
| **TC-07: Nuevo pago tras 5 ausencias reinicia `ausencias = 0` y audita** | Pago aprobado para un estudio con `ausencias == 5` y pago previo `anulado == True`. | `Pago` nuevo en `PAGADO`/`PARCIAL`, `estudio.ausencias = 0`, fila nueva en `registro_modificaciones`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El pago de la Cuota #1 confirmada por MercadoPago habilita inmediatamente al paciente para sacar turno de extracción (ver [ADR-001](../ADRs/ADR-001-pagos-en-cuotas-mercadopago.md)). | Requerimientos 1 y 3 + `ADR-001`. | Bajo; puede ajustarse en política si se exigiera cancelar N cuotas antes del turno. |

## Open Questions

- ¿El monto en USD del presupuesto se convierte a ARS al tipo de cambio oficial/configurado al momento de generar cada preferencia en MercadoPago? *(Se recomienda parametrizar `cotizacion_usd_ars` en la tabla `configuracion` o enviar moneda configurada en `MercadoPagoClient`).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial (v1.0) para pago simulado único. | Marcada como `Approved`. |
| 2026-11-17 | Actualizada a v2.0 para soporte de cuotas vía `MercadoPago`, webhooks idempotentes y registro de auditoría en `registro_modificaciones`. | Actualizada y alineada con `ADR-001` y `DER.md`. |
