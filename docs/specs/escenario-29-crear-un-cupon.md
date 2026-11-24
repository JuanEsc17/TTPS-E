# WORKFLOW: Escenario 29 – Crear un cupón
**Versión**: 1.1
**Fecha**: 2026-11-24
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-29`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Gerente médico** | `Usuario` (`rol = Rol.GERENTE_MEDICO`) + perfil `Medico` (`medicos.id`) |
| **Objetos** | **Cupón** | Modelo `Cupon` (tabla `cupones`: `id`, `codigo`, `qr_url` (siempre `NULL` en esta versión), `descuento_porcentaje`, `gerente_id`, `medico_id`, `paciente_id`, `usado`, `usado_en`, `vigente_hasta`) |
| **Objetos** | **API de cupones** | Cliente HTTP externo (`app/src/clients/cupones_client.py`) hacia el módulo externo que genera cupones con **código numérico** y valida su vigencia |
| **Verbos** | **Pagar presupuesto** | Flujo posterior que consume el **cupón** creado (ver Escenario 30) |
| **Estados** | *(No altera `EstadoEstudio`)* | La creación de un **cupón** es independiente de un **estudio** específico |

---

## Overview

- **Objetivo:** Generar un **cupón** de descuento limitado para ser usado posteriormente en el pago del **presupuesto** de un **estudio**.
- **Contexto:** El **gerente médico** quiere ofrecer un descuento porcentual a **pacientes** (asignándolo opcionalmente a un **médico** tratante para que este lo entregue a un **paciente**).
- **Recursos:** **Cupón**, descuento (`descuento_porcentaje`), **API de cupones**, código numérico (`codigo`).
- **Episodios:**
  1. El **gerente médico** solicita crear uno o más **cupones**.
  2. El **gerente médico** define el descuento y la cantidad de **cupones**.
  3. El sistema pide los **cupones** a la **API de cupones**.
  4. El sistema registra cada **cupón** con su código numérico en la base de datos.

**Resumen del flujo:** El **gerente médico** autenticado envía `POST /api/v1/cupones` con `descuento_porcentaje` (de `0.01` a `100.00`, máximo 2 decimales) y `cantidad` opcional (de `1` a `20`, por defecto `1`). El `router` delega en `cupon_service`, que valida las reglas de dominio y la existencia del perfil `Medico` del gerente. Luego invoca `cupones_client.generar_cupones_gerencia`, que devuelve un `codigo_cupon` por cada cupón. Finalmente `cupon_repo` persiste las filas en `cupones` con `vigente_hasta = now() + 30 días`. **Decisión (Entrevista, líneas 365-367):** se usa código numérico en lugar de QR ("si no, lo pueden hacer con un código numérico y listo"), porque la **API de cupones** no genera QR. Si la persistencia local falla después de la emisión externa, se ejecuta `ABORT_CLEANUP`, que registra una alerta `ORPHAN_VOUCHER_ALERT`: la API no expone una operación de anulación.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Gerente médico** (Sujeto LEL) | Inicia la solicitud de creación de **cupón** y define el porcentaje de descuento desde la interfaz web. |
| **Router HTTP** (`app/src/web/api/cupones.py`) | Verifica sesión activa y rol `Rol.GERENTE_MEDICO`, extrae el JSON y devuelve la respuesta HTTP estandarizada. |
| **Servicio de Cupones** (`app/src/core/services/cupon_service.py`) | Valida `descuento_porcentaje` y `cantidad`, resuelve el perfil `Medico` del gerente, llama al cliente externo y coordina la transacción. |
| **Cliente API de Cupones** (`app/src/clients/cupones_client.py`) | Llama vía `httpx` a `POST /generar_cupones_gerencia` con header `X-API-Key`. |
| **Repositorio de Cupones** (`app/src/core/repos/cupon_repo.py`) | Consultas e inserciones SQLAlchemy sobre `medicos` y `cupones`. 
|**API de cupones** para solicitar la generación del código numérico y QR, y para revocar el cupón en caso de rollback local. |
| **PostgreSQL** (`db`) | Persiste la fila en `cupones` garantizando las restricciones `UNIQUE(codigo)` y `CHECK(descuento_porcentaje BETWEEN 0 AND 100)`. |

---

## Prerequisites

- **Sesión y Rol:** El usuario autenticado debe poseer una sesión activa válida, tener `Usuario.rol == Rol.GERENTE_MEDICO` y `Usuario.debe_cambiar_password == False`.
- **Datos existentes en `app/src/core/models/`:**
  - Debe existir una fila en `usuarios` correspondiente al **gerente médico** y su fila vinculada en `medicos` (`medicos.usuario_id == usuarios.id`), cuyo `medicos.id` se utilizará como `cupones.gerente_id`.borro re
- **Estado previo del `Estudio`:** No aplica (`N/A`); el **cupón** se crea antes de ser aplicado al pago del **presupuesto** de un **estudio**.
- **Servicios externos:** La **API de cupones** debe estar accesible mediante `CUPONES_API_URL` y la clave del grupo `CUPONES_API_KEY`.
---

## Trigger

- **Acción de usuario:** El **gerente médico** completa el formulario "Nuevo Cupón de Descuento" con el porcentaje de descuento y la cantidad, y presiona "Crear cupones".
- **Endpoint HTTP:** `POST /api/v1/cupones`

---

## Workflow Tree

### STEP 1: Autenticación, autorización de rol y validación de entrada
**Actor**: Router HTTP (`cupones.py`) -> Servicio de Cupones (`cupon_service.py`) -> Repositorio (`cupon_repo.py`)
**Action**: Verifica que la sesión pertenezca a un usuario con `Rol.GERENTE_MEDICO`, valida `0 < descuento_porcentaje <= 100` (máximo 2 decimales) y `1 <= cantidad <= 20`, y recupera el perfil `Medico` del gerente (`gerente_id`).
**Timeout**: `2s`
**Input**:
```json
{ "usuario_autenticado_id": "int", "descuento_porcentaje": "Decimal (0.01 .. 100.00)", "cantidad": "int (1..20, default 1)" }
```
**Output on SUCCESS**: `{ gerente_id: int, descuento_porcentaje: Decimal, cantidad: int }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Sin sesión o token inválido -> `401` (`NO_AUTENTICADO`).
  - `FAILURE(forbidden)`: Rol distinto de `GERENTE_MEDICO` -> `403` (`ROL_NO_AUTORIZADO`).
  - `FAILURE(validation_error)`: Descuento ausente, no numérico, `<= 0`, `> 100` o con más de 2 decimales -> `422` (`DESCUENTO_INVALIDO`). Cantidad no entera o fuera de `1..20` -> `422` (`CANTIDAD_INVALIDA`).
  - `FAILURE(invalid_state)`: El gerente no tiene fila en `medicos` -> `409` (`PERFIL_GERENTE_INCOMPLETO`) y log `ERROR`.

**Observable states during this step**:
  - Customer/Actor (**Gerente médico**) sees: Indicador de carga ("Generando cupón...") en el botón de creación.
  - Operator sees: Petición entrante en el log de acceso HTTP `POST /api/cupones`.
  - Database: Lectura (`SELECT`) sobre `usuarios` y `medicos`; ninguna fila insertada ni modificada en `cupones`.
  - Logs: `[cupon_service] step=1_validacion usuario_id=<id> descuento=<pct> medico_id=<mid>`

---

### STEP 2: Solicitud de emisión de cupón y QR a la API de cupones
**Actor**: Servicio de Cupones (`cupon_service.py`) -> Cliente API de Cupones (`cupones_client.py`) -> **API de cupones**
**Action**: Envía una solicitud `POST /external/vouchers` a la **API de cupones** indicando el porcentaje de descuento y metadatos de auditoría (`gerente_id`) para que el módulo externo genere un código único (`codigo`), el documento/imagen QR (`qr_url`) y la fecha de expiración (`vigente_hasta`).
**Timeout**: `5s` por intento (hasta 3 intentos en fallos transitorios con backoff exponencial de `0.5s`, `1.0s`).
**Input**:
```json
{
  "descuento_porcentaje": "25.00",
  "emitido_por_gerente_id": 4
}
```
**Output on SUCCESS**: `{ codigo: str, qr_url: str | null, vigente_hasta: datetime | null }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(timeout)`: La **API de cupones** no responde dentro de `5s` -> reintentar hasta 2 veces (`0.5s`, `1.0s` de espera). Si agota los reintentos -> retornar `504 Gateway Timeout` (`CUPONES_API_TIMEOUT`, `retryable=True`), sin registros locales creados.
  - `FAILURE(transient_external_error)`: La **API de cupones** responde `502`/`503`/`429` o error de conexión `httpx.RequestError` -> reintentar hasta 2 veces con backoff exponencial. Si persiste -> retornar `502 Bad Gateway` (`CUPONES_API_UNAVAILABLE`, `retryable=True`).
  - `FAILURE(permanent_external_error)`: La **API de cupones** rechaza la petición con `400`/`422` -> no reintentar; retornar `502 Bad Gateway` (`CUPONES_API_REJECTED`, `retryable=False`).

**Observable states during this step**:
  - Customer/Actor (**Gerente médico**) sees: Spinner activo "Comunicando con el servicio de cupones...".
  - Operator sees: Llamada saliente hacia `CUPONES_API_BASE_URL/external/vouchers` en métricas de clientes externos.
  - Database: Sin cambios en PostgreSQL (no se mantiene transacción abierta con lock durante la llamada HTTP externa).
  - Logs: `[cupones_client] step=2_emision_externa gerente_id=<id> attempt=<n> status=<http_status>`

---

### STEP 3: Persistencia del cupón en PostgreSQL
**Actor**: Servicio de Cupones (`cupon_service.py`) -> Repositorio de Cupones (`cupon_repo.py`) -> PostgreSQL
**Action**: Inserta una fila en `cupones` por cada código con `qr_url = NULL`, `medico_id = NULL`, `paciente_id = NULL`, `usado = False` y `vigente_hasta = now() + 30 días`, y hace `COMMIT`.
**Timeout**: `3s`
**Input**:
```json
{ "codigos": ["53399388", "2ded2dc3"], "descuento_porcentaje": "25.00", "gerente_id": 4, "vigente_hasta": "2026-12-24T10:00:00" }
```
**Output on SUCCESS**: `{ cupones: list[Cupon] }` -> `201 Created`
**Output on FAILURE**:
  - `FAILURE(conflict)`: `IntegrityError` por `UNIQUE(codigo)` -> `ROLLBACK` -> `ABORT_CLEANUP` -> `409` (`CODIGO_CUPON_DUPLICADO`).
  - `FAILURE(database_error)`: cualquier otro `SQLAlchemyError` -> `ROLLBACK` -> `ABORT_CLEANUP` -> `500` (`DB_ERROR`, `retryable=True`).

**Observable states during this step**:
  - Customer/Actor (**Gerente médico**) sees: Confirmación visual con el código numérico (`codigo`), enlace/vista previa del QR (`qr_url`), porcentaje de descuento (`descuento_porcentaje`) y vigencia (`vigente_hasta`).
  - Operator sees: Nuevo registro en `cupones` con `usado = False`.
  - Database:
    - Tabla `cupones`: nueva fila insertada con `id`, `codigo`, `qr_url`, `descuento_porcentaje`, `gerente_id`, `medico_id`, `paciente_id = NULL`, `usado = False`, `usado_en = NULL`, `vigente_hasta`, `created_at = now()`, `updated_at = now()`.
  - Logs: `[cupon_repo] step=3_persistencia_ok cupon_id=<id> codigo=<codigo> gerente_id=<gerente_id>`

---

### ABORT_CLEANUP: Reversión de cupón emitido ante fallo de persistencia local
**Triggered by**: Fallo en `STEP 3` después de que `STEP 2` emitió exitosamente el **cupón** en la **API de cupones**.
**Actions** (in order):
  1. `session.rollback()`.
  2. Log `CRITICAL` con la etiqueta `ORPHAN_VOUCHER_ALERT`, el `gerente_id`, los `codigos` emitidos y la causa, para conciliación manual. La **API de cupones** no ofrece un endpoint de anulación.
**What customer/actor (**Gerente médico**) sees**: Mensaje de error claro indicando que no se pudo registrar el cupón y que puede reintentar la operación.
**What operator sees**: Log `ERROR` o alerta `ORPHAN_VOUCHER_ALERT` con el `codigo` externo y la causa raíz del fallo de base de datos.

---

## State Transitions

```
Cupon (Escenario 29):
  [Inexistente]
    -- (STEP 1 + 2 + 3 exitosos) --> [Disponible (usado=False, medico_id=NULL, paciente_id=NULL, qr_url=NULL)]
    -- (STEP 2 ok + STEP 3 falla) --> [Inexistente localmente / "disponible" en la API + ORPHAN_VOUCHER_ALERT]

Estudio (EstadoEstudio):
  Sin transición en este escenario (no requiere ni modifica filas de `estudios`).
```

---

## Handoff Contracts

### 1. Frontend (Gerente médico) -> Backend
**Endpoint**: `POST /api/v1/cupones`
**Payload**:
```json
{ "descuento_porcentaje": 25.00, "cantidad": 2 }
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": [
    { "id": 105, "codigo": "53399388", "qr_url": null, "descuento_porcentaje": 25.0, "gerente_id": 4,
      "medico_id": null, "paciente_id": null, "usado": false, "usado_en": null,
      "vigente_hasta": "2026-12-24T10:00:00" }
  ]
}
```
**Failure response**: `{ "ok": false, "error": "...", "code": "DESCUENTO_INVALIDO", "retryable": false }`

### 2. Backend (`cupones_client`) -> API de cupones
**Endpoint**: `POST /generar_cupones_gerencia` (header `X-API-Key`)
**Payload**: `{ "p_gerente_id": "4", "p_cantidad": 2, "p_porcentaje_descuento": 25.0 }`
**Success response** (`200 OK`): `[{ "codigo_cupon": "53399388", "porcentaje": 25 }]`
**ON FAILURE**: No reintentar. Abortar antes de tocar PostgreSQL.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Cupones emitidos en **API de cupones** | Step 2 | `ABORT_CLEANUP` | Sin anulación disponible: log `CRITICAL ORPHAN_VOUCHER_ALERT` para conciliación manual |
| Fila en tabla `cupones` (en memoria de sesión SQLAlchemy) | Step 3 | `ABORT_CLEANUP` | `db.session.rollback()` |


---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | El modelo `Cupon` ya existe en `app/src/core/models/economia.py` con las columnas exactas `id`, `codigo`, `qr_url`, `descuento_porcentaje`, `gerente_id`, `medico_id`, `paciente_id`, `usado`, `usado_en`, `vigente_hasta` y `CheckConstraint("descuento_porcentaje BETWEEN 0 AND 100")`. | Low | Overview, STEP 1, STEP 3 | Alineado 100% con el modelo real; en el servicio se restringe además `descuento_porcentaje > 0` para que un cupón represente un descuento real. |
| RC-2 | `Cupon.gerente_id` referencia `medicos.id` (`ForeignKey("medicos.id")`), no `usuarios.id`. | High | Prerequisites, STEP 1, STEP 3 | El servicio debe resolver el registro `Medico` asociado al `Usuario` con `Rol.GERENTE_MEDICO` antes de poblar `Cupon.gerente_id`. |
| RC-3 | No existen aún las capas `app/src/routers/cupones.py`, `app/src/services/cupon_service.py`, `app/src/repos/cupon_repo.py` ni `app/src/clients/cupones_client.py`. | Medium | Actors, Handoff Contracts | Especificados los contratos y responsabilidades exactas para su implementación bajo arquitectura estricta `router -> service -> repo + clients`. |
| RC-4 | La **API de cupones** real (`.ai/APIs/API_Cupones.md`) no genera QR, emite por lotes, vence a 30 días y no tiene anulación. La Entrevista (l. 365-367) acepta código numérico en lugar de QR. | High | STEP 2, ABORT_CLEANUP, Handoff | Se usa código numérico, `qr_url = NULL`, `cantidad` por lote y alerta en lugar de anulación. Asignar a médico pasa al Esc. 30. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01` | Gerente crea 1 cupón de 20% | `201`, 1 fila con `codigo`, `qr_url=NULL`, `usado=False`, `vigente_hasta≈now+30d` |
| `TC-02` | Gerente crea lote de 3 cupones de 15.5% | `201`, 3 filas |
| `TC-03` | Sin token | `401`, no llama a la API |
| `TC-04` | Rol `MEDICO` / `ADMINISTRATIVO` / `PACIENTE` | `403 ROL_NO_AUTORIZADO`, no llama a la API |
| `TC-05` | Descuento `0`, `-5`, `120`, `"abc"`, `null`, `10.555` | `422 DESCUENTO_INVALIDO`, no llama a la API |
| `TC-06` | Cantidad `0`, `21`, `"dos"`, `1.5` | `422 CANTIDAD_INVALIDA` |
| `TC-07` | Gerente sin fila en `medicos` | `409 PERFIL_GERENTE_INCOMPLETO` |
| `TC-08` | API timeout / 5xx | `503`/`502 CUPONES_API_NO_DISPONIBLE`, retryable, 1 sola llamada |
| `TC-09` | API responde 403 | `409 GRUPO_CON_OTRO_GERENTE` |
| `TC-10` | API responde 400 | `502 CUPONES_API_RECHAZO` |
| `TC-11` | API devuelve respuesta mal formada | `502 CUPONES_API_RESPUESTA_INVALIDA`, sin filas |
| `TC-12` | Código ya existente en `cupones` | `409 CODIGO_CUPON_DUPLICADO`, log `ORPHAN_VOUCHER_ALERT` |
| `TC-13` | Falla el `commit` | `500 DB_ERROR`, rollback, log `ORPHAN_VOUCHER_ALERT` |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Todo **gerente médico** tiene tanto una fila en `usuarios` (`rol = Rol.GERENTE_MEDICO`) como una fila en `medicos` (creadas en el Escenario 31). | Verificado en `app/src/core/models/perfiles.py` (docstring de `Medico`) y `economia.py` (`Cupon.gerente_id -> medicos.id`). | Si un gerente médico se creara solo en `usuarios`, la FK `cupones.gerente_id` fallaría. |
| A2 | La **API de cupones** devuelve solo `codigo_cupon` (sin QR). Se usa el código numérico según la Entrevista (l. 365-367). | `.ai/APIs/API_Cupones.md`, `.ai/1-Entrevista.md` | Bajo; `qr_url` es nullable si en el futuro se agrega QR. |
| A3 | La asignación del cupón a un **médico** se hace en el Escenario 30 (`asignar_cupon_a_medico`). | `.ai/APIs/API_Cupones.md` | Bajo. |

## Open Questions

- ¿Existe un límite máximo en la cantidad de **cupones** activos que un **gerente médico** puede crear o asignar a un mismo **médico** por mes, o esa cuota la administra internamente la **API de cupones**?

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada verificando el modelo `Cupon` en `app/src/core/models/economia.py` y el LEL. | Aprobada para implementación en capas `router -> service -> repo + clients`. |
| 2026-11-24 | La spec usaba `/external/vouchers` con QR; la API real usa `/generar_cupones_gerencia` con código numérico. | Actualizada a v1.1: código numérico, lote, sin reintentos, `ABORT_CLEANUP` = alerta, `medico_id` movido al Esc. 30. |