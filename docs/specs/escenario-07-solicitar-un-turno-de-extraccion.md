# WORKFLOW: Escenario 7 – Solicitar un turno de extracción
**Versión**: 1.2
**Fecha**: 2026-11-25
**Autor**: Workflow Architect & Software Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-7`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Paciente` |
| **Objetos** | `Estudio`, `Centro de extracción`, `Turno`, `Orden de extracción`, `Consentimiento informado`, `Recordatorio`, `Presupuesto`, `Cuota`, `Registro de modificaciones`, `Aviso` |
| **Verbos** | `Sacar turno`, `Registrar modificación` |
| **Estados** | `Creado`, `Autorizado`, `Remuestreo requerido`, `Turno sacado` |

---

## Overview

- **Objetivo**: Asignar un `Turno` de extracción de sangre de 15 minutos en uno de los 100 `Centros de extracción` del país para un `Paciente` cuyo `Estudio` está autorizado o pagado (o en remuestreo sin costo), cambiar el `Estudio` al estado `Turno sacado`, generar y asociar al `Turno` el PDF unificado de `Orden de extracción` y `Consentimiento informado`, notificar su disponibilidad mediante un `Aviso` en la aplicación (`CanalAviso.APP`) y enviar el `Recordatorio` del turno.
- **Contexto**: El `Estudio` ya fue `Autorizado` por la `Obra social` (Escenarios 4 o 5), o fue abonado de forma particular teniendo un `Pago` activo en estado `Creado` (Escenario 6), o requiere una nueva muestra sin costo por estar en `Remuestreo requerido` (Escenario 10), o el `Paciente` faltó de 1 a 4 veces a un turno previo (`ausencias < 5`, Escenario 33) y necesita reservar un nuevo `Turno`. Los `Turnos` son de 15 minutos, para una sola persona por centro y horario, de lunes a viernes de 09:00 a 18:00, excluyendo feriados.
- **Recursos**: Mapa de `Centros de extracción` (`centros_extraccion`), agenda de `Turnos` (`turnos`), archivo PDF de `Orden de extracción` y `Consentimiento informado` asociado al `Turno` (`storage/turnos/orden_consentimiento_turno_{turno_id}.pdf`), `Aviso` en la aplicación (`CanalAviso.APP`), `Recordatorio` por mail (con fecha, hora y advertencia del límite de `MAX_AUSENCIAS = 5` ausencias).
- **Episodios**:
  1. El `Paciente` consulta los `Centros de extracción` disponibles en el mapa.
  2. El sistema muestra los `Centros de extracción` con sus coordenadas (`latitud`, `longitud`) y sus `Turnos` libres de 15 minutos (lunes a viernes de 09:00 a 18:00, sin feriados).
  3. El `Paciente` selecciona un `Centro de extracción`.
  4. El `Paciente` selecciona un `Turno` libre (`inicio`).
  5. El sistema registra el `Turno` (`activo = True`), pasa el `Estudio` al estado `Turno sacado` (`EstadoEstudio.TURNO_SACADO`), genera y guarda junto al `Turno` el PDF de `Orden de extracción` y `Consentimiento informado` (descargable cuando el paciente lo desee), emite un `Aviso` in-app (`CanalAviso.APP`) para su descarga y envía el `Recordatorio` del turno.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` | Sujeto LEL que visualiza el mapa de `Centros de extracción`, elige un `Turno` libre, recibe el `Aviso` en la aplicación y descarga cuando lo necesite el PDF de `Orden de extracción` y `Consentimiento informado`. |
| `router` (`turnos_router`) | Capa HTTP Flask (`GET /api/v1/centros-extraccion`, `GET /api/v1/centros-extraccion/{centro_id}/turnos-disponibles`, `POST /api/v1/estudios/{estudio_id}/turnos`, `GET /api/v1/turnos/{turno_id}/consentimiento-pdf`). |
| `service` (`turno_service`) | Capa de negocio que valida horarios hábiles (lunes a viernes 09:00–18:00, múltiplos de 15 min, no feriado), verifica habilitación económica/estado del `Estudio`, crea el `Turno`, genera y guarda el PDF en `almacenamiento_service`, crea el `Aviso` in-app y dispara el `Recordatorio`. |
| `repo` (`turno_repo`) | Capa de acceso a datos SQLAlchemy sobre `centros_extraccion`, `turnos`, `estudios`, `pagos`, `avisos`. |
| `clients` (`email_client`, `almacenamiento_service`) | Servicio de almacenamiento de PDFs de turnos (`storage/turnos/orden_consentimiento_turno_{turno_id}.pdf`) y cliente de correo para el `Recordatorio`. |
| `PostgreSQL` | Base de datos relacional que garantiza exclusión mutua del slot mediante el índice parcial único `uq_turno_activo` (`centro_id`, `inicio` donde `activo = True`). |

---

## Prerequisites

- El usuario autenticado tiene `Usuario.rol == Rol.PACIENTE`, `debe_cambiar_password == False` y es titular del `Estudio` (`estudio.paciente.usuario_id == usuario_actual.id`).
- El `Centro de extracción` (`centros_extraccion.id == centro_id`) existe en la base de datos.
- El `Estudio` (`estudios.id == estudio_id`) cumple **una** de las siguientes condiciones de habilitación:
  1. `estudio.estado == EstadoEstudio.AUTORIZADO`, **o**
  2. `estudio.estado == EstadoEstudio.CREADO` y posee un `Pago` vigente con `anulado == False` y `estado in (EstadoPago.PAGADO, EstadoPago.PARCIAL)` (pago total o al menos cuota #1 abonada vía `MercadoPago`) en `estudio.presupuesto.pagos`, **o**
  3. `estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO`, **o**
  4. `estudio.estado == EstadoEstudio.TURNO_SACADO`, no tiene ningún `Turno` futuro con `activo == True` y `asistio is None` (porque el turno anterior ya pasó y fue marcado con `asistio == False`), y `estudio.ausencias < 5`.
- No existe otro `Turno` con `activo == True` y `asistio is None` para ese mismo `estudio_id`.

---

## Trigger

1. **Consulta previa en el mapa**: El `Paciente` abre el mapa interactivo (`GET /api/v1/centros-extraccion`) y consulta los horarios libres de una fecha (`GET /api/v1/centros-extraccion/{centro_id}/turnos-disponibles?fecha=YYYY-MM-DD`).
2. **Reserva del turno**: El `Paciente` selecciona el slot de 15 minutos y confirma:
   - **Endpoint HTTP**: `POST /api/v1/estudios/{estudio_id}/turnos` (autenticado con rol `paciente`).

---

## Workflow Tree

### STEP 1: Validación de rol del `Paciente`, habilitación del `Estudio` y reglas de agenda del `Turno`
**Actor**: `router` (`turnos_router`) -> `service` (`turno_service`) -> `repo` (`estudio_repo`, `turno_repo`)
**Action**:
1. Verifica que el usuario autenticado tenga `Usuario.rol == Rol.PACIENTE` y sea el titular del `Estudio` (`estudio.paciente.usuario_id == usuario_actual.id`).
2. Carga el `Estudio` con `SELECT ... FOR UPDATE` y verifica que esté habilitado para sacar turno (`AUTORIZADO`, `CREADO` con `Pago` vigente `anulado == False` y `estado in (EstadoPago.PAGADO, EstadoPago.PARCIAL)`, `REMUESTREO_REQUERIDO`, o `TURNO_SACADO` tras ausencia con `ausencias < 5` y sin turno activo pendiente).
3. Verifica que el `Estudio` no tenga ya un `Turno` activo pendiente de asistencia (`activo == True` y `asistio is None`).
4. Verifica que `centro_id` exista en `centros_extraccion`.
5. Valida las reglas de negocio del horario `inicio`:
   - Debe ser futuro (`inicio > ahora`).
   - Día de la semana de lunes a viernes (`inicio.weekday() in (0, 1, 2, 3, 4)`).
   - No debe ser un día feriado nacional.
   - Hora entre las `09:00` y las `17:45` inclusive (para que el turno de 15 minutos finalice a más tardar a las `18:00`), con minutos en `{0, 15, 30, 45}` y segundos `0`.
**Timeout**: `2s`
**Input**: `estudio_id`, `centro_id`, `inicio` (ISO-8601), `usuario_actual` (`Paciente`).
**Output on SUCCESS**: `Estudio` y `CentroExtraccion` validados -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no tiene `Rol.PACIENTE` o no es titular del `Estudio` -> `return 403 Forbidden` (`code: "FORBIDDEN_NOT_OWNER"`).
  - `FAILURE(not_found)`: `estudio_id` o `centro_id` no existen -> `return 404 Not Found` (`code: "RECURSO_NO_ENCONTRADO"`).
  - `FAILURE(invalid_state)`: El `Estudio` no está pagado ni autorizado ni en remuestreo, o ya tiene un turno activo reservado -> `return 409 Conflict` (`{"ok": false, "error": "El estudio no se encuentra habilitado para sacar turno o ya posee un turno activo", "code": "ESTUDIO_NO_HABILITADO_TURNO", "retryable": false}`).
  - `FAILURE(validation_error)`: El horario `inicio` cae en fin de semana, feriado, fuera de la franja 09:00–18:00 o no es múltiplo de 15 minutos -> `return 422 Unprocessable Entity` (`{"ok": false, "error": "Los turnos solo pueden reservarse de lunes a viernes de 09:00 a 18:00 cada 15 minutos, excepto feriados", "code": "HORARIO_TURNO_INVALIDO", "retryable": false}`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Spinner `"Reservando turno en el centro de extracción..."`.
  - **Operator sees**: Validación de agenda en curso.
  - **Database**: Lectura `FOR UPDATE` sobre `estudios` y consulta a `centros_extraccion` y `turnos`.
  - **Logs**: `[turno_service] STEP 1 estudio_id=<eid> centro_id=<cid> inicio=<iso>`

---

### STEP 2: Reserva atómica del `Turno` y transición del `Estudio` a `Turno sacado`
**Actor**: `service` (`turno_service`) -> `repo` (`turno_repo`, `estudio_repo`) -> `PostgreSQL`
**Action**:
1. Inserta una fila en la tabla `turnos`:
   - `centro_id = centro.id`
   - `paciente_id = estudio.paciente_id`
   - `estudio_id = estudio.id`
   - `inicio = inicio`
   - `activo = True`
   - `asistio = None`
2. Si `estado_anterior != EstadoEstudio.TURNO_SACADO`, actualiza `estudio.estado = EstadoEstudio.TURNO_SACADO` (`"Turno sacado"`) y registra la transición en `registro_modificaciones` (`entidad_tipo = 'estudio'`, `entidad_id = estudio.id`, `accion = 'cambio_estado'`, `cambios = {"estado": {"anterior": estado_anterior, "nuevo": EstadoEstudio.TURNO_SACADO}}`).
3. Ejecuta `session.flush()` para validar el índice único parcial `uq_turno_activo` (`centro_id`, `inicio` donde `activo = True`).
**Timeout**: `3s`
**Input**: `Estudio`, `CentroExtraccion`, `inicio`
**Output on SUCCESS**: `Turno` persistido (`turno.id`) y `estudio.estado == EstadoEstudio.TURNO_SACADO` -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(conflict)`: `IntegrityError` sobre el índice `uq_turno_activo` porque otro paciente reservó el mismo `centro_id` e `inicio` simultáneamente -> `session.rollback()` -> `return 409 Conflict` (`{"ok": false, "error": "El turno seleccionado acaba de ser ocupado por otro paciente. Por favor elija otro horario.", "code": "TURNO_OCUPADO", "retryable": false}`).
  - `FAILURE(db_error)` / `FAILURE(timeout)`: Error de base de datos -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: `"Generando orden de extracción y consentimiento informado..."`.
  - **Operator sees**: Slot `(centro_id, inicio)` ocupado en `turnos`.
  - **Database**: Fila insertada en `turnos` (`activo = True`, `asistio = NULL`); `estudios.estado = EstadoEstudio.TURNO_SACADO`.
  - **Logs**: `[turno_repo] STEP 2 turno_id=<tid> estudio_id=<eid> estado=Turno sacado`

---

### STEP 3: Generación/guardado de PDF en el `Turno`, `Aviso` en la app y `Recordatorio`
**Actor**: `service` (`turno_service` + `pdf_consentimiento`) -> `clients` (`almacenamiento_service`, `email_client`) -> `repo` (`turno_repo`)
**Action**:
1. Genera el PDF A4 unificado (`construir_pdf_orden_y_consentimiento`) con los datos del `Turno`, `CentroExtraccion`, `Estudio`, `Paciente` y `Medico`:
   - **Orden de extracción**: Determinaciones solicitadas, indicación expresa de que no requiere ayuno ni preparación especial y matrícula del profesional.
   - **Consentimiento informado**: Plantilla formal con fecha/hora de extracción y bloques de aceptación/firma para que el `Paciente` (o su responsable legal) imprima, complete, firme y entregue en el `Centro de extracción`.
2. Persiste el PDF asociado al `Turno` en `almacenamiento_service` bajo la ruta `storage/turnos/orden_consentimiento_turno_{turno.id}.pdf` para que el paciente pueda descargarlo cuando lo desee mediante `GET /api/v1/turnos/{turno_id}/consentimiento-pdf`.
3. Inserta un **`Aviso` en la aplicación** (`canal = CanalAviso.APP`, `enviado = True`) indicando que la `Orden de extracción` y el `Consentimiento informado` (PDF) del `Turno #{turno.id}` (`Estudio #{estudio.id}`) están disponibles para descargar desde la app y desde **Mis turnos**.
4. Inserta el `Aviso` de recordatorio (`canal = CanalAviso.MAIL`) y envía mediante `EmailClient` el `Recordatorio` del turno con fecha, hora, sede y la advertencia de `MAX_AUSENCIAS = 5` ausencias. Finalmente marca el aviso enviado y ejecuta `session.commit()`.
**Timeout**: `6s`
**Input**: `Turno`, `Estudio`, `CentroExtraccion`, `Paciente`.
**Output on SUCCESS**: Respuesta `201 Created` con los datos del `Turno`, URL de descarga (`consentimiento_pdf_url`) y confirmación de emisión -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(storage_or_mail_error)`: Si falla el almacenamiento del PDF o el despacho de correo -> `GO TO ABORT_CLEANUP` (elimina el PDF si alcanzó a crearse, hace rollback de BD y retorna `502 Bad Gateway` con `retryable: true`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Ticket de confirmación con botón `"Descargar Orden y Consentimiento (PDF)"`, aviso nuevo en la campana con descarga directa y recordatorio por correo; además puede volver a descargarlo cuando quiera desde `"Mis turnos"`.
  - **Operator sees**: `Estudio` en estado `Turno sacado` con turno activo y archivo `storage/turnos/orden_consentimiento_turno_{turno_id}.pdf`.
  - **Database**: `turnos` (`activo = True`), `estudios` (`estado = EstadoEstudio.TURNO_SACADO`), `avisos` (`CanalAviso.APP` y `CanalAviso.MAIL`, `enviado = True`).
  - **Logs**: `[turno_service] STEP 3 completado turno_id=<tid> pdf_guardado=True`

---

### ABORT_CLEANUP: Reversión de reserva de turno
**Triggered by**: Fallo de base de datos en `STEP 2` o fallo de almacenamiento/envío en `STEP 3`.
**Actions**:
  1. Eliminar el PDF del turno mediante `almacenamiento_service.eliminar_archivo(...)` si ya había sido guardado.
  2. Ejecutar `session.rollback()` liberando el slot `(centro_id, inicio)` en la tabla `turnos` y restaurando `estudios.estado` a su valor previo (`CREADO`, `AUTORIZADO` o `REMUESTREO_REQUERIDO`).
  3. Registrar el error en logs y retornar respuesta HTTP de error con `retryable: true`.
**What customer (`Paciente`) sees**: Mensaje de error indicando que no se pudo completar la reserva del turno y que el horario sigue disponible para reintentar.
**What operator sees**: Log de error; slot liberado en `turnos`.

---

## State Transitions

```
[Estudio en CREADO (con Pago activo) | AUTORIZADO | REMUESTREO_REQUERIDO | TURNO_SACADO (con ausencia previa < 5)]
   |
   |-- (STEP 1 falla: fuera de horario 9-18 L-V, feriado, estudio sin pago/autorización)
   |       --> [Rechazado (403 / 409 / 422), sin cambios en BD]
   |
   |-- (STEP 2 falla: colisión concurrente en uq_turno_activo)
   |       --> [Rechazado (409 Conflict TURNO_OCUPADO), sin cambios en BD]
   |
   |-- (STEP 1-3 tienen éxito)
   |       --> Turno creado (activo = True, asistio = None)
   |       --> Estudio.estado = EstadoEstudio.TURNO_SACADO ("Turno sacado")
   |       --> Orden de extracción + Consentimiento informado + Recordatorio enviados al Paciente
   |
   +-- (STEP 3 falla -> ABORT_CLEANUP)
           --> [Rollback al estado previo del Estudio, slot libre]
```

---

## Handoff Contracts

### 1. Frontend Paciente -> Backend (Consulta de Centros y Disponibilidad)
**Endpoint**: `GET /api/v1/centros-extraccion` y `GET /api/v1/centros-extraccion/{centro_id}/turnos-disponibles?fecha=2026-11-02`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "centro": {
      "id": 14,
      "nombre": "Laboratorio Rossi - Sede Belgrano",
      "direccion": "Av. Cabildo 2040",
      "provincia": "Buenos Aires",
      "latitud": -34.5612,
      "longitud": -58.4567
    },
    "fecha": "2026-11-02",
    "slots_libres": [
      "2026-11-02T09:00:00",
      "2026-11-02T09:15:00",
      "2026-11-02T09:30:00"
    ]
  }
}
```
**Timeout**: `3s`

---

### 2. Frontend Paciente -> Backend (Reserva de Turno)
**Endpoint**: `POST /api/v1/estudios/{estudio_id}/turnos`
**Payload**:
```json
{
  "centro_id": 14,
  "inicio": "2026-11-02T09:15:00"
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "turno_id": 501,
    "estudio_id": 101,
    "paciente_id": 42,
    "centro_id": 14,
    "inicio": "2026-11-02T09:15:00",
    "duracion_minutos": 15,
    "activo": true,
    "estado_estudio": "Turno sacado",
    "ausencias_acumuladas": 0,
    "max_ausencias": 5,
    "consentimiento_pdf_url": "/api/v1/turnos/501/consentimiento-pdf",
    "documentacion_enviada": {
      "orden_extraccion": true,
      "consentimiento_informado": true,
      "recordatorio": true,
      "canal_pdf": "app",
      "pdf_url": "/api/v1/turnos/501/consentimiento-pdf"
    }
  }
}
```
**Failure response** (`403` / `404` / `409` / `422` / `502`):
```json
{
  "ok": false,
  "error": "El turno seleccionado acaba de ser ocupado por otro paciente. Por favor elija otro horario.",
  "code": "TURNO_OCUPADO",
  "retryable": false
}
```
**Timeout**: `10s`
**ON FAILURE**: Rollback transaccional mediante `ABORT_CLEANUP`.

---

### 3. Frontend Paciente -> Backend (Descarga de Orden y Consentimiento PDF)
**Endpoint**: `GET /api/v1/turnos/{turno_id}/consentimiento-pdf` (autenticado con rol `paciente` titular del turno)
**Success response** (`200 OK`, `Content-Type: application/pdf`): binario PDF con `Content-Disposition: attachment; filename="orden_consentimiento_turno_{turno_id}.pdf"` (regenerado bajo demanda si no existiera en almacenamiento).
**Failure response**: `401` / `403` (`FORBIDDEN_NOT_OWNER`) / `404` (`RECURSO_NO_ENCONTRADO`).

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Registro en `turnos` (`activo = True`) | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Cambio de `estudios.estado` a `TURNO_SACADO` | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Archivo `storage/turnos/orden_consentimiento_turno_{turno_id}.pdf` | STEP 3 | `ABORT_CLEANUP` | `almacenamiento_service.eliminar_archivo(...)` |
| Registros en `avisos` (`APP` y `MAIL`) | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/turnos.py`, `Turno` define el índice parcial único `Index("uq_turno_activo", "centro_id", "inicio", unique=True, sqlite_where=text("activo"), postgresql_where=text("activo"))`. Esto garantiza en PostgreSQL y SQLite (tests) que no puedan existir dos turnos activos en el mismo centro y horario, pero permite reutilizar el slot si el turno anterior fue cancelado (`activo = False`). | Low | STEP 2 | Aprovechado directamente en STEP 2 para control de concurrencia. |
| RC-2 | En lugar de adjuntar la `Orden de extracción` y el `Consentimiento informado` por correo electrónico, el archivo PDF se genera y persiste en `almacenamiento_service` asociado al `Turno` (`storage/turnos/orden_consentimiento_turno_{turno_id}.pdf`) sin alterar el esquema de tablas PostgreSQL, se notifica en la aplicación mediante `CanalAviso.APP` y queda disponible para descargar en cualquier momento. | Low | STEP 3 | Implementado mediante `pdf_consentimiento.py`, `almacenamiento_service` y `GET /api/v1/turnos/{turno_id}/consentimiento-pdf`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path reserva de turno en estudio Autorizado** | `POST /api/v1/estudios/{id}/turnos` en día hábil a las `10:15:00` para un estudio en `EstadoEstudio.AUTORIZADO`. | Retorna `201 Created`; crea `Turno` (`activo=True`, `asistio=None`); cambia `Estudio.estado` a `EstadoEstudio.TURNO_SACADO`; guarda PDF en `storage/turnos/orden_consentimiento_turno_{id}.pdf`, emite `Aviso(CanalAviso.APP)` y envía `Recordatorio` por correo. |
| **TC-02: Happy path reserva de turno en estudio Creado con pago particular activo** | `POST /api/v1/estudios/{id}/turnos` para un estudio en `Creado` que tiene `Pago` con `anulado == False`. | Retorna `201 Created`; `Estudio.estado` pasa a `EstadoEstudio.TURNO_SACADO`. |
| **TC-03: Happy path reserva de turno en estado Remuestreo requerido (sin nuevo pago)** | `POST /api/v1/estudios/{id}/turnos` para un estudio en `EstadoEstudio.REMUESTREO_REQUERIDO`. | Retorna `201 Created`; `Estudio.estado` pasa a `EstadoEstudio.TURNO_SACADO` sin exigir nuevo pago. |
| **TC-04: Colisión concurrente en el mismo centro y horario** | Dos pacientes solicitan simultáneamente `centro_id = 14` e `inicio = "2026-11-02T09:15:00"`. | El primero recibe `201 Created`; el segundo recibe `409 Conflict` (`code: "TURNO_OCUPADO"`) gracias a `uq_turno_activo`. |
| **TC-05: Rechazo por horario fuera de franja (antes de las 9, después de las 18, fin de semana o feriado)** | `POST /api/v1/estudios/{id}/turnos` un sábado, un feriado o a las `18:30:00` o `09:07:00`. | Retorna `422 Unprocessable Entity` (`code: "HORARIO_TURNO_INVALIDO"`); 0 filas creadas en `turnos`. |
| **TC-06: Rechazo por estudio impago / no autorizado** | `POST /api/v1/estudios/{id}/turnos` en un estudio en `Creado` sin `Pago` o en `Pendiente de autorización` o `Rechazado`. | Retorna `409 Conflict` (`code: "ESTUDIO_NO_HABILITADO_TURNO"`). |
| **TC-07: Descarga de Orden y Consentimiento PDF del turno** | `GET /api/v1/turnos/{turno_id}/consentimiento-pdf` autenticado como el paciente titular (o regeneración si faltara el archivo). | Retorna `200 OK` con `Content-Type: application/pdf` y binario `%PDF-`; `403` para otro paciente; `404` para turno inexistente. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El último turno de 15 minutos del horario de 09:00 a 18:00 inicia a las `17:45:00` y finaliza a las `18:00:00`. | `.ai/2-Glosario_LEL.md` (`Objeto: Turno`: *"Horario de 15 minutos en un centro de extracción para una sola persona, de lunes a viernes de 9 a 18, salvo feriados"*). | Bajo. |

## Open Questions

- ¿El calendario de feriados nacionales se consulta desde una tabla/configuración local o librería estándar de feriados de Argentina (`holidays`)? *(Se recomienda parametrizarlo en el servicio de turnos para facilitar el testing determinístico en `pytest`).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/turnos.py` y `estudios.py`. | Marcada como `Approved`. |
| 2026-11-17 | Adaptación v1.1 por Requerimientos 1 y 6: habilitación con `Pago.estado in (PAGADO, PARCIAL)` (cuota #1 abonada en MercadoPago) y registro en `registro_modificaciones` al pasar a `TURNO_SACADO`. | Especificación actualizada (ver ADR-001 y ADR-003). |
| 2026-11-25 | Adaptación v1.2: generación y guardado de Orden de extracción y Consentimiento informado PDF asociado al `Turno`, emisión de `Aviso(CanalAviso.APP)` para descargarlo en la app y endpoint `GET /api/v1/turnos/{turno_id}/consentimiento-pdf`. | Especificación actualizada. |
