# WORKFLOW: Escenario 7 – Solicitar un turno de extracción
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-7`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Paciente` |
| **Objetos** | `Estudio`, `Centro de extracción`, `Turno`, `Orden de extracción`, `Consentimiento informado`, `Recordatorio`, `Presupuesto`, `Aviso` |
| **Verbos** | `Sacar turno` |
| **Estados** | `Creado`, `Autorizado`, `Remuestreo requerido`, `Turno sacado` |

---

## Overview

- **Objetivo**: Asignar un `Turno` de extracción de sangre de 15 minutos en uno de los 100 `Centros de extracción` del país para un `Paciente` cuyo `Estudio` está autorizado o pagado (o en remuestreo sin costo), cambiar el `Estudio` al estado `Turno sacado` y enviar al `Paciente` la `Orden de extracción`, el `Consentimiento informado` y el `Recordatorio`.
- **Contexto**: El `Estudio` ya fue `Autorizado` por la `Obra social` (Escenarios 4 o 5), o fue abonado de forma particular teniendo un `Pago` activo en estado `Creado` (Escenario 6), o requiere una nueva muestra sin costo por estar en `Remuestreo requerido` (Escenario 10), o el `Paciente` faltó de 1 a 4 veces a un turno previo (`ausencias < 5`, Escenario 33) y necesita reservar un nuevo `Turno`. Los `Turnos` son de 15 minutos, para una sola persona por centro y horario, de lunes a viernes de 09:00 a 18:00, excluyendo feriados.
- **Recursos**: Mapa de `Centros de extracción` (`centros_extraccion`), agenda de `Turnos` (`turnos`), `Orden de extracción` (PDF/adjunto), plantilla de `Consentimiento informado` (PDF/adjunto que no se guarda en el sistema), `Recordatorio` por mail (con fecha, hora y advertencia del límite de `MAX_AUSENCIAS = 5` ausencias).
- **Episodios**:
  1. El `Paciente` consulta los `Centros de extracción` disponibles en el mapa.
  2. El sistema muestra los `Centros de extracción` con sus coordenadas (`latitud`, `longitud`) y sus `Turnos` libres de 15 minutos (lunes a viernes de 09:00 a 18:00, sin feriados).
  3. El `Paciente` selecciona un `Centro de extracción`.
  4. El `Paciente` selecciona un `Turno` libre (`inicio`).
  5. El sistema registra el `Turno` (`activo = True`), pasa el `Estudio` al estado `Turno sacado` (`EstadoEstudio.TURNO_SACADO`) y envía por mail al `Paciente` la `Orden de extracción`, el `Consentimiento informado` y el `Recordatorio`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` | Sujeto LEL que visualiza el mapa de `Centros de extracción`, elige un `Turno` libre y recibe la documentación para asistir a la extracción. |
| `router` (`turnos_router`) | Capa HTTP Flask (`GET /api/v1/centros-extraccion`, `GET /api/v1/centros-extraccion/{centro_id}/disponibilidad` y `POST /api/v1/estudios/{estudio_id}/turnos`). |
| `service` (`turno_service`) | Capa de negocio que valida horarios hábiles (lunes a viernes 09:00–18:00, múltiplos de 15 min, no feriado), verifica habilitación económica/estado del `Estudio`, crea el `Turno` y dispara el envío de documentos. |
| `repo` (`turno_repo`, `estudio_repo`, `usuario_repo`) | Capa de acceso a datos SQLAlchemy sobre `centros_extraccion`, `turnos`, `estudios`, `pagos`, `avisos`. |
| `clients` (`notificacion_client`) | Cliente de correo y generación de adjuntos para enviar la `Orden de extracción`, el `Consentimiento informado` y el `Recordatorio`. |
| `PostgreSQL` | Base de datos relacional que garantiza exclusión mutua del slot mediante el índice parcial único `uq_turno_activo` (`centro_id`, `inicio` donde `activo = True`). |

---

## Prerequisites

- El usuario autenticado tiene `Usuario.rol == Rol.PACIENTE`, `debe_cambiar_password == False` y es titular del `Estudio` (`estudio.paciente.usuario_id == usuario_actual.id`).
- El `Centro de extracción` (`centros_extraccion.id == centro_id`) existe en la base de datos.
- El `Estudio` (`estudios.id == estudio_id`) cumple **una** de las siguientes condiciones de habilitación:
  1. `estudio.estado == EstadoEstudio.AUTORIZADO`, **o**
  2. `estudio.estado == EstadoEstudio.CREADO` y posee un `Pago` con `anulado == False` en `estudio.presupuesto.pagos`, **o**
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
2. Carga el `Estudio` con `SELECT ... FOR UPDATE` y verifica que esté habilitado para sacar turno (`AUTORIZADO`, `CREADO` con pago vigente `anulado == False`, `REMUESTREO_REQUERIDO`, o `TURNO_SACADO` tras ausencia con `ausencias < 5` y sin turno activo pendiente).
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
2. Actualiza `estudio.estado = EstadoEstudio.TURNO_SACADO` (`"Turno sacado"`).
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

### STEP 3: Envío de `Orden de extracción`, `Consentimiento informado` y `Recordatorio` al `Paciente`
**Actor**: `service` (`turno_service`) -> `repo` (`usuario_repo`) + `clients` (`notificacion_client`)
**Action**:
1. Genera en memoria (sin guardar el consentimiento en la base de datos, tal como exige `.ai/2-Glosario_LEL.md` en `Objeto: Consentimiento informado`):
   - **Orden de extracción**: Documento con fecha, hora (`inicio`), nombre y dirección del `Centro de extracción`, datos del `Paciente` y aclaración de que **no requiere ayuno ni preparación especial**.
   - **Consentimiento informado**: Plantilla oficial para que el `Paciente` (o su padre/responsable si es menor de edad) imprima, complete, firme y entregue en el `Centro de extracción`.
   - **Recordatorio**: Mensaje de correo electrónico con la fecha y hora del `Turno` y la advertencia expresa de que el límite máximo de inasistencias es de **5 ausencias** (`MAX_AUSENCIAS = 5`), tras lo cual perderá el pago.
2. Inserta un `Aviso` en la tabla `avisos` (`usuario_id = estudio.paciente.usuario_id`, `canal = CanalAviso.MAIL`, `mensaje = f"Turno reservado para el {inicio} en {centro.nombre}. Recuerde que al acumular 5 ausencias perderá el pago del estudio."`).
3. Envía el correo electrónico con la `Orden de extracción`, el `Consentimiento informado` y el `Recordatorio`, marca `avisos.enviado = True`, `avisos.enviado_en = func.now()` y hace `session.commit()`.
**Timeout**: `6s` (con 2 reintentos de `1s` y `2s` para el despacho de correo).
**Input**: `Turno`, `Estudio`, `CentroExtraccion`, `Paciente`.
**Output on SUCCESS**: Respuesta `201 Created` con los datos del `Turno` y confirmación de envío -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(transient_mail_error)`: Si el servidor SMTP falla tras los 2 reintentos -> `GO TO ABORT_CLEANUP` (o si se configura cola asíncrona, mantener `avisos.enviado = False`; por defecto en flujo síncrono hace rollback y devuelve `502 Bad Gateway` con `retryable: true` para garantizar que el paciente reciba la `Orden de extracción` y el `Consentimiento informado`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Confirmación `"Turno reservado con éxito"` mostrando fecha, hora, dirección del `Centro de extracción` en el mapa y aviso de que se enviaron a su correo la `Orden de extracción`, el `Consentimiento informado` y el `Recordatorio`.
  - **Operator sees**: `Estudio` en estado `Turno sacado` con turno activo.
  - **Database**: `turnos` (`activo = True`), `estudios` (`estado = EstadoEstudio.TURNO_SACADO`), `avisos` (`enviado = True`). *(El `Consentimiento informado` NO se almacena en la base de datos).*
  - **Logs**: `[turno_service] STEP 3 completado turno_id=<tid> documentos_enviados=True`

---

### ABORT_CLEANUP: Reversión de reserva de turno
**Triggered by**: Fallo de base de datos en `STEP 2` o fallo definitivo de envío de documentación en `STEP 3`.
**Actions**:
  1. Ejecutar `session.rollback()` liberando el slot `(centro_id, inicio)` en la tabla `turnos` y restaurando `estudios.estado` a su valor previo (`CREADO`, `AUTORIZADO` o `REMUESTREO_REQUERIDO`).
  2. Registrar el error en logs y retornar respuesta HTTP de error con `retryable: true`.
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
    "documentacion_enviada": {
      "orden_extraccion": true,
      "consentimiento_informado": true,
      "recordatorio": true
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

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Registro en `turnos` (`activo = True`) | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Cambio de `estudios.estado` a `TURNO_SACADO` | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Registro en `avisos` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/turnos.py`, `Turno` define el índice parcial único `Index("uq_turno_activo", "centro_id", "inicio", unique=True, sqlite_where=text("activo"), postgresql_where=text("activo"))`. Esto garantiza en PostgreSQL y SQLite (tests) que no puedan existir dos turnos activos en el mismo centro y horario, pero permite reutilizar el slot si el turno anterior fue cancelado (`activo = False`). | Low | STEP 2 | Aprovechado directamente en STEP 2 para control de concurrencia. |
| RC-2 | Según `.ai/2-Glosario_LEL.md` (`Objeto: Consentimiento informado`), el consentimiento informado se envía al paciente al sacar turno pero *"se gestiona fuera del sistema y no se guarda en él"*. En `app/src/core/models/` efectivamente no existe columna ni tabla para guardar el consentimiento informado. | Low | STEP 3 | Documentado explícitamente que se genera y adjunta al mail sin persistirse en BD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path reserva de turno en estudio Autorizado** | `POST /api/v1/estudios/{id}/turnos` en día hábil a las `10:15:00` para un estudio en `EstadoEstudio.AUTORIZADO`. | Retorna `201 Created`; crea `Turno` (`activo=True`, `asistio=None`); cambia `Estudio.estado` a `EstadoEstudio.TURNO_SACADO`; envía `Orden de extracción`, `Consentimiento informado` y `Recordatorio`. |
| **TC-02: Happy path reserva de turno en estudio Creado con pago particular activo** | `POST /api/v1/estudios/{id}/turnos` para un estudio en `Creado` que tiene `Pago` con `anulado == False`. | Retorna `201 Created`; `Estudio.estado` pasa a `EstadoEstudio.TURNO_SACADO`. |
| **TC-03: Happy path reserva de turno en estado Remuestreo requerido (sin nuevo pago)** | `POST /api/v1/estudios/{id}/turnos` para un estudio en `EstadoEstudio.REMUESTREO_REQUERIDO`. | Retorna `201 Created`; `Estudio.estado` pasa a `EstadoEstudio.TURNO_SACADO` sin exigir nuevo pago. |
| **TC-04: Colisión concurrente en el mismo centro y horario** | Dos pacientes solicitan simultáneamente `centro_id = 14` e `inicio = "2026-11-02T09:15:00"`. | El primero recibe `201 Created`; el segundo recibe `409 Conflict` (`code: "TURNO_OCUPADO"`) gracias a `uq_turno_activo`. |
| **TC-05: Rechazo por horario fuera de franja (antes de las 9, después de las 18, fin de semana o feriado)** | `POST /api/v1/estudios/{id}/turnos` un sábado, un feriado o a las `18:30:00` o `09:07:00`. | Retorna `422 Unprocessable Entity` (`code: "HORARIO_TURNO_INVALIDO"`); 0 filas creadas en `turnos`. |
| **TC-06: Rechazo por estudio impago / no autorizado** | `POST /api/v1/estudios/{id}/turnos` en un estudio en `Creado` sin `Pago` o en `Pendiente de autorización` o `Rechazado`. | Retorna `409 Conflict` (`code: "ESTUDIO_NO_HABILITADO_TURNO"`). |

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
