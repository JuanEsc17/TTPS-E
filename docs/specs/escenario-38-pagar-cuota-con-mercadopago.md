# WORKFLOW: Escenario 38 – Pagar una cuota de un estudio con MercadoPago
**Versión**: 1.0
**Fecha**: 2026-11-17
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-38`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Paciente`, `Administrativo` *(monitorea las cuotas en Escenario 39)* |
| **Objetos** | `Cuota`, `Presupuesto`, `Estudio`, `API de MercadoPago`, `Aviso` |
| **Verbos** | `Pagar cuota`, `Pagar presupuesto` |
| **Estados** | *(No modifica `EstadoEstudio` ya habilitado por cuota 1; actualiza `Cuota.estado` y `Pago.estado`)* |

---

## Overview

- **Objetivo**: Permitir al `Paciente` abonar las `Cuotas` subsiguientes (`numero_cuota >= 2`) de un `Estudio` financiado mediante `MercadoPago`, y detectar automáticamente las cuotas que superan su `fecha_vencimiento` marcándolas como `vencida`.
- **Contexto**: En el Escenario 6 el `Paciente` optó por pagar un `Presupuesto` en `N > 1` cuotas con `MercadoPago` y ya abonó la cuota #1 (`Pago.estado == EstadoPago.PARCIAL`, `Pago.anulado == False`). Quedan cuotas mensuales pendientes en la tabla `cuotas`. Este workflow cubre: (A) la generación del checkout de `MercadoPago` y acreditación por webhook para una `Cuota` pendiente o vencida, y (B) el job diario de vencimiento de cuotas.
- **Recursos**: `Cuota` (`cuotas`), `Pago` (`pagos`), `Estudio` (`estudios`), `API de MercadoPago` (`mercadopago_client`), `Aviso` (`avisos`).
- **Episodios**:
  1. El `Paciente` consulta el detalle de sus `Cuotas` pendientes o vencidas asociadas al `Estudio`.
  2. El `Paciente` selecciona una `Cuota` y solicita generar su preferencia de pago en `MercadoPago`.
  3. El sistema invoca la `API de MercadoPago` (`POST /checkout/preferences`), guarda `mp_preference_id` en la `Cuota` y retorna el `init_point`.
  4. Al confirmarse el webhook `payment` con `status == "approved"`, el sistema marca la `Cuota` como `pagada` y, si todas las cuotas del `Pago` quedaron pagadas, actualiza `Pago.estado = EstadoPago.PAGADO`.
  5. Un proceso diario verifica `cuotas` con `estado == PENDIENTE` y `fecha_vencimiento < hoy`, pasándolas a `EstadoCuota.VENCIDA` y emitiendo un `Aviso` al `Paciente`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` | Consulta sus cuotas y abona cada cuota pendiente o vencida a través de `MercadoPago`. |
| `API de MercadoPago` | Emite la preferencia de pago de la cuota individual y notifica vía webhook el resultado. |
| `Sistema (Job diario de vencimientos)` | Marca como `vencida` toda cuota impaga cuyo vencimiento ya expiró. |
| `router` (`cuotas_router`, `webhooks_router`) | Expone `GET /api/v1/estudios/{estudio_id}/cuotas`, `POST /api/v1/cuotas/{cuota_id}/pagar` y recibe `POST /api/v1/webhooks/mercadopago`. |
| `service` (`economia_service`) | Valida titularidad, bloquea la cuota (`FOR UPDATE`), crea la preferencia MP, procesa el webhook de forma idempotente y actualiza `Pago.estado`. |
| `repo` (`economia_repo`, `usuario_repo`) | Opera sobre `cuotas`, `pagos` y `avisos` en `PostgreSQL`. |

---

## Prerequisites

- Para pago de cuota: usuario autenticado con `Rol.PACIENTE`, titular del `Estudio` asociado a `cuota.pago.presupuesto.estudio`.
- El `Pago` padre tiene `anulado == False` y `estado == EstadoPago.PARCIAL`.
- La `Cuota` objetivo tiene `estado in (EstadoCuota.PENDIENTE, EstadoCuota.VENCIDA, EstadoCuota.RECHAZADA)`.

---

## Trigger

1. **Inicio de pago de cuota**: `POST /api/v1/cuotas/{cuota_id}/pagar` (autenticado como `Paciente` titular).
2. **Webhook de MercadoPago**: `POST /api/v1/webhooks/mercadopago` (con `external_reference = "pago:{pago_id}:cuota:{cuota_id}"`).
3. **Job diario de vencimiento**: Cron diario a las `00:30` ART.

---

## Workflow Tree

### STEP 1: Validación de titularidad y estado pagable de la `Cuota`
**Actor**: `router` -> `service` (`economia_service`) -> `repo` (`economia_repo`)
**Action**:
1. Verifica `Rol.PACIENTE` y que `cuota.pago.presupuesto.estudio.paciente.usuario_id == usuario_actual.id`.
2. Bloquea `Cuota` y `Pago` (`SELECT ... FOR UPDATE`).
3. Verifica que `pago.anulado == False` y `pago.estado == EstadoPago.PARCIAL`.
4. Verifica que `cuota.estado in (EstadoCuota.PENDIENTE, EstadoCuota.VENCIDA, EstadoCuota.RECHAZADA)`.
**Timeout**: `2s`
**Input**: `cuota_id`, `usuario_actual`.
**Output on SUCCESS**: `Cuota` y `Pago` bloqueados -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: La cuota pertenece a otro paciente -> `return 403 Forbidden` (`FORBIDDEN_NOT_OWNER`).
  - `FAILURE(not_found)`: `cuota_id` inexistente -> `return 404 Not Found` (`CUOTA_NO_ENCONTRADA`).
  - `FAILURE(conflict)`: La cuota ya está `PAGADA` o `ANULADA` -> `return 409 Conflict` (`CUOTA_NO_PAGABLE`).

**Observable states during this step**:
  - **Customer (`Paciente`) sees**: Spinner `"Generando enlace de pago en MercadoPago..."`.
  - **Operator (`Administrativo`) sees**: Sin cambios aún en la tabla `cuotas`.
  - **Database**: Lectura `FOR UPDATE` sobre `cuotas` y `pagos`.
  - **Logs**: `[economia_service] STEP 1 cuota_pago_iniciado cuota_id=<cid> pago_id=<pid>`

---

### STEP 2: Creación de preferencia en `API de MercadoPago`
**Actor**: `service` -> `clients` (`mercadopago_client`) -> `repo` (`economia_repo`)
**Action**:
1. Invoca `MercadoPagoClient.crear_preferencia` con `unit_price = cuota.monto_usd`, descripción `"Estudio #<id> - Cuota <numero_cuota>/<cantidad_cuotas>"`, `external_reference = f"pago:{pago.id}:cuota:{cuota.id}"` y `notification_url`.
2. Actualiza `cuota.mp_preference_id = pref.id` (si estaba en `RECHAZADA`, vuelve a `PENDIENTE`) y ejecuta `session.commit()`.
**Timeout**: `8s` (2 reintentos con backoff `1s`, `2s`).
**Input**: `Cuota`, `Pago`, `Estudio`.
**Output on SUCCESS**: `{ cuota_id, mp_preference_id, init_point }` -> Retorna `200 OK` -> Aguarda webhook en `STEP 3`.
**Output on FAILURE**:
  - `FAILURE(external_api_error)` / `FAILURE(timeout)`: Fallo en `MercadoPago` -> `ABORT_CLEANUP` (`session.rollback()`) -> `return 502 Bad Gateway` (`MERCADOPAGO_UNAVAILABLE`, `retryable: true`).

**Observable states during this step**:
  - **Customer (`Paciente`) sees**: Redirección al checkout de `MercadoPago`.
  - **Operator (`Administrativo`) sees**: `mp_preference_id` registrado en la cuota.
  - **Database**: `cuotas.mp_preference_id` actualizado.
  - **Logs**: `[mercadopago_client] STEP 2 preferencia_cuota_creada cuota_id=<cid> pref=<pref>`

---

### STEP 3: Confirmación de webhook de `MercadoPago` y actualización de `Cuota` y `Pago`
**Actor**: `API de MercadoPago` -> `webhooks_router` -> `economia_service` -> `mercadopago_client` -> `PostgreSQL`
**Action**:
1. Valida firma HMAC `x-signature` y consulta `GET /v1/payments/{mp_payment_id}` en `MercadoPago`.
2. Bloquea `Cuota` y `Pago` (`SELECT ... FOR UPDATE`). Si `cuota.estado == EstadoCuota.PAGADA` con el mismo `mp_payment_id`, retorna `200 OK` idempotente.
3. Si `status == "approved"`:
   - Marca `cuota.estado = EstadoCuota.PAGADA`, `cuota.mp_payment_id = payment.id`, `cuota.mp_status_detail = payment.status_detail`, `cuota.pagada_en = now()`.
   - Verifica si existen otras cuotas del mismo `pago_id` con `estado != EstadoCuota.PAGADA`. Si todas están pagadas, actualiza `pago.estado = EstadoPago.PAGADO`; de lo contrario mantiene `EstadoPago.PARCIAL`.
   - Crea `Aviso` (`APP` y `MAIL`) confirmando el pago de la cuota #`numero_cuota`.
4. Si `status in ("rejected", "cancelled")`: marca `cuota.estado = EstadoCuota.RECHAZADA` y notifica al `Paciente`.
5. Ejecuta `session.commit()`.
**Timeout**: `8s`
**Input**: Webhook `payment` + firma `x-signature`.
**Output on SUCCESS**: `200 OK` -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Firma inválida -> `return 401 Unauthorized`.
  - `FAILURE(transient_external_error)`: Fallo consultando `MercadoPago` -> `return 503 Service Unavailable` para reintento del webhook.

**Observable states during this step**:
  - **Customer (`Paciente`) sees**: Cuota marcada como `"Pagada"` y saldo pendiente reducido.
  - **Operator (`Administrativo`) sees**: Cuota actualizada a `pagada` en el panel administrativo (Escenario 39) con `mp_payment_id` y `pagada_en`.
  - **Database**: `cuotas.estado = 'pagada'`, `pagos.estado` actualizado, `avisos` creado.
  - **Logs**: `[economia_service] STEP 3 cuota_confirmada cuota_id=<cid> pago_id=<pid> estado_pago=<estado>`

---

### STEP 4 (Job Programado): Detección de cuotas vencidas
**Actor**: Scheduler diario (`00:30` ART) -> `economia_service.marcar_cuotas_vencidas` -> `repo`
**Action**:
1. Selecciona todas las `Cuota`s con `estado == EstadoCuota.PENDIENTE`, `fecha_vencimiento < date.today()` y `pago.anulado == False`.
2. Actualiza `cuota.estado = EstadoCuota.VENCIDA`.
3. Inserta `Aviso` (`CanalAviso.APP` y `CanalAviso.MAIL`) para el `Paciente` recordando el pago pendiente vía `MercadoPago`, y confirma `session.commit()`.
**Timeout**: `15s`

---

### ABORT_CLEANUP: Reversión transaccional
**Triggered by**: Fallo en `STEP 2`, `STEP 3` o `STEP 4`.
**Actions**:
  1. Ejecutar `session.rollback()` preservando el estado previo de `cuotas` y `pagos`.
  2. Registrar error en logs y retornar `502`/`503` con `retryable: true`.

---

## State Transitions

```
Cuota (cuotas.estado):
  [PENDIENTE] -- (fecha_vencimiento < hoy sin pago) ----------> [VENCIDA]
  [PENDIENTE | VENCIDA | RECHAZADA] -- (Webhook MP approved) -> [PAGADA]
  [PENDIENTE | VENCIDA | RECHAZADA] -- (Webhook MP rejected) -> [RECHAZADA]
  [PENDIENTE | VENCIDA | RECHAZADA] -- (5ta ausencia Esc. 33) -> [ANULADA]

Pago (pagos.estado):
  [PARCIAL] -- (última cuota pasa a PAGADA) -----------------> [PAGADO]
```

---

## Handoff Contracts

### `Paciente (UI)` -> `Backend (POST /api/v1/cuotas/{cuota_id}/pagar)`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "cuota_id": 202,
    "pago_id": 104,
    "numero_cuota": 2,
    "monto_usd": "149.33",
    "mp_preference_id": "987654-pref-cuota2",
    "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=987654-pref-cuota2"
  }
}
```
**Failure response** (`403` / `404` / `409` / `502`): `{"ok": false, "error": "...", "code": "CUOTA_NO_PAGABLE", "retryable": false}`

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Actualización `cuotas.mp_preference_id` | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Actualización `cuotas.estado`, `pagos.estado`, `avisos` | STEP 3 / STEP 4 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | La tabla `cuotas` y el cliente `mercadopago_client` aún no existen en `app/src/`. | High | Todos los pasos | Especificado en `docs/DER.md` y [ADR-001](../ADRs/ADR-001-pagos-en-cuotas-mercadopago.md) para implementación SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path pago de cuota #2 y actualización parcial** | `POST /api/v1/cuotas/202/pagar` + webhook `approved` en plan de 3 cuotas. | `Cuota #2 == PAGADA`; `Pago.estado` sigue `PARCIAL` (falta cuota #3). |
| **TC-02: Pago de última cuota completa el plan** | Webhook `approved` para `Cuota #3` de 3 cuando #1 y #2 ya están `PAGADA`. | `Cuota #3 == PAGADA` y `Pago.estado` pasa a `PAGADO`. |
| **TC-03: Rechazo al intentar pagar cuota ya pagada o anulada** | `POST /api/v1/cuotas/201/pagar` sobre cuota en estado `PAGADA` o `ANULADA`. | Retorna `409 Conflict` (`CUOTA_NO_PAGABLE`). |
| **TC-04: Job de vencimiento marca cuotas impagas vencidas** | Cuota `PENDIENTE` con `fecha_vencimiento` de ayer procesada por `marcar_cuotas_vencidas`. | Pasa a `EstadoCuota.VENCIDA` y genera `Aviso` al `Paciente`. |
| **TC-05: Pago de cuota vencida vía MercadoPago** | `POST /api/v1/cuotas/202/pagar` cuando está `VENCIDA` + webhook `approved`. | Transiciona `VENCIDA -> PAGADA` normalmente. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El pago de una cuota vencida no aplica intereses moratorios automáticos salvo que se defina una tasa en `configuracion`. | Requerimientos 1 y 3 (sin recargo explícito). | Bajo. |

## Open Questions

- Ninguna bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-11-17 | Especificación creada para soporte de pago de cuotas con `MercadoPago` (Req. 1). | Marcada como `Approved`. |
