# WORKFLOW: Escenario 39 – Consultar las cuotas de los pacientes
**Versión**: 1.0
**Fecha**: 2026-11-17
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-39`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Administrativo`, `Paciente` |
| **Objetos** | `Cuota`, `Presupuesto`, `Estudio`, `API de MercadoPago` |
| **Verbos** | `Consultar cuotas` |
| **Estados** | *(Solo lectura; no altera `EstadoEstudio` ni `EstadoCuota`)* |

---

## Overview

- **Objetivo**: Permitir al `Administrativo` visualizar y filtrar las `Cuotas` de todos los `Pacientes` (estado de pago, montos, fechas de vencimiento, referencias de `MercadoPago` y totales consolidados de deuda/recaudación).
- **Contexto**: Con la incorporación del pago por cuotas con `MercadoPago` (Escenarios 6 y 38), el `Administrativo` del laboratorio central necesita monitorear las cuotas pagadas, pendientes, vencidas, rechazadas o anuladas de cada `Paciente` y `Estudio` para el seguimiento administrativo y de caja.
- **Recursos**: Tablas `cuotas`, `pagos`, `presupuestos`, `estudios`, `pacientes`, `usuarios`.
- **Episodios**:
  1. El `Administrativo` accede a la vista administrativa de cuotas de pacientes (`GET /api/v1/administracion/cuotas` o por paciente `GET /api/v1/pacientes/{paciente_id}/cuotas`).
  2. Aplica filtros opcionales por `paciente_id`, `dni`, `estudio_id`, `estado` (`pendiente`, `pagada`, `vencida`, `rechazada`, `anulada`) o rango de `fecha_vencimiento`.
  3. El sistema retorna el listado paginado de `Cuotas` con datos del `Paciente`, `Estudio`, número de cuota sobre el total, monto, vencimiento, estado e IDs de `MercadoPago`, junto con un resumen agregado (`total_pagado_usd`, `total_pendiente_usd`, `total_vencido_usd`).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Administrativo` | Sujeto LEL autorizado que consulta y filtra las cuotas de los pacientes. |
| `router` (`administracion_cuotas_router`) | Expone `GET /api/v1/administracion/cuotas` y `GET /api/v1/pacientes/{paciente_id}/cuotas`. |
| `service` (`economia_service`) | Valida `Rol.ADMINISTRATIVO`, aplica filtros y calcula agregados financieros. |
| `repo` (`economia_repo`) | Ejecuta consultas optimizadas con `JOIN` e índice `idx_cuotas_estado_vencimiento` sobre `PostgreSQL`. |

---

## Prerequisites

- El usuario autenticado tiene sesión activa con `Usuario.rol == Rol.ADMINISTRATIVO`.
- Existen planes de pago en cuotas registrados en `pagos` y `cuotas`.

---

## Trigger

El `Administrativo` ingresa al panel `"Cuotas de Pacientes"` o filtra cuotas en el listado administrativo:
- **Endpoint HTTP**: `GET /api/v1/administracion/cuotas` (y `GET /api/v1/pacientes/{paciente_id}/cuotas`).

---

## Workflow Tree

### STEP 1: Autenticación de rol `Administrativo` y validación de filtros
**Actor**: `router` -> `service` (`economia_service.listar_cuotas_administracion`)
**Action**:
1. Verifica que `usuario_actual.rol == Rol.ADMINISTRATIVO` (otros roles como `Paciente` ajeno, `Transportista` o `Bioinformático` reciben `403 Forbidden`; el `Paciente` solo consulta sus propias cuotas vía Escenario 38).
2. Valida parámetros de consulta: `estado` (dentro de `EstadoCuota`), `paciente_id`, `dni`, `estudio_id`, `fecha_desde`, `fecha_hasta`, `pagina` (`>= 1`), `limite` (`1..100`).
**Timeout**: `2s`
**Input**: Query params de filtrado + `usuario_actual`.
**Output on SUCCESS**: DTO de filtros validado -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Rol distinto de `Rol.ADMINISTRATIVO` -> `return 403 Forbidden` (`FORBIDDEN_ROLE`).
  - `FAILURE(validation_error)`: Parámetros de fecha o `estado` inválidos -> `return 400 Bad Request` (`FILTROS_INVALIDOS`).

**Observable states during this step**:
  - **Operator (`Administrativo`) sees**: Indicador `"Cargando cuotas de pacientes..."`.
  - **Database**: Sin lecturas aún.
  - **Logs**: `[economia_service] STEP 1 consulta_cuotas_admin usuario_id=<uid> filtros=<f>`

---

### STEP 2: Consulta paginada en `PostgreSQL` y cálculo de resumen financiero
**Actor**: `service` -> `repo` (`economia_repo`) -> `PostgreSQL`
**Action**:
1. Consulta `cuotas` haciendo `JOIN` con `pagos`, `presupuestos`, `estudios`, `pacientes` y `usuarios`, aplicando los filtros solicitados y ordenando por `Cuota.fecha_vencimiento ASC, Cuota.id ASC`.
2. Calcula los totales agregados sobre el conjunto filtrado: `total_pagado_usd`, `total_pendiente_usd`, `total_vencido_usd`, `cantidad_cuotas_vencidas`.
3. Serializa cada cuota con: `cuota_id`, `pago_id`, `estudio_id`, `paciente` (`id`, `dni`, `nombre`, `apellido`), `numero_cuota`, `cantidad_cuotas`, `monto_usd`, `fecha_vencimiento`, `estado`, `pagada_en`, `mp_preference_id`, `mp_payment_id`, `mp_status_detail`, `pago_anulado`.
**Timeout**: `4s`
**Input**: `FiltrosCuotasDTO`
**Output on SUCCESS**: `{ cuotas: [...], paginacion: {...}, resumen: {...} }` -> `return 200 OK` -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(not_found)`: Si se consultó `/pacientes/{paciente_id}/cuotas` y `paciente_id` no existe -> `return 404 Not Found` (`PACIENTE_NO_ENCONTRADO`).
  - `FAILURE(timeout)` / `FAILURE(db_error)`: Error en `PostgreSQL` -> reintenta 1 vez (`500ms`); si persiste -> `return 503 Service Unavailable`.

**Observable states during this step**:
  - **Operator (`Administrativo`) sees**: Tabla con todas las cuotas de los pacientes, etiquetas visuales por estado (`pagada`, `pendiente`, `vencida`, `rechazada`, `anulada`), tarjetas resumen de deuda vencida/pendiente y referencia de `MercadoPago`.
  - **Database**: Lecturas indexadas sobre `cuotas` (`idx_cuotas_estado_vencimiento`).
  - **Logs**: `[economia_repo] STEP 2 consulta_cuotas_ok total=<n> vencidas=<v>`

---

### ABORT_CLEANUP: Manejo de fallo de lectura
**Triggered by**: Timeout o error de conexión en `STEP 2`.
**Actions**:
  1. Registrar el error en logs y retornar `503 Service Unavailable` (`retryable: true`) sin efectos laterales (operación de solo lectura).

---

## State Transitions

*(Operación de solo lectura; no modifica estados).*

---

## Handoff Contracts

### `Administrativo (UI)` -> `Backend (GET /api/v1/administracion/cuotas)`
**Query params**: `?estado=vencida&paciente_id=42&pagina=1&limite=20`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "items": [
      {
        "cuota_id": 202,
        "pago_id": 104,
        "estudio_id": 101,
        "paciente": {
          "id": 42,
          "dni": "40123456",
          "nombre": "Juan",
          "apellido": "Pérez"
        },
        "numero_cuota": 2,
        "cantidad_cuotas": 3,
        "monto_usd": "149.33",
        "fecha_vencimiento": "2026-12-17",
        "estado": "vencida",
        "pagada_en": null,
        "mp_preference_id": "123456789-pref-2",
        "mp_payment_id": null,
        "pago_anulado": false
      }
    ],
    "resumen": {
      "total_pagado_usd": "149.34",
      "total_pendiente_usd": "149.33",
      "total_vencido_usd": "149.33",
      "cantidad_cuotas_vencidas": 1
    },
    "paginacion": {
      "pagina": 1,
      "limite": 20,
      "total": 1
    }
  }
}
```
**Failure response** (`403` / `400` / `503`): `{"ok": false, "error": "...", "code": "FORBIDDEN_ROLE", "retryable": false}`

---

## Cleanup Inventory

*(Sin recursos creados ni modificados: endpoint de solo lectura).*

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | No existen aún el modelo `Cuota` ni los endpoints de administración de cuotas en `app/src/`. | High | `DER.md`, STEP 2 | Especificado en `docs/DER.md` y `ADR-001` para implementación SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path listado de todas las cuotas por Administrativo** | `GET /api/v1/administracion/cuotas` autenticado como `Rol.ADMINISTRATIVO`. | Retorna `200 OK` con cuotas de todos los pacientes y su `resumen` financiero. |
| **TC-02: Filtrado por estado `vencida` y por `paciente_id`** | `GET /api/v1/administracion/cuotas?estado=vencida&paciente_id=42`. | Retorna únicamente las cuotas vencidas del paciente 42 y calcula totales filtrados. |
| **TC-03: Rechazo para roles no administrativos** | `GET /api/v1/administracion/cuotas` invocado por un `Paciente`, `Médico` o `Transportista`. | Retorna `403 Forbidden` (`FORBIDDEN_ROLE`). |
| **TC-04: Consulta por paciente inexistente** | `GET /api/v1/pacientes/99999/cuotas` por un `Administrativo`. | Retorna `404 Not Found` (`PACIENTE_NO_ENCONTRADO`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El `Administrativo` visualiza las cuotas de todos los pacientes sin exponer datos clínicos sensibles (síntomas, historia clínica o variantes genéticas), limitándose a datos identificatorios y financieros. | Principio de mínimo privilegio (`agency-privacy-engineer` / `.ai/1-Entrevista.md` línea 315) y Req. 3. | Bajo. |

## Open Questions

- Ninguna bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-11-17 | Especificación creada para visibilidad administrativa de cuotas de pacientes (Req. 3). | Marcada como `Approved`. |
