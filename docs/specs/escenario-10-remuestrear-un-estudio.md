# WORKFLOW: Escenario 10 – Remuestrear un estudio
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-10-Remuestrear-un-estudio`

## Símbolos LEL utilizados

| Categoría | Símbolo LEL | Modelo / Tabla en `app/src/core/models/` |
|---|---|---|
| **Sujeto** | `Administrativo` | `Usuario` (`Rol.ADMINISTRATIVO`) en `usuarios` |
| **Sujeto** | `Paciente` | `Paciente` en `pacientes` / `Usuario` (`Rol.PACIENTE`) |
| **Sujeto** | `Médico` | `Medico` en `medicos` / `Usuario` (`Rol.MEDICO`, `Rol.GERENTE_MEDICO`) |
| **Objeto** | `Estudio` | `Estudio` en `estudios` |
| **Objeto** | `Muestra` | `Muestra` en `muestras` (`MotivoDescarte`, `ML_MINIMOS_TUBO`) |
| **Objeto** | `Turno` | `Turno` en `turnos` |
| **Objeto** | `Centro de extracción` | `CentroExtraccion` en `centros_extraccion` |
| **Objeto** | `Orden de extracción` | Documento PDF/adjunto emitido al `Sacar turno` |
| **Objeto** | `Consentimiento informado` | Documento PDF adjunto emitido al `Sacar turno` |
| **Objeto** | `Recordatorio` | Notificación enviada por `CanalAviso.MAIL` al `Sacar turno` |
| **Objeto** | `Aviso` | `Aviso` en `avisos` (`CanalAviso.APP`, `CanalAviso.MAIL`) |
| **Objeto** | `Bot de Telegram` | Webhook receptor de toma de muestra en `Centro de extracción` |
| **Verbo** | `Remuestrear` | Servicio `remuestrear_estudio` (`service` -> `repo`) |
| **Verbo** | `Sacar turno` | Servicio `sacar_turno_extraccion` sin requerir nuevo pago |
| **Estado** | `En laboratorio central` | `EstadoEstudio.EN_LAB_CENTRAL` (`"En laboratorio central"`) |
| **Estado** | `En espera de retiro` | `EstadoEstudio.EN_ESPERA_RETIRO` (`"En espera de retiro"`) |
| **Estado** | `En viaje a Corea` | `EstadoEstudio.EN_VIAJE_COREA` (`"En viaje a Corea"`) |
| **Estado** | `Remuestreo requerido` | `EstadoEstudio.REMUESTREO_REQUERIDO` (`"Remuestreo requerido"`) |
| **Estado** | `Turno sacado` | `EstadoEstudio.TURNO_SACADO` (`"Turno sacado"`) |
| **Estado** | `Lista para retirar` | `EstadoEstudio.LISTA_PARA_RETIRAR` (`"Lista para retirar"`) |

---

## Overview

- **Objetivo**: Obtener una nueva `Muestra` de sangre para el mismo `Estudio`, sin costo adicional para el `Paciente`, cuando la `Muestra` original no puede ser procesada.
- **Contexto**: La `Muestra` recibida en el laboratorio central presenta un volumen menor a 2 mililitros (`MotivoDescarte.VOLUMEN_INSUFICIENTE`, `< ML_MINIMOS_TUBO`), se encuentra desnaturalizada por mala conservación (`MotivoDescarte.DESNATURALIZADA`) o presenta ADN insuficiente al intentarse su procesamiento (`MotivoDescarte.ADN_INSUFICIENTE`).
- **Recursos**: `Muestra` (`muestras`), `Turno` (`turnos`), `Estudio` (`estudios`), `Aviso` (`avisos`).
- **Episodios**:
  1. El laboratorio detecta que la `Muestra` no puede ser procesada y registra el motivo de descarte.
  2. El `Paciente` recibe la notificación (`Aviso` y correo electrónico) de la necesidad de una nueva `Muestra` sin cargo.
  3. El `Médico` tratante recibe la notificación correspondiente.
  4. El `Paciente` solicita un nuevo `Turno` en un `Centro de extracción` para el mismo `Estudio`.
  5. El `Paciente` realiza una nueva extracción y el `Centro de extracción` informa la toma mediante el `Bot de Telegram`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Administrativo` | Registra que la `Muestra` vigente del `Estudio` es inválida (por volumen `< 2 ml`, ADN insuficiente o muestra desnaturalizada). |
| `Paciente` | Recibe el `Aviso` de `Remuestreo requerido`, reserva un nuevo `Turno` sin abonar nuevamente y asiste al `Centro de extracción`. |
| `Médico` | Recibe el `Aviso` informativo de que el `Estudio` de su `Paciente` retrocedió a `Remuestreo requerido`. |
| `Centro de extracción` / `Bot de Telegram` | Informa al sistema que se extrajo la nueva `Muestra` del `Paciente`. |
| Capa `router` (`Flask Blueprint`) | Valida autenticación JWT/sesión, rol y esquema del payload; delega a `service`. |
| Capa `service` (`EstudioService` / `LogisticaService` / `TurnoService`) | Ejecuta las reglas de negocio de `Remuestrear`, descarte de `Muestra`, transición de `EstadoEstudio` y despacho de `Aviso`s. |
| Capa `repo` (`EstudioRepo`, `MuestraRepo`, `TurnoRepo`, `AvisoRepo`) | Ejecuta las consultas y escrituras transaccionales en `PostgreSQL` vía `SQLAlchemy`. |
| Capa `clients` (`MailClient`, `TelegramWebhookHandler`) | Envía los correos electrónicos a `Paciente` y `Médico` y procesa el mensaje entrante del `Bot de Telegram`. |

---

## Prerequisites

- Existe un usuario autenticado con `Rol.ADMINISTRATIVO` en la tabla `usuarios` para iniciar el descarte de la muestra.
- Existe un registro `Estudio` en la tabla `estudios` cuyo `estado` actual es `EstadoEstudio.EN_LAB_CENTRAL`, `EstadoEstudio.EN_ESPERA_RETIRO` o `EstadoEstudio.EN_VIAJE_COREA`.
- El `Estudio` posee una `muestra_vigente` en la tabla `muestras` (`motivo_descarte IS NULL`).
- El `Paciente` (`pacientes.id == estudio.paciente_id`) y el `Médico` (`medicos.id == estudio.medico_id`) tienen usuarios activos asociados en `usuarios`.
- El `Estudio` ya cuenta con su `Presupuesto` pagado o su `Autorizacion` aprobada; el remuestreo no altera ni anula pagos previos en `pagos`.

---

## Trigger

1. **Inicio del remuestreo**: El `Administrativo` invoca `POST /api/estudios/{estudio_id}/remuestrear` indicando el `motivo_descarte` (`volumen_insuficiente`, `adn_insuficiente` o `desnaturalizada`) y opcionalmente los `mililitros` medidos en el tubo (o se dispara automáticamente cuando al registrar los mililitros del tubo en el laboratorio central el valor es `< 2.00`).
2. **Reserva de nuevo turno**: El `Paciente` invoca `POST /api/estudios/{estudio_id}/turnos` con `centro_id` e `inicio`.
3. **Toma de nueva muestra**: El `Centro de extracción` envía confirmación al `Bot de Telegram` (`POST /api/webhooks/telegram/muestra-tomada`).

---

## Workflow Tree

### STEP 1: Validación de solicitud de remuestreo y bloqueo del estudio
**Actor**: `router` -> `service` (`LogisticaService.solicitar_remuestreo`) -> `repo` (`EstudioRepo`, `MuestraRepo`)
**Action**: Verifica que el usuario tenga `Rol.ADMINISTRATIVO`, bloquea la fila del `Estudio` (`SELECT ... FOR UPDATE`), comprueba que `estudio.estado` admita remuestreo (`EN_LAB_CENTRAL`, `EN_ESPERA_RETIRO` o `EN_VIAJE_COREA`), que exista `estudio.muestra_vigente` y que el `motivo_descarte` pertenezca al enum `MotivoDescarte` (si se informan `mililitros < 2.00`, fuerza o valida `MotivoDescarte.VOLUMEN_INSUFICIENTE`).
**Timeout**: 3s
**Input**:
```json
{
  "estudio_id": 42,
  "motivo_descarte": "volumen_insuficiente | adn_insuficiente | desnaturalizada",
  "mililitros": "1.50"
}
```
**Output on SUCCESS**: Contexto validado `{ estudio, muestra_vigente }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario autenticado no tiene `Rol.ADMINISTRATIVO` -> retornar HTTP `403 Forbidden`, sin cambios en base de datos.
  - `FAILURE(not_found)`: No existe `Estudio` con `id = estudio_id` -> retornar HTTP `404 Not Found`.
  - `FAILURE(validation_error)`: `motivo_descarte` no es un valor válido de `MotivoDescarte`, o `motivo_descarte == "volumen_insuficiente"` pero `mililitros >= 2.00` (`ML_MINIMOS_TUBO`) -> retornar HTTP `400 Bad Request` con detalle del campo inválido.
  - `FAILURE(invalid_state)`: `estudio.estado` no está en `{EN_LAB_CENTRAL, EN_ESPERA_RETIRO, EN_VIAJE_COREA}` o `estudio.muestra_vigente` es `None` -> retornar HTTP `409 Conflict` (`code: "ESTUDIO_ESTADO_INVALIDO_PARA_REMUESTREO"`).
  - `FAILURE(conflict)`: Otra transacción ya descartó la muestra simultáneamente (`estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO`) -> retornar HTTP `409 Conflict` (`code: "MUESTRA_YA_DESCARTADA"`).
  - `FAILURE(timeout)`: Bloqueo en `PostgreSQL` supera 3s -> reintentar lectura 1 vez con backoff de 500ms; si persiste, retornar HTTP `503 Service Unavailable`.

**Observable states during this step**:
  - Customer/Actor (`Administrativo`) sees: Indicador `"Procesando solicitud de remuestreo..."`.
  - Operator sees: `Estudio` aún en su estado previo (`En laboratorio central` / `En viaje a Corea`).
  - Database: `SELECT ... FOR UPDATE` activo sobre `estudios.id = 42` y `muestras.id = muestra_vigente.id`.
  - Logs: `[logistica_service] validando_remuestreo estudio_id=42 usuario_id=7 motivo=volumen_insuficiente ml=1.50`

---

### STEP 2: Descarte de la muestra inválida y retroceso de estado a `Remuestreo requerido`
**Actor**: `service` -> `repo` (`MuestraRepo`, `EstudioRepo`, `TurnoRepo`) -> `PostgreSQL`
**Action**: En una única transacción de base de datos:
1. Actualiza la `Muestra` vigente en `muestras`: asigna `muestra.motivo_descarte = MotivoDescarte(motivo_descarte)`, actualiza `muestra.mililitros` si fue provisto, y si la muestra estaba vinculada a un `SampleSet` en estado `EstadoSampleSet.ABIERTO`, limpia `muestra.sample_set_id = None` para liberar el cupo en el lote abierto.
2. Si existe algún `Turno` activo previo en `turnos` para ese `estudio_id`, asegura `turno.activo = False`.
3. Actualiza `estudio.estado = EstadoEstudio.REMUESTREO_REQUERIDO` (sin incrementar `estudio.ausencias` ni alterar `pagos`).
4. Crea dos registros `Aviso` en la tabla `avisos` (`CanalAviso.APP` y `CanalAviso.MAIL` pendientes de envío) dirigidos a `estudio.paciente.usuario_id` y a `estudio.medico.usuario_id`.
**Timeout**: 5s
**Input**: `{ estudio, muestra_vigente, motivo_descarte, mililitros }`
**Output on SUCCESS**: `{ estudio_id, muestra_descartada_id, nuevo_estado: "Remuestreo requerido", avisos_ids }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(database_error)`: Error de integridad o conexión al actualizar `muestras` / `estudios` -> rollback automático de la transacción SQLAlchemy -> GO TO `ABORT_CLEANUP`.
  - `FAILURE(timeout)`: Commit supera 5s -> rollback transaccional y retornar HTTP `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Administrativo`) sees: `"Actualizando estado del estudio a Remuestreo requerido..."`.
  - Operator sees: `estudio.estado = "Remuestreo requerido"`, `estudio.muestra_vigente = None`.
  - Database:
    - Tabla `muestras`: `motivo_descarte = 'volumen_insuficiente' | 'adn_insuficiente' | 'desnaturalizada'`, `mililitros = 1.50`, `sample_set_id = NULL` (si el `SampleSet` estaba `ABIERTO`).
    - Tabla `estudios`: `estado = 'Remuestreo requerido'`, `updated_at = now()`.
    - Tabla `avisos`: 2 filas insertadas con `leido = False`, `enviado = False`.
  - Logs: `[logistica_service] muestra_descartada estudio_id=42 muestra_id=108 estado="Remuestreo requerido"`

---

### STEP 3: Notificación por correo electrónico y aviso en plataforma al Paciente y al Médico
**Actor**: `service` -> `clients` (`MailClient`) -> `repo` (`AvisoRepo`)
**Action**: Envía correo electrónico al `Paciente` (`estudio.paciente.usuario.email`) y al `Médico` tratante (`estudio.medico.usuario.email`) informando que la muestra no pudo ser procesada, que el `Estudio` pasó a `Remuestreo requerido` y que el `Paciente` puede reservar un nuevo `Turno` sin costo. Al confirmarse el despacho SMTP, marca `aviso.enviado = True` y `aviso.enviado_en = now()` en la tabla `avisos`.
**Timeout**: 10s
**Input**: `{ estudio_id, paciente_email, medico_email, motivo_descarte, avisos_ids }`
**Output on SUCCESS**: `{ notificaciones_enviadas: true }` -> Retorna HTTP `200 OK` al `Administrativo`; el flujo aguarda la acción del `Paciente` en STEP 4.
**Output on FAILURE**:
  - `FAILURE(transient_smtp_error)`: Timeout o error 5xx del servidor de correo -> reintentar hasta 3 veces con backoff exponencial (1s, 2s, 4s).
  - `FAILURE(permanent_smtp_error)`: Si tras los 3 reintentos el envío de mail falla, **no se revierte** el estado `Remuestreo requerido` del `Estudio` (el descarte físico de la muestra ya ocurrió); se mantiene `aviso.enviado = False` en `avisos` para reintento en background, el `Aviso` interno en la app sigue visible (`leido = False`) y se retorna HTTP `200 OK` con `warning: "AVISO_MAIL_PENDIENTE"`.

**Observable states during this step**:
  - Customer/Actor (`Paciente` y `Médico`) sees: Nuevo `Aviso` en su bandeja del sistema y correo electrónico recibido; el `Paciente` ve habilitado el botón `"Sacar nuevo turno (sin cargo)"`.
  - Operator (`Administrativo`) sees: Confirmación `"Estudio #42 en estado Remuestreo requerido. Paciente y médico notificados."`.
  - Database: Tabla `avisos` con `enviado = True`, `enviado_en = <timestamp>`.
  - Logs: `[mail_client] notificacion_remuestreo_enviada estudio_id=42 paciente_id=15 medico_id=4`

---

### STEP 4: Reserva de nuevo turno de extracción sin cargo por el Paciente
**Actor**: `Paciente` -> `router` -> `service` (`TurnoService.sacar_turno`) -> `repo` (`TurnoRepo`, `EstudioRepo`, `AvisoRepo`)
**Action**: El `Paciente` autenticado consulta los `Centro de extracción` en el mapa y selecciona un horario libre de 15 minutos (lunes a viernes de 09:00 a 18:00, no feriado). El sistema verifica que `estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO` (lo cual lo exime de validar un nuevo pago, reutilizando el pago/autorización original vigente), inserta la nueva fila en `turnos` (`activo = True`, `asistio = None`), cambia `estudio.estado = EstadoEstudio.TURNO_SACADO` y envía al `Paciente` la `Orden de extracción`, el `Consentimiento informado` y el `Recordatorio` (indicando fecha, hora y el límite de `MAX_AUSENCIAS = 5`).
**Timeout**: 5s
**Input**:
```json
{
  "estudio_id": 42,
  "centro_id": 12,
  "inicio": "2026-11-02T10:15:00"
}
```
**Output on SUCCESS**: `{ turno_id: 305, estado_estudio: "Turno sacado" }` -> GO TO STEP 5
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no es el `Paciente` titular del `Estudio` -> retornar HTTP `403 Forbidden`.
  - `FAILURE(invalid_state)`: `estudio.estado` no está en `{AUTORIZADO, CREADO (con pago vigente), REMUESTREO_REQUERIDO}` -> retornar HTTP `409 Conflict`.
  - `FAILURE(validation_error)`: El horario `inicio` no es múltiplo de 15 minutos, cae fuera de lunes a viernes 09:00–18:00 o es feriado -> retornar HTTP `400 Bad Request` (`code: "HORARIO_TURNO_INVALIDO"`).
  - `FAILURE(conflict)`: Violación del índice único `uq_turno_activo` (`centro_id`, `inicio` con `activo = True`) porque otro paciente reservó el mismo slot simultáneamente -> retornar HTTP `409 Conflict` (`code: "TURNO_NO_DISPONIBLE"`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: Confirmación del nuevo `Turno`, descarga/recepción de `Orden de extracción`, `Consentimiento informado` y `Recordatorio`.
  - Operator sees: `Estudio` en estado `Turno sacado`.
  - Database:
    - Tabla `turnos`: Nueva fila con `estudio_id = 42`, `centro_id = 12`, `inicio = '2026-11-02 10:15:00'`, `activo = True`, `asistio = NULL`.
    - Tabla `estudios`: `estado = 'Turno sacado'`.
    - Tabla `pagos`: Sin cargos nuevos (se mantiene intacto el pago/autorización original).
  - Logs: `[turno_service] turno_remuestreo_creado estudio_id=42 turno_id=305 centro_id=12`

---

### STEP 5: Nueva extracción y aviso del Centro de extracción vía Bot de Telegram
**Actor**: `Centro de extracción` -> `Bot de Telegram` -> `router` (`POST /api/webhooks/telegram/muestra-tomada`) -> `service` -> `repo`
**Action**: Cuando el `Paciente` concurre al `Centro de extracción` y se realiza la nueva extracción, el `Centro de extracción` envía el mensaje al `Bot de Telegram`. El sistema valida el token del webhook y el `turno_id` / `estudio_id`, marca `turno.asistio = True` en `turnos`, inserta una **nueva fila** en la tabla `muestras` (`estudio_id = 42`, `turno_id = 305`, `tomada_en = now()`, `motivo_descarte = None`) que pasa a ser la nueva `estudio.muestra_vigente` (conservando la fila anterior descartada para trazabilidad histórica), y actualiza `estudio.estado = EstadoEstudio.LISTA_PARA_RETIRAR`.
**Timeout**: 5s
**Input**:
```json
{
  "estudio_id": 42,
  "turno_id": 305,
  "tomada_en": "2026-11-02T10:20:00"
}
```
**Output on SUCCESS**: `{ muestra_id: 149, estado_estudio: "Lista para retirar" }` -> FIN DEL WORKFLOW (continúa en Escenario 11: Transportar muestras al laboratorio central).
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Token/secreto del webhook de `Bot de Telegram` inválido -> retornar HTTP `401 Unauthorized`.
  - `FAILURE(invalid_state)`: `estudio.estado != EstadoEstudio.TURNO_SACADO` -> retornar HTTP `409 Conflict`.
  - `FAILURE(database_error)`: Fallo al insertar la nueva `Muestra` o actualizar `Estudio` -> rollback transaccional (`ABORT_CLEANUP`) y retornar HTTP `500 Internal Server Error` (`retryable: true` para que el webhook de Telegram reintente).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: Estado de su `Estudio` actualizado a `Lista para retirar`.
  - Operator (`Administrativo` / `Transportista`) sees: Nueva `Muestra` (`id = 149`) en `Lista para retirar` lista para ser incluida en la próxima `Orden del día` del `Transportista`.
  - Database:
    - Tabla `turnos`: `asistio = True` en `turnos.id = 305`.
    - Tabla `muestras`: Se conserva la fila histórica `id = 108` (`motivo_descarte != NULL`) y existe la nueva fila `id = 149` (`motivo_descarte = NULL`, `tomada_en = '2026-11-02 10:20:00'`), por lo que `estudio.muestra_vigente` devuelve la muestra `149`.
    - Tabla `estudios`: `estado = 'Lista para retirar'`.
  - Logs: `[logistica_service] nueva_muestra_registrada estudio_id=42 muestra_id=149 turno_id=305 estado="Lista para retirar"`

---

### ABORT_CLEANUP: Reversión transaccional por fallo en paso intermedio
**Triggered by**: Fallo de base de datos en STEP 2, STEP 4 o STEP 5.
**Actions** (in order):
  1. Ejecutar `session.rollback()` en SQLAlchemy para revertir cualquier escritura parcial en `muestras`, `estudios`, `turnos` o `avisos`.
  2. Asegurar que `estudio.estado` y `muestra.motivo_descarte` conserven el valor exacto previo al intento fallido.
  3. Registrar el error con `estudio_id` y stacktrace en el log de aplicación.
**What customer sees**: Mensaje de error claro indicando que la operación no pudo completarse y que puede reintentarse sin pérdida de datos.
**What operator sees**: El `Estudio` y su `Muestra` permanecen en su estado consistente anterior; alerta en logs de error.

---

## State Transitions

```
Estudio (EstadoEstudio):
[En laboratorio central | En espera de retiro | En viaje a Corea]
  -- (STEP 1-3: muestra inválida descartada con MotivoDescarte) --> [Remuestreo requerido]
[Remuestreo requerido]
  -- (STEP 4: Paciente reserva nuevo Turno sin cargo) ------------> [Turno sacado]
[Turno sacado]
  -- (STEP 5: Bot de Telegram informa extracción de nueva Muestra) -> [Lista para retirar]

Muestra original (muestras):
[motivo_descarte = NULL (vigente)]
  -- (STEP 2: descarte) --> [motivo_descarte = VOLUMEN_INSUFICIENTE | ADN_INSUFICIENTE | DESNATURALIZADA]

Nueva Muestra (muestras):
(inexistente)
  -- (STEP 5: extracción) --> [motivo_descarte = NULL (nueva muestra_vigente)]
```

---

## Handoff Contracts

### 1. `Administrativo (UI)` -> `Backend (router -> service)` (Descartar muestra y solicitar remuestreo)
**Endpoint**: `POST /api/estudios/{estudio_id}/remuestrear`
**Payload**:
```json
{
  "motivo_descarte": "volumen_insuficiente",
  "mililitros": 1.50
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "estudio_id": 42,
  "muestra_descartada_id": 108,
  "motivo_descarte": "volumen_insuficiente",
  "estado_estudio": "Remuestreo requerido",
  "notificaciones_enviadas": true
}
```
**Failure response** (`400` / `403` / `404` / `409` / `503`):
```json
{
  "ok": false,
  "error": "El estudio no se encuentra en un estado válido para remuestreo.",
  "code": "ESTUDIO_ESTADO_INVALIDO_PARA_REMUESTREO",
  "retryable": false
}
```
**Timeout**: 10s
**ON FAILURE**: Rollback de transacción si falló antes del commit; si falló solo el despacho SMTP posterior al commit, mantener estado `Remuestreo requerido` y encolar reintento de correo.

---

### 2. `Paciente (UI)` -> `Backend (router -> service)` (Sacar nuevo turno por remuestreo)
**Endpoint**: `POST /api/estudios/{estudio_id}/turnos`
**Payload**:
```json
{
  "centro_id": 12,
  "inicio": "2026-11-02T10:15:00"
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "turno_id": 305,
  "estudio_id": 42,
  "centro_id": 12,
  "inicio": "2026-11-02T10:15:00",
  "estado_estudio": "Turno sacado",
  "sin_cargo": true
}
```
**Failure response** (`400` / `403` / `409`):
```json
{
  "ok": false,
  "error": "El horario solicitado ya se encuentra ocupado en este centro de extracción.",
  "code": "TURNO_NO_DISPONIBLE",
  "retryable": false
}
```
**Timeout**: 5s
**ON FAILURE**: Rollback de inserción en `turnos`; el `Estudio` permanece en `Remuestreo requerido`.

---

### 3. `Bot de Telegram` -> `Backend (router -> service)` (Confirmación de nueva muestra tomada)
**Endpoint**: `POST /api/webhooks/telegram/muestra-tomada`
**Payload**:
```json
{
  "estudio_id": 42,
  "turno_id": 305,
  "tomada_en": "2026-11-02T10:20:00"
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "estudio_id": 42,
  "muestra_id": 149,
  "estado_estudio": "Lista para retirar"
}
```
**Failure response** (`401` / `404` / `409` / `500`):
```json
{
  "ok": false,
  "error": "El estudio no tiene un turno activo pendiente de extracción.",
  "code": "TURNO_NO_ACTIVO",
  "retryable": false
}
```
**Timeout**: 5s
**ON FAILURE**: Si es error 5xx/timeout, el `Bot de Telegram` reintenta el envío con backoff exponencial.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Actualización de `muestras.motivo_descarte` y `estudios.estado` | Step 2 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Filas de `Aviso` en tabla `avisos` | Step 2 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Nueva fila de `Turno` en tabla `turnos` | Step 4 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Nueva fila de `Muestra` en tabla `muestras` | Step 5 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | Los modelos `Estudio`, `Muestra`, `MotivoDescarte`, `Turno` y `Aviso` ya existen en `app/src/core/models/` y soportan múltiples muestras por estudio mediante la relación `Estudio.muestras` y la propiedad `Estudio.muestra_vigente` (`estudios.py#L50-L52`). | Low | Prerequisites / STEP 2 & 5 | Alineado 100% con el modelo de datos actual: descartar una muestra consiste en setear `muestra.motivo_descarte`, lo que hace que `estudio.muestra_vigente` pase a `None` hasta que se cree la nueva `Muestra` en STEP 5. |
| RC-2 | Si una `Muestra` ya había sido agregada a un `SampleSet` en estado `EstadoSampleSet.ABIERTO` antes de detectarse el descarte en el laboratorio central, mantener `muestra.sample_set_id` ocuparía un lugar inválido en el lote. | High | STEP 2 | Se especificó explícitamente en STEP 2 que al descartar una `Muestra` cuyo `SampleSet` esté `ABIERTO`, se debe desvincular `muestra.sample_set_id = None`. |
| RC-3 | No existen aún los módulos `router`, `service` ni `repo` implementados en `app/src/`. | Medium | Actors / Handoff Contracts | Especificados los contratos y responsabilidades de cada capa para su implementación siguiendo SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path de remuestreo por volumen insuficiente (`< 2 ml`) | `POST /api/estudios/42/remuestrear` con `motivo_descarte="volumen_insuficiente"` y `mililitros=1.50` por un `Administrativo` | HTTP `200 OK`; `muestra.motivo_descarte == MotivoDescarte.VOLUMEN_INSUFICIENTE`, `estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO`, `estudio.muestra_vigente is None`, se crean 2 `Aviso`s (para `Paciente` y `Médico`). |
| `TC-02`: Happy path de remuestreo por ADN insuficiente o muestra desnaturalizada | `POST /api/estudios/42/remuestrear` con `motivo_descarte="adn_insuficiente"` o `"desnaturalizada"` | HTTP `200 OK`; muestra original marcada con el motivo correspondiente y estudio en `EstadoEstudio.REMUESTREO_REQUERIDO`. |
| `TC-03`: Rechazo por volumen suficiente cuando se invoca `volumen_insuficiente` | `POST /api/estudios/42/remuestrear` con `motivo_descarte="volumen_insuficiente"` y `mililitros=2.50` (`>= ML_MINIMOS_TUBO`) | HTTP `400 Bad Request`; no se descarta la muestra ni cambia el estado del estudio. |
| `TC-04`: Rechazo por rol no autorizado | `POST /api/estudios/42/remuestrear` invocado por un `Médico` o `Paciente` | HTTP `403 Forbidden`; sin efectos secundarios en base de datos. |
| `TC-05`: Rechazo por estado inválido del estudio | `POST /api/estudios/42/remuestrear` cuando el estudio está en `EstadoEstudio.CREADO` o `EstadoEstudio.RESULTADO_CARGADO` | HTTP `409 Conflict` con código `ESTUDIO_ESTADO_INVALIDO_PARA_REMUESTREO`. |
| `TC-06`: Desvinculación de `SampleSet` abierto al descartar muestra | Muestra pertenecía a un `SampleSet` con `EstadoSampleSet.ABIERTO` y se descarta en `POST /api/estudios/42/remuestrear` | `muestra.sample_set_id` queda en `None`, liberando el lugar en el `SampleSet` abierto. |
| `TC-07`: Reserva de nuevo turno sin nuevo pago desde `Remuestreo requerido` | `POST /api/estudios/42/turnos` por el `Paciente` titular cuando `estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO` | HTTP `201 Created`; se crea nuevo `Turno` activo, `estudio.estado == EstadoEstudio.TURNO_SACADO`, no se exige nuevo registro en `pagos`. |
| `TC-08`: Toma de nueva muestra vía `Bot de Telegram` conserva historial | `POST /api/webhooks/telegram/muestra-tomada` para el nuevo turno del estudio remuestreado | HTTP `200 OK`; ` len(estudio.muestras) == 2` (una descartada y una nueva con `motivo_descarte == None`), `estudio.muestra_vigente` apunta a la nueva muestra y `estudio.estado == EstadoEstudio.LISTA_PARA_RETIRAR`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Cuando un estudio requiere remuestreo, el contador `estudio.ausencias` no se reinicia o no penaliza el pago previo ya efectuado, pero mantiene la regla general `BETWEEN 0 AND 5` (`estudios.py#L47`). | `.ai/2-Glosario_LEL.md` (`Remuestrear`) y `app/src/core/models/estudios.py` | Low |
| A2 | Si el fallo ocurre cuando la muestra ya viajó a Corea (`EstadoEstudio.EN_VIAJE_COREA`), el descarte individual de esa muestra permite retroceder ese `Estudio` a `Remuestreo requerido` sin afectar a los otros 9 estudios del mismo `SampleSet`. | `.ai/1-Entrevista.md` (línea 154: los resultados/fallas en Corea son individuales por cada estudio) | Low |

## Open Questions

- Ninguna pregunta abierta bloqueante: las reglas de volumen mínimo (`ML_MINIMOS_TUBO = Decimal("2")`), motivos de descarte (`MotivoDescarte`) y gratuidad del remuestreo están completamente definidas en el LEL y en `app/src/core/models/`.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/estudios.py`, `logistica.py`, `turnos.py`, `usuarios.py`, `enums.py` y `reglas.py`. | Estado marcado como `Approved`. |
