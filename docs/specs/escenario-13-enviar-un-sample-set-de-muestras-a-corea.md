# WORKFLOW: Escenario 13 – Enviar un sample-set de muestras a Corea
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-13-Enviar-un-sample-set-de-muestras-a-corea`

## Símbolos LEL utilizados

| Categoría | Símbolo LEL | Modelo / Tabla en `app/src/core/models/` |
|---|---|---|
| **Sujeto** | `Administrativo` | `Usuario` (`Rol.ADMINISTRATIVO`) en `usuarios` |
| **Objeto** | `Sample set` | `SampleSet` en `sample_sets` (`EstadoSampleSet`) |
| **Objeto** | `Muestra` | `Muestra` en `muestras` |
| **Objeto** | `Estudio` | `Estudio` en `estudios` |
| **Objeto** | `Paciente` | `Paciente` en `pacientes` |
| **Objeto** | `CSV` | Archivo generado y referenciado en `SampleSet.csv_path` |
| **Objeto** | `API del Ministerio de Salud` | Cliente HTTP en `app/src/clients/` |
| **Objeto** | `Autorización del Ministerio` | PDF recibido y referenciado en `SampleSet.autorizacion_ministerio_pdf_path` |
| **Objeto** | `FedEx` | Módulo externo de retiro (`SampleSet.retiro_fedex_fecha`, `retiro_fedex_lugar`, `retiro_fedex_url`, `retiro_fedex_pedido_id`) |
| **Objeto** | `Aviso` | `Aviso` en `avisos` |
| **Verbo** | `Retirar sample set` | Servicio `programar_retiro_fedex` y webhook `confirmar_retiro_fedex` |
| **Estado** | `En espera de retiro` | `EstadoEstudio.EN_ESPERA_RETIRO` (`"En espera de retiro"`) |
| **Estado** | `En viaje a Corea` | `EstadoEstudio.EN_VIAJE_COREA` (`"En viaje a Corea"`) / `EstadoSampleSet.EN_VIAJE_COREA` (`"en_viaje_a_corea"`) |

---

## Overview

- **Objetivo**: Gestionar la autorización ministerial automática y el envío mediante `FedEx` de un `Sample set` sellado al laboratorio biotecnológico de Corea.
- **Contexto**: El `Sample set` ya fue cerrado (`EstadoSampleSet.CERRADO`) con 10 `Muestra`s (o en lote parcial por `Pompe urgente`) y sus `Estudio`s se encuentran en `En espera de retiro`. Antes de salir del país hacia Corea, el lote requiere generar un archivo `CSV` con los `Paciente`s incluidos, enviarlo automáticamente a la `API del Ministerio de Salud` para obtener la `Autorización del Ministerio` en PDF, y luego que el `Administrativo` programe el retiro con `FedEx`, el cual al efectivizarse pasa el `Sample set` y sus `Estudio`s a `En viaje a Corea`.
- **Recursos**: `Sample set` (`sample_sets`), archivo `CSV` (`csv_path`), `Autorización del Ministerio` (`autorizacion_ministerio_pdf_path`), datos de `FedEx` (`retiro_fedex_fecha`, `retiro_fedex_lugar`, `retiro_fedex_url`, `retiro_fedex_pedido_id`).
- **Episodios**:
  1. El sistema genera automáticamente el archivo `CSV` con los `Paciente`s del `Sample set` y lo asocia al lote y sus estudios.
  2. El sistema envía automáticamente el `CSV` a la `API del Ministerio de Salud` sin intervención del `Administrativo`.
  3. El sistema recibe el PDF de `Autorización del Ministerio` y lo asocia al `Sample set` (y por su intermedio a los `Estudio`s del lote).
  4. El `Administrativo` programa el retiro de `FedEx` indicando día, hora (lunes a viernes de 09:00 a 18:00), lugar y la URL de callback.
  5. `FedEx` retira el paquete en el horario programado e invoca la URL de callback del `Sample set`.
  6. El sistema cambia el estado del `Sample set` y de los `Estudio`s de sus `Muestra`s a `En viaje a Corea`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| Sistema (`LogisticaService`) | Genera automáticamente el `CSV` al cerrarse el `Sample set` y lo envía a la `API del Ministerio de Salud`. |
| `API del Ministerio de Salud` | Recibe el `CSV` con los `Paciente`s del `Sample set` y devuelve el PDF de `Autorización del Ministerio` para aduana. |
| `Administrativo` | Programa el día, la hora y el lugar del retiro del `Sample set` con `FedEx`. |
| `FedEx` (API / Simulador externo) | Recibe la solicitud de retiro programado y, a la hora pactada, impacta en la `retiro_fedex_url` del sistema confirmando el retiro del paquete. |
| Capa `router` (`Flask Blueprint`) | Expone `POST /api/sample-sets/{sample_set_id}/retiro-fedex` (para el `Administrativo`) y `POST /api/webhooks/fedex/sample-sets/{sample_set_id}/retirado` (callback de `FedEx`). |
| Capa `service` (`LogisticaService`) | Orquesta la generación del `CSV`, el llamado al Ministerio, la programación en `FedEx` y la transición a `En viaje a Corea`. |
| Capa `repo` (`SampleSetRepo`, `EstudioRepo`, `AvisoRepo`) | Persiste las rutas de archivos, datos de `FedEx` y estados en `PostgreSQL`. |
| Capa `clients` (`MinisterioSaludClient`, `FedExClient`) | Clientes HTTP (`httpx`) hacia la `API del Ministerio de Salud` y el módulo de `FedEx`. |

---

## Prerequisites

- Existe un `SampleSet` en la tabla `sample_sets` con `estado == EstadoSampleSet.CERRADO` y `cerrado_en IS NOT NULL`.
- El `SampleSet` contiene exactamente 10 `Muestra`s válidas (`motivo_descarte IS NULL`), o entre 1 y 10 si `sample_set.es_pompe_urgente == True`.
- Todos los `Estudio`s de las muestras del `SampleSet` están en `EstadoEstudio.EN_ESPERA_RETIRO`.
- Cada `Estudio` tiene asociado su `Paciente` en `pacientes` (con `dni`, `fecha_nacimiento`, `usuario.nombre`, `usuario.apellido`).

---

## Trigger

1. **Fase automática (Episodios 1–3)**: Se dispara inmediatamente al cerrarse el `SampleSet` (STEP 4 del Escenario 12 o STEP 2 del Escenario 14).
2. **Programación de retiro (Episodio 4)**: El `Administrativo` invoca `POST /api/sample-sets/{sample_set_id}/retiro-fedex`.
3. **Confirmación de retiro (Episodios 5–6)**: El módulo de `FedEx` invoca la URL de callback `POST /api/webhooks/fedex/sample-sets/{sample_set_id}/retirado` en la fecha y hora programadas.

---

## Workflow Tree

### STEP 1: Generación automática del archivo CSV de pacientes del Sample Set
**Actor**: `service` (`LogisticaService.generar_csv_sample_set`) -> `repo` (`SampleSetRepo`) -> File Storage
**Action**:
1. Obtiene las `Muestra`s válidas del `SampleSet` junto con sus `Estudio`s, `Paciente`s y `Usuario`s asociados, ordenadas por `Muestra.id`.
2. Genera un archivo CSV UTF-8 con encabezados `muestra_id,estudio_id,paciente_dni,paciente_nombre,paciente_apellido,fecha_nacimiento,patologia_sospechada`.
3. Guarda el archivo en almacenamiento persistente (`storage/sample_sets/sample_set_{id}.csv`) y actualiza `sample_set.csv_path` en la tabla `sample_sets` (quedando vinculado a todos los `Estudio`s del lote a través de `estudio.muestra_vigente.sample_set.csv_path`).
**Timeout**: 5s
**Input**: `{ sample_set_id: 12 }`
**Output on SUCCESS**: `{ sample_set_id: 12, csv_path: "storage/sample_sets/sample_set_12.csv" }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(invalid_state)`: `sample_set.estado != EstadoSampleSet.CERRADO` -> abortar con `409 Conflict` (`code: "SAMPLE_SET_NO_CERRADO"`).
  - `FAILURE(io_error)`: Error de escritura en disco al crear el archivo CSV -> eliminar archivo parcial (`ABORT_CLEANUP`) y reintentar hasta 2 veces; si persiste, registrar alerta operativa para reintento vía `POST /api/sample-sets/{id}/reintentar-autorizacion-ministerio`.

**Observable states during this step**:
  - Customer/Actor sees: `Estudio` en `En espera de retiro`.
  - Operator (`Administrativo`) sees: `SampleSet #12` con archivo `CSV` generado y descargable.
  - Database: `sample_sets.csv_path = 'storage/sample_sets/sample_set_12.csv'`.
  - Logs: `[logistica_service] csv_sample_set_generado sample_set_id=12 path="storage/sample_sets/sample_set_12.csv"`

---

### STEP 2: Envío automático del CSV a la API del Ministerio de Salud y recepción del PDF de Autorización
**Actor**: `service` -> `clients` (`MinisterioSaludClient.solicitar_autorizacion`) -> `repo` (`SampleSetRepo`, `AvisoRepo`)
**Action**:
1. Envía mediante petición HTTP `multipart/form-data` el archivo `CSV` generado en STEP 1 a la `API del Ministerio de Salud` sin requerir intervención del `Administrativo`.
2. Recibe como respuesta el documento PDF de la `Autorización del Ministerio` (que certifica que la lista de pacientes autorizados coincide con los tubos del paquete para el control aduanero rumbo a Corea).
3. Almacena el PDF en `storage/sample_sets/autorizacion_ministerio_{id}.pdf` y actualiza `sample_set.autorizacion_ministerio_pdf_path` en la tabla `sample_sets` (quedando asociado a todos los `Estudio`s del `SampleSet`).
4. Registra un `Aviso` para los usuarios con `Rol.ADMINISTRATIVO` indicando que el `SampleSet` ya cuenta con `Autorización del Ministerio` y está listo para programar el retiro con `FedEx`.
**Timeout**: 15s
**Input**: `{ sample_set_id: 12, csv_path: "storage/sample_sets/sample_set_12.csv" }`
**Output on SUCCESS**: `{ sample_set_id: 12, autorizacion_ministerio_pdf_path: "storage/sample_sets/autorizacion_ministerio_12.pdf" }` -> Aguarda acción del `Administrativo` en STEP 3
**Output on FAILURE**:
  - `FAILURE(external_api_timeout_or_5xx)`: La `API del Ministerio de Salud` no responde dentro de 15s o devuelve HTTP 5xx -> reintentar automáticamente 3 veces con backoff exponencial (2s, 4s, 8s).
  - `FAILURE(external_api_4xx)`: El Ministerio rechaza el formato del CSV -> conservar `sample_set.csv_path`, dejar `sample_set.autorizacion_ministerio_pdf_path = None` y crear `Aviso` de error para el `Administrativo` con opción de reintentar (`POST /api/sample-sets/{sample_set_id}/reintentar-autorizacion-ministerio`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: `Estudio` en `En espera de retiro`.
  - Operator (`Administrativo`) sees: `SampleSet #12` con `CSV` y PDF de `Autorización del Ministerio` asociados; botón `"Programar retiro FedEx"` habilitado.
  - Database: `sample_sets.autorizacion_ministerio_pdf_path = 'storage/sample_sets/autorizacion_ministerio_12.pdf'`.
  - Logs: `[ministerio_client] autorizacion_recibida sample_set_id=12 pdf_path="storage/sample_sets/autorizacion_ministerio_12.pdf"`

---

### STEP 3: Programación del retiro del Sample Set con FedEx por el Administrativo
**Actor**: `Administrativo` -> `router` -> `service` (`LogisticaService.programar_retiro_fedex`) -> `clients` (`FedExClient`) -> `repo` (`SampleSetRepo`)
**Action**:
1. Verifica que el usuario autenticado tenga `Rol.ADMINISTRATIVO`.
2. Verifica que `sample_set.estado == EstadoSampleSet.CERRADO` y que `sample_set.autorizacion_ministerio_pdf_path IS NOT NULL` (no se puede despachar a Corea sin el permiso ministerial).
3. Valida que la fecha y hora de retiro (`retiro_fedex_fecha`) caiga en día hábil (lunes a viernes, no feriado) dentro del horario de atención del laboratorio central (`09:00` a `18:00`).
4. Construye la URL de callback (`retiro_fedex_url = "{BASE_URL}/api/webhooks/fedex/sample-sets/{sample_set_id}/retirado"`).
5. Invoca la API del módulo externo de `FedEx` enviando `sample_set_id`, `fecha_hora_retiro`, `lugar_retiro` y `callback_url`.
6. Persiste en `sample_sets`: `retiro_fedex_fecha`, `retiro_fedex_lugar`, `retiro_fedex_url` y `retiro_fedex_pedido_id` devuelto por `FedEx`. El `SampleSet` permanece en `EstadoSampleSet.CERRADO` (y los estudios en `EstadoEstudio.EN_ESPERA_RETIRO`) hasta que se cumpla la hora de retiro e impacte el callback de `FedEx`.
**Timeout**: 10s
**Input**:
```json
{
  "sample_set_id": 12,
  "fecha_retiro": "2026-10-29T14:00:00",
  "lugar_retiro": "Laboratorio Central - Calle 50 Nro 1200, La Plata"
}
```
**Output on SUCCESS**: `{ sample_set_id: 12, retiro_fedex_pedido_id: "FDX-2026-0012", retiro_fedex_fecha: "2026-10-29T14:00:00", retiro_fedex_url: "..." }` -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no tiene `Rol.ADMINISTRATIVO` -> retornar HTTP `403 Forbidden`.
  - `FAILURE(invalid_state)`: `sample_set.estado != EstadoSampleSet.CERRADO` o `sample_set.autorizacion_ministerio_pdf_path is None` -> retornar HTTP `409 Conflict` (`code: "FALTA_AUTORIZACION_MINISTERIO_O_ESTADO_INVALIDO"`).
  - `FAILURE(validation_error)`: `fecha_retiro` está fuera de lunes a viernes de 09:00 a 18:00, es feriado o está en el pasado -> retornar HTTP `400 Bad Request` (`code: "HORARIO_RETIRO_FEDEX_INVALIDO"`).
  - `FAILURE(conflict)`: El `SampleSet` ya tiene un pedido de retiro activo en `FedEx` (`retiro_fedex_pedido_id IS NOT NULL`) -> retornar HTTP `409 Conflict` (`code: "RETIRO_FEDEX_YA_PROGRAMADO"`).
  - `FAILURE(external_api_error)`: La API de `FedEx` falla o da timeout -> reintentar 2 veces con backoff de 1s; si falla, `ABORT_CLEANUP` y retornar HTTP `502 Bad Gateway` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: `Estudio` en `En espera de retiro`.
  - Operator (`Administrativo`) sees: Retiro programado con `FedEx` (`Pedido #FDX-2026-0012` para el `2026-10-29 14:00`).
  - Database: Tabla `sample_sets` con `retiro_fedex_fecha`, `retiro_fedex_lugar`, `retiro_fedex_url` y `retiro_fedex_pedido_id = 'FDX-2026-0012'`.
  - Logs: `[fedex_client] retiro_programado sample_set_id=12 pedido_id="FDX-2026-0012" fecha="2026-10-29T14:00:00"`

---

### STEP 4: Ejecución del retiro por FedEx y transición a `En viaje a Corea`
**Actor**: `FedEx` -> `router` (`POST /api/webhooks/fedex/sample-sets/{sample_set_id}/retirado`) -> `service` (`LogisticaService.confirmar_retiro_fedex`) -> `repo` (`SampleSetRepo`, `EstudioRepo`)
**Action**: En el día y hora programados, el módulo de `FedEx` invoca la URL (`retiro_fedex_url`) que le fue indicada en STEP 3:
1. Bloquea la fila del `SampleSet` (`SELECT ... FOR UPDATE`).
2. Verifica que `sample_set.estado == EstadoSampleSet.CERRADO` y valida el `pedido_id` / firma del webhook.
3. Cambia `sample_set.estado = EstadoSampleSet.EN_VIAJE_COREA` en la tabla `sample_sets`.
4. Cambia el estado de **todos** los `Estudio`s cuyas muestras integran ese `SampleSet` de `EstadoEstudio.EN_ESPERA_RETIRO` a `EstadoEstudio.EN_VIAJE_COREA`.
**Timeout**: 5s
**Input**:
```json
{
  "sample_set_id": 12,
  "pedido_id": "FDX-2026-0012",
  "retirado_en": "2026-10-29T14:00:00"
}
```
**Output on SUCCESS**: `{ sample_set_id: 12, estado_sample_set: "en_viaje_a_corea", estudios_actualizados_ids: [31, 32, 33, 34, 35, 36, 37, 38, 39, 42] }` -> FIN DEL WORKFLOW (continúa en Escenario 15 cuando llegan los `Datos crudos` desde Corea).
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Firma o `pedido_id` no coincide con `sample_set.retiro_fedex_pedido_id` -> retornar HTTP `401 Unauthorized`.
  - `FAILURE(idempotent_already_in_transit)`: Si `sample_set.estado == EstadoSampleSet.EN_VIAJE_COREA` (reintento del webhook de `FedEx`), responder HTTP `200 OK` idempotente sin volver a mutar datos.
  - `FAILURE(invalid_state)`: `sample_set.estado == EstadoSampleSet.ABIERTO` -> retornar HTTP `409 Conflict`.
  - `FAILURE(database_error)`: Error en base de datos -> `ABORT_CLEANUP` (`session.rollback()`) y retornar HTTP `500 Internal Server Error` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Paciente` y `Médico`) sees: El `Estudio` ahora figura en estado `En viaje a Corea`.
  - Operator (`Administrativo`) sees: `SampleSet #12` y todos sus estudios en estado `En viaje a Corea`.
  - Database:
    - Tabla `sample_sets`: `estado = 'en_viaje_a_corea'`.
    - Tabla `estudios`: `estado = 'En viaje a Corea'` para los 10 estudios del lote.
  - Logs: `[logistica_service] sample_set_en_viaje_a_corea sample_set_id=12 pedido_id="FDX-2026-0012"`

---

### ABORT_CLEANUP: Limpieza de artefactos y reversión transaccional
**Triggered by**: Fallo de escritura de archivos o de base de datos en STEP 1, STEP 2, STEP 3 o STEP 4.
**Actions** (in order):
  1. Ejecutar `session.rollback()` en SQLAlchemy.
  2. Si en STEP 1 o STEP 2 se escribió un archivo truncado/inválido en disco sin llegar a commitear su ruta en `sample_sets`, eliminar el archivo temporal del disco.
  3. Mantener `sample_set.estado = EstadoSampleSet.CERRADO` y `estudio.estado = EstadoEstudio.EN_ESPERA_RETIRO`.
**What customer sees**: `Estudio` permanece en `En espera de retiro`.
**What operator sees**: Mensaje de error detallado y botón para reintentar el paso fallido (solicitud al Ministerio o programación con `FedEx`).

---

## State Transitions

```
SampleSet (EstadoSampleSet):
[cerrado] (csv_path = NULL, autorizacion_ministerio_pdf_path = NULL)
  -- (STEP 1: generación automática de CSV) ------------------> [cerrado] (csv_path != NULL)
  -- (STEP 2: respuesta PDF de API del Ministerio de Salud) --> [cerrado] (autorizacion_ministerio_pdf_path != NULL)
  -- (STEP 3: Administrativo programa retiro con FedEx) ------> [cerrado] (retiro_fedex_pedido_id != NULL)
  -- (STEP 4: Callback de FedEx en el horario de retiro) -----> [en_viaje_a_corea]

Estudio (EstadoEstudio):
[En espera de retiro]
  -- (STEP 4: FedEx retira el SampleSet) ---------------------> [En viaje a Corea]
```

---

## Handoff Contracts

### 1. `Backend (service)` -> `API del Ministerio de Salud (clients)`
**Endpoint**: `POST {MINISTERIO_SALUD_API_URL}/autorizaciones-exportacion` (`multipart/form-data`)
**Payload**:
- Archivo `csv`: contenido de `sample_set_{id}.csv` con las filas de pacientes y muestras del lote.
- Campo `sample_set_id`: `12`.
**Success response** (`200 OK`, `application/pdf` o JSON con PDF en base64/binario):
```json
{
  "ok": true,
  "autorizacion_id": "MSAL-2026-8891",
  "cantidad_pacientes_autorizados": 10,
  "pdf_base64": "JVBERi0xLjQK..."
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "El archivo CSV no contiene las columnas obligatorias.",
  "code": "CSV_INVALIDO",
  "retryable": false
}
```
**Timeout**: 15s
**ON FAILURE**: Reintentar 3 veces con backoff exponencial si `retryable == true` (5xx / timeout); si falla, registrar `Aviso` para el `Administrativo`.

---

### 2. `Administrativo (UI)` -> `Backend (router -> service)` (Programar retiro FedEx)
**Endpoint**: `POST /api/sample-sets/{sample_set_id}/retiro-fedex`
**Payload**:
```json
{
  "fecha_retiro": "2026-10-29T14:00:00",
  "lugar_retiro": "Laboratorio Central - Calle 50 Nro 1200, La Plata"
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "sample_set_id": 12,
  "retiro_fedex_pedido_id": "FDX-2026-0012",
  "retiro_fedex_fecha": "2026-10-29T14:00:00",
  "retiro_fedex_lugar": "Laboratorio Central - Calle 50 Nro 1200, La Plata",
  "retiro_fedex_url": "https://ttps-e.local/api/webhooks/fedex/sample-sets/12/retirado",
  "estado_sample_set": "cerrado"
}
```
**Failure response** (`400` / `403` / `409` / `502`):
```json
{
  "ok": false,
  "error": "El horario de retiro debe ser de lunes a viernes entre las 09:00 y las 18:00.",
  "code": "HORARIO_RETIRO_FEDEX_INVALIDO",
  "retryable": false
}
```
**Timeout**: 10s
**ON FAILURE**: Rollback transaccional; no se persisten campos `retiro_fedex_*`.

---

### 3. `Backend (service)` -> `API de FedEx (clients)`
**Endpoint**: `POST {FEDEX_API_URL}/retiros`
**Payload**:
```json
{
  "referencia_externa": "SAMPLE-SET-12",
  "fecha_hora_retiro": "2026-10-29T14:00:00",
  "direccion_retiro": "Laboratorio Central - Calle 50 Nro 1200, La Plata",
  "callback_url": "https://ttps-e.local/api/webhooks/fedex/sample-sets/12/retirado"
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "pedido_id": "FDX-2026-0012",
  "estado": "PROGRAMADO"
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Servicio de programación FedEx no disponible",
  "code": "FEDEX_UNAVAILABLE",
  "retryable": true
}
```
**Timeout**: 8s
**ON FAILURE**: Reintentar 2 veces con backoff de 1s; si persiste, abortar la operación del `Administrativo` con HTTP `502`.

---

### 4. `API de FedEx` -> `Backend (router -> service)` (Webhook de confirmación de retiro)
**Endpoint**: `POST /api/webhooks/fedex/sample-sets/{sample_set_id}/retirado`
**Payload**:
```json
{
  "pedido_id": "FDX-2026-0012",
  "retirado_en": "2026-10-29T14:00:00"
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "sample_set_id": 12,
  "estado_sample_set": "en_viaje_a_corea",
  "estado_estudios": "En viaje a Corea",
  "cantidad_estudios_actualizados": 10
}
```
**Failure response** (`401` / `404` / `409` / `500`):
```json
{
  "ok": false,
  "error": "El pedido_id no coincide con el retiro programado para este sample-set.",
  "code": "PEDIDO_FEDEX_INVALIDO",
  "retryable": false
}
```
**Timeout**: 5s
**ON FAILURE**: Rollback transaccional; si es error 5xx, `FedEx` reintenta el callback.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Archivo `sample_set_{id}.csv` y columna `sample_sets.csv_path` | Step 1 | `ABORT_CLEANUP` | `os.remove()` del archivo truncado + `session.rollback()` |
| Archivo `autorizacion_ministerio_{id}.pdf` y `autorizacion_ministerio_pdf_path` | Step 2 | `ABORT_CLEANUP` | `os.remove()` del archivo truncado + `session.rollback()` |
| Campos `retiro_fedex_*` en `sample_sets` | Step 3 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Transición a `EN_VIAJE_COREA` en `sample_sets` y `estudios` | Step 4 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/logistica.py` (`SampleSet`, líneas 31-37), las columnas `csv_path`, `autorizacion_ministerio_pdf_path`, `retiro_fedex_fecha`, `retiro_fedex_lugar`, `retiro_fedex_url` y `retiro_fedex_pedido_id` están definidas en la tabla `sample_sets`. Como cada `Estudio` se relaciona con su `Muestra` vigente (`estudio.muestra_vigente.sample_set`), el `CSV` y la `Autorización del Ministerio` quedan automáticamente asociados a todos los `Estudio`s del lote sin duplicar columnas en `estudios`. | Low | STEP 1 & 2 | Documentada explícitamente esta relación en STEP 1 y STEP 2. |
| RC-2 | El LEL establece que cada `Sample set` viaja en un paquete independiente (`"No. Cada uno es un paquete aparte"`, `.ai/1-Entrevista.md` línea 467). | Low | STEP 3 | El endpoint de retiro y el `pedido_id` de `FedEx` operan estrictamente por un único `sample_set_id`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Generación automática de CSV y obtención de PDF de `Autorización del Ministerio` | El `SampleSet #12` se cierra al llegar a 10 muestras | Se genera el archivo CSV con los 10 pacientes, se envía a la `API del Ministerio de Salud`, y `sample_set.csv_path` y `sample_set.autorizacion_ministerio_pdf_path` quedan poblados. |
| `TC-02`: Programación exitosa de retiro con `FedEx` por el `Administrativo` | `POST /api/sample-sets/12/retiro-fedex` para un miércoles a las 14:00 | HTTP `200 OK`; se invoca a `FedEx` con la URL de callback y se guardan `retiro_fedex_fecha`, `retiro_fedex_lugar`, `retiro_fedex_url` y `retiro_fedex_pedido_id`. |
| `TC-03`: Rechazo de programación de retiro sin `Autorización del Ministerio` | `POST /api/sample-sets/12/retiro-fedex` cuando `autorizacion_ministerio_pdf_path is None` | HTTP `409 Conflict` (`FALTA_AUTORIZACION_MINISTERIO_O_ESTADO_INVALIDO`). |
| `TC-04`: Rechazo de programación de retiro fuera del horario de atención o en fin de semana | `POST /api/sample-sets/12/retiro-fedex` a las 20:30 o un día sábado | HTTP `400 Bad Request` (`HORARIO_RETIRO_FEDEX_INVALIDO`). |
| `TC-05`: Rechazo de programación de retiro por un rol distinto a `Administrativo` | `POST /api/sample-sets/12/retiro-fedex` invocado por un `Médico` o `Bioinformático` | HTTP `403 Forbidden`. |
| `TC-06`: Callback de `FedEx` actualiza el `SampleSet` y todos sus `Estudio`s a `En viaje a Corea` | `POST /api/webhooks/fedex/sample-sets/12/retirado` con `pedido_id="FDX-2026-0012"` | HTTP `200 OK`; `sample_set.estado == EstadoSampleSet.EN_VIAJE_COREA` y los 10 `Estudio`s pasan a `EstadoEstudio.EN_VIAJE_COREA`. |
| `TC-07`: Idempotencia del callback de `FedEx` | `FedEx` envía dos veces el mismo webhook `/retirado` | Ambas respuestas devuelven HTTP `200 OK` y el estado permanece consistente en `En viaje a Corea`. |
| `TC-08`: Reintento ante fallo transitorio de la `API del Ministerio de Salud` | El primer intento a la API del Ministerio devuelve `503` y el segundo `200 OK` | El cliente reintenta con backoff y completa la persistencia de `autorizacion_ministerio_pdf_path`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El Ministerio de Salud siempre autoriza la totalidad de los pacientes incluidos en el CSV válido (no existen autorizaciones parciales de un `SampleSet`). | `.ai/1-Entrevista.md` (líneas 345-348: `"¿Puede darse el caso de que en el PDF que devuelve el Ministerio haya menos pacientes...? No. Además no tiene potestad el Ministerio para saber lo que yo estoy mandando"`) | Low |

## Open Questions

- Ninguna pregunta abierta bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/logistica.py`, `estudios.py` y `enums.py`. | Estado marcado como `Approved`. |
