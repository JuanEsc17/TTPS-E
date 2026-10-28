# WORKFLOW: Escenario 29 – Crear un cupón
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-29`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Gerente médico** | `Usuario` (`rol = Rol.GERENTE_MEDICO`) + perfil `Medico` (`medicos.id`) |
| **Sujetos** | **Médico** | `Medico` (`medicos.id`, destinatario opcional de asignación de cupón por el gerente médico) |
| **Objetos** | **Cupón** | Modelo `Cupon` (tabla `cupones`: `id`, `codigo`, `qr_url`, `descuento_porcentaje`, `gerente_id`, `medico_id`, `paciente_id`, `usado`, `usado_en`, `vigente_hasta`) |
| **Objetos** | **API de cupones** | Cliente HTTP externo (`app/src/core/clients/cupones_client.py`) hacia el módulo externo de generación y validación de cupones con QR/código numérico |
| **Verbos** | **Pagar presupuesto** | Flujo posterior que consume el **cupón** creado (ver Escenario 30) |
| **Estados** | *(No altera `EstadoEstudio`)* | La creación de un **cupón** es independiente de un **estudio** específico |

---

## Overview

- **Objetivo:** Generar un **cupón** de descuento limitado para ser usado posteriormente en el pago del **presupuesto** de un **estudio**.
- **Contexto:** El **gerente médico** quiere ofrecer un descuento porcentual a **pacientes** (asignándolo opcionalmente a un **médico** tratante para que este lo entregue a un **paciente**).
- **Recursos:** **Cupón**, descuento (`descuento_porcentaje`), **API de cupones**, código QR (`qr_url`) o código numérico (`codigo`).
- **Episodios:**
  1. El **gerente médico** solicita crear un **cupón**.
  2. El **gerente médico** define el descuento del **cupón** (y opcionalmente el **médico** al que se le asigna).
  3. El sistema pide el **cupón** a la **API de cupones**.
  4. El sistema registra el **cupón** con su código y URL de QR en la base de datos.

**Resumen del flujo:** El **gerente médico** autenticado envía una petición `POST /api/cupones` indicando el porcentaje de descuento (`descuento_porcentaje` entre `0.01` y `100.00`) y opcionalmente el `medico_id` al cual asignarlo. El `router` delega en `cupon_service`, que valida reglas de dominio y existencia del perfil `Medico` del gerente (y del médico destinatario si fue provisto). Luego invoca a la **API de cupones** mediante `cupones_client` para emitir el voucher externo con su `codigo`, `qr_url` y `vigente_hasta`. Finalmente, `cupon_repo` persiste el registro en la tabla `cupones`. Si la persistencia local falla tras haberse emitido el cupón en la **API de cupones**, se ejecuta `ABORT_CLEANUP` para anular/vencer el cupón en la API externa y evitar cupones huérfanos.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Gerente médico** (Sujeto LEL) | Inicia la solicitud de creación de **cupón** y define el porcentaje de descuento desde la interfaz web. |
| **Router HTTP** (`app/src/routers/cupones.py`) | Verifica sesión activa, rol `Rol.GERENTE_MEDICO`, deserializa el payload JSON y devuelve la respuesta HTTP estandarizada. |
| **Servicio de Cupones** (`app/src/services/cupon_service.py`) | Valida el rango del descuento (`0 < descuento_porcentaje <= 100`), verifica los perfiles en `medicos`, coordina la llamada al cliente HTTP externo y la transacción de base de datos. |
| **Cliente API de Cupones** (`app/src/clients/cupones_client.py`) | Se comunica vía `httpx` con el objeto LEL **API de cupones** para solicitar la generación del código numérico y QR, y para revocar el cupón en caso de rollback local. |
| **Repositorio de Cupones** (`app/src/repos/cupon_repo.py`) | Ejecuta las consultas e inserciones SQLAlchemy sobre las tablas `cupones` y `medicos`. |
| **PostgreSQL** (`db`) | Persiste la fila en `cupones` garantizando las restricciones `UNIQUE(codigo)` y `CHECK(descuento_porcentaje BETWEEN 0 AND 100)`. |

---

## Prerequisites

- **Sesión y Rol:** El usuario autenticado debe poseer una sesión activa válida, tener `Usuario.rol == Rol.GERENTE_MEDICO` y `Usuario.debe_cambiar_password == False`.
- **Datos existentes en `app/src/core/models/`:**
  - Debe existir una fila en `usuarios` correspondiente al **gerente médico** y su fila vinculada en `medicos` (`medicos.usuario_id == usuarios.id`), cuyo `medicos.id` se utilizará como `cupones.gerente_id`.
  - Si en la solicitud se incluye `medico_id` para asignar el cupón a un **médico** en el mismo acto, debe existir dicha fila en la tabla `medicos`.
- **Estado previo del `Estudio`:** No aplica (`N/A`); el **cupón** se crea antes de ser aplicado al pago del **presupuesto** de un **estudio**.
- **Servicios externos:** La **API de cupones** debe estar accesible a través de la red interna/configuración `CUPONES_API_BASE_URL`.

---

## Trigger

- **Acción de usuario:** El **gerente médico** completa el formulario "Nuevo Cupón de Descuento" e ingresa el porcentaje de descuento (y opcionalmente selecciona un **médico**) y presiona "Crear cupón".
- **Endpoint HTTP:** `POST /api/cupones`

---

## Workflow Tree

### STEP 1: Autenticación, autorización de rol y validación de entrada
**Actor**: Router HTTP (`cupones.py`) -> Servicio de Cupones (`cupon_service.py`) -> Repositorio (`cupon_repo.py`)
**Action**: Verifica que la sesión pertenezca a un usuario con `Rol.GERENTE_MEDICO`, recupera su perfil `Medico` (`gerente_id`), valida que `descuento_porcentaje` sea un `Decimal` con `0 < descuento_porcentaje <= 100` (máximo 2 decimales) y, si se envió `medico_id`, comprueba que exista en la tabla `medicos`.
**Timeout**: `2s`
**Input**:
```json
{
  "usuario_autenticado_id": "int",
  "rol": "Rol.GERENTE_MEDICO",
  "descuento_porcentaje": "Decimal (0.01 .. 100.00)",
  "medico_id": "int | null"
}
```
**Output on SUCCESS**: `{ gerente_medico_id: int, descuento_porcentaje: Decimal, medico_id: int | null }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: No hay sesión activa o el token expiró -> retornar `401 Unauthorized`, sin efectos secundarios.
  - `FAILURE(forbidden)`: El usuario autenticado tiene un rol distinto de `Rol.GERENTE_MEDICO` (por ejemplo, `Rol.MEDICO` o `Rol.ADMINISTRATIVO`) -> retornar `403 Forbidden` con código `ROL_NO_AUTORIZADO`, sin limpieza necesaria.
  - `FAILURE(validation_error)`: `descuento_porcentaje` ausente, no numérico, `<= 0` o `> 100`, o `medico_id` inexistente en `medicos` -> retornar `422 Unprocessable Entity` / `404 Not Found` con detalle del campo inválido, sin limpieza necesaria.
  - `FAILURE(invalid_state)`: El usuario con `Rol.GERENTE_MEDICO` no posee registro asociado en la tabla `medicos` -> retornar `409 Conflict` (`PERFIL_GERENTE_INCOMPLETO`), registrar alerta en logs.

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
**Action**: Inserta una nueva fila en la tabla `cupones` con `codigo`, `qr_url`, `descuento_porcentaje`, `gerente_id`, `medico_id` (si fue provisto), `paciente_id = NULL`, `usado = False`, `usado_en = NULL` y `vigente_hasta`, y confirma la transacción (`COMMIT`).
**Timeout**: `3s`
**Input**:
```json
{
  "codigo": "EXOMA-2026-88412",
  "qr_url": "https://cupones.exoma.local/qr/EXOMA-2026-88412.pdf",
  "descuento_porcentaje": "25.00",
  "gerente_id": 4,
  "medico_id": 12,
  "vigente_hasta": "2026-12-31T23:59:59Z"
}
```
**Output on SUCCESS**: `{ cupon: Cupon }` -> Retornar `201 Created` al **gerente médico** (FIN DEL WORKFLOW).
**Output on FAILURE**:
  - `FAILURE(conflict)`: Violación de restricción `UNIQUE(codigo)` en `cupones` (`IntegrityError` porque la **API de cupones** devolvió un código ya registrado o por doble envío concurrente) -> hacer `ROLLBACK` local -> GO TO `ABORT_CLEANUP` -> retornar `409 Conflict` (`CODIGO_CUPON_DUPLICADO`).
  - `FAILURE(validation_error)`: Violación de `CheckConstraint("descuento_porcentaje BETWEEN 0 AND 100")` -> `ROLLBACK` local -> GO TO `ABORT_CLEANUP` -> retornar `422 Unprocessable Entity`.
  - `FAILURE(timeout / database_error)`: Error de conexión o timeout en PostgreSQL -> `ROLLBACK` local -> GO TO `ABORT_CLEANUP` -> retornar `500 Internal Server Error` (`DB_PERSISTENCE_ERROR`, `retryable=True`).

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
  1. Ejecutar `session.rollback()` en SQLAlchemy para asegurar que no quede ninguna transacción abierta ni fila parcial en `cupones`.
  2. Invocar a `cupones_client.anular_cupon(codigo)` (`POST /external/vouchers/{codigo}/consumir` o `DELETE /external/vouchers/{codigo}`) en la **API de cupones** para invalidar el código externo no persistido localmente.
  3. Si la anulación en la **API de cupones** falla tras 2 reintentos, registrar un log de severidad `CRITICAL` con etiqueta `ORPHAN_VOUCHER_ALERT` y el `codigo` para conciliación operativa.
**What customer/actor (**Gerente médico**) sees**: Mensaje de error claro indicando que no se pudo registrar el cupón y que puede reintentar la operación.
**What operator sees**: Log `ERROR` o alerta `ORPHAN_VOUCHER_ALERT` con el `codigo` externo y la causa raíz del fallo de base de datos.

---

## State Transitions

```
Cupon (Ciclo de vida en Escenario 29):
  [Inexistente]
    -- (STEP 1 + STEP 2 + STEP 3 exitosos, sin medico_id) --> [Creado / Disponible (cupones.usado = False, medico_id = NULL, paciente_id = NULL)]
    -- (STEP 1 + STEP 2 + STEP 3 exitosos, con medico_id) --> [Asignado a Médico (cupones.usado = False, medico_id = <id>, paciente_id = NULL)]
    -- (STEP 2 exitoso + STEP 3 falla + ABORT_CLEANUP exitoso) --> [Inexistente localmente / Vencido en API de cupones]
    -- (STEP 2 exitoso + STEP 3 falla + ABORT_CLEANUP falla) --> [Inexistente localmente + ORPHAN_VOUCHER_ALERT]

Estudio (EstadoEstudio):
  Sin transición en este escenario (no requiere ni modifica filas de `estudios`).
```

---

## Handoff Contracts

### 1. Frontend (Gerente médico) -> Backend (`router` -> `service`)
**Endpoint**: `POST /api/cupones`
**Payload**:
```json
{
  "descuento_porcentaje": 25.00,
  "medico_id": 12
}
```
*(Nota: `medico_id` es opcional; puede enviarse `null` si el **gerente médico** solo crea el **cupón** y lo asigna más adelante).*

**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "id": 105,
    "codigo": "EXOMA-2026-88412",
    "qr_url": "https://cupones.exoma.local/qr/EXOMA-2026-88412.pdf",
    "descuento_porcentaje": 25.00,
    "gerente_id": 4,
    "medico_id": 12,
    "paciente_id": null,
    "usado": false,
    "usado_en": null,
    "vigente_hasta": "2026-12-31T23:59:59Z",
    "created_at": "2026-10-28T19:55:00Z"
  }
}
```
**Failure response** (`401` / `403` / `404` / `409` / `422` / `502` / `504`):
```json
{
  "ok": false,
  "error": "El porcentaje de descuento debe ser mayor a 0 y menor o igual a 100.",
  "code": "DESCUENTO_INVALIDO",
  "retryable": false
}
```
**Timeout**: `10s`
**ON FAILURE**: Mostrar mensaje de error en el formulario; si `retryable == true`, habilitar reintento manual sin recargar la página.

---

### 2. Backend (`cupones_client`) -> API de cupones
**Endpoint**: `POST /external/vouchers`
**Payload**:
```json
{
  "descuento_porcentaje": 25.00,
  "emitido_por_gerente_id": 4
}
```
**Success response** (`201 Created`):
```json
{
  "codigo": "EXOMA-2026-88412",
  "qr_url": "https://cupones.exoma.local/qr/EXOMA-2026-88412.pdf",
  "vigente_hasta": "2026-12-31T23:59:59Z",
  "vigente": true
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Servicio de generación de QR temporalmente no disponible",
  "code": "CUPONES_API_UNAVAILABLE",
  "retryable": true
}
```
**Timeout**: `5s` por intento (máximo 3 intentos con backoff `0.5s`, `1.0s`).
**ON FAILURE**: Si falla tras los reintentos, abortar antes de tocar PostgreSQL y devolver `502`/`504` al cliente.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Voucher externo en **API de cupones** (`codigo`, `qr_url`) | Step 2 | `ABORT_CLEANUP` | Llamada HTTP `POST /external/vouchers/{codigo}/consumir` (o `DELETE`) vía `cupones_client` |
| Fila en tabla `cupones` (en memoria de sesión SQLAlchemy) | Step 3 | `ABORT_CLEANUP` | `db.session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | El modelo `Cupon` ya existe en `app/src/core/models/economia.py` con las columnas exactas `id`, `codigo`, `qr_url`, `descuento_porcentaje`, `gerente_id`, `medico_id`, `paciente_id`, `usado`, `usado_en`, `vigente_hasta` y `CheckConstraint("descuento_porcentaje BETWEEN 0 AND 100")`. | Low | Overview, STEP 1, STEP 3 | Alineado 100% con el modelo real; en el servicio se restringe además `descuento_porcentaje > 0` para que un cupón represente un descuento real. |
| RC-2 | `Cupon.gerente_id` referencia `medicos.id` (`ForeignKey("medicos.id")`), no `usuarios.id`. | High | Prerequisites, STEP 1, STEP 3 | El servicio debe resolver el registro `Medico` asociado al `Usuario` con `Rol.GERENTE_MEDICO` antes de poblar `Cupon.gerente_id`. |
| RC-3 | No existen aún las capas `app/src/routers/cupones.py`, `app/src/services/cupon_service.py`, `app/src/repos/cupon_repo.py` ni `app/src/clients/cupones_client.py`. | Medium | Actors, Handoff Contracts | Especificados los contratos y responsabilidades exactas para su implementación bajo arquitectura estricta `router -> service -> repo + clients`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Creación de cupón sin médico asignado | `POST /api/cupones` con `descuento_porcentaje=20.00` por usuario `Rol.GERENTE_MEDICO` y **API de cupones** operativa | Retorna `201 Created`, persiste fila en `cupones` con `codigo`, `qr_url`, `gerente_id`, `medico_id=None`, `usado=False`. |
| `TC-02`: Happy path – Creación de cupón asignado directamente a un médico | `POST /api/cupones` con `descuento_porcentaje=15.50` y `medico_id` existente | Retorna `201 Created`, persiste fila en `cupones` con `medico_id` seteado y `paciente_id=None`. |
| `TC-03`: Rechazo por rol no autorizado | `POST /api/cupones` invocado por un usuario con `Rol.MEDICO`, `Rol.ADMINISTRATIVO` o `Rol.PACIENTE` | Retorna `403 Forbidden` (`ROL_NO_AUTORIZADO`), no llama a la **API de cupones** ni inserta en `cupones`. |
| `TC-04`: Validación de porcentaje fuera de rango (`<= 0` o `> 100`) | `POST /api/cupones` con `descuento_porcentaje=0` o `descuento_porcentaje=120` | Retorna `422 Unprocessable Entity` (`DESCUENTO_INVALIDO`), sin llamadas externas ni escrituras en BD. |
| `TC-05`: Médico destinatario inexistente | `POST /api/cupones` con `medico_id=99999` inexistente en `medicos` | Retorna `404 Not Found` (`MEDICO_NO_ENCONTRADO`), sin llamar a la **API de cupones**. |
| `TC-06`: Timeout / caída de la API de cupones | `POST /api/cupones` cuando `cupones_client` lanza `httpx.TimeoutException` en los 3 intentos | Reintenta 3 veces en total, retorna `504 Gateway Timeout` (`CUPONES_API_TIMEOUT`, `retryable=True`) y la tabla `cupones` permanece intacta. |
| `TC-07`: Fallo transitorio recuperado en el segundo intento | `POST /api/cupones` cuando la **API de cupones** devuelve `503` en el intento 1 y `201` en el intento 2 | El servicio completa el flujo sin error, persiste el cupón en `cupones` y retorna `201 Created`. |
| `TC-08`: Fallo de persistencia en BD por `codigo` duplicado dispara `ABORT_CLEANUP` | La **API de cupones** devuelve un `codigo` ya existente en `cupones` | `cupon_repo` hace `rollback()`, se invoca `cupones_client.anular_cupon(codigo)` en `ABORT_CLEANUP` y retorna `409 Conflict` (`CODIGO_CUPON_DUPLICADO`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Todo **gerente médico** tiene tanto una fila en `usuarios` (`rol = Rol.GERENTE_MEDICO`) como una fila en `medicos` (creadas en el Escenario 31). | Verificado en `app/src/core/models/perfiles.py` (docstring de `Medico`) y `economia.py` (`Cupon.gerente_id -> medicos.id`). | Si un gerente médico se creara solo en `usuarios`, la FK `cupones.gerente_id` fallaría. |
| A2 | La **API de cupones** devuelve tanto el `codigo` alfanumérico/numérico como `qr_url` (o al menos `codigo` obligatorio y `qr_url` opcional). | Verificado en `.ai/1-Entrevista.md` (líneas 365-367) y `Cupon.qr_url: Mapped[Optional[str]]`. | Bajo; el modelo soporta `qr_url = NULL` si el módulo externo opera solo con código numérico. |
| A3 | El **gerente médico** puede asignar el cupón a un **médico** durante la creación o mediante un endpoint de asignación a médico (`PATCH /api/cupones/{id}/asignar-medico`). | Verificado en `.ai/2-Glosario_LEL.md` ("El gerente médico asigna cupones a los médicos"). | Bajo; ambos caminos actualizan `cupones.medico_id`. |

## Open Questions

- ¿Existe un límite máximo en la cantidad de **cupones** activos que un **gerente médico** puede crear o asignar a un mismo **médico** por mes, o esa cuota la administra internamente la **API de cupones**?

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada verificando el modelo `Cupon` en `app/src/core/models/economia.py` y el LEL. | Aprobada para implementación en capas `router -> service -> repo + clients`. |
