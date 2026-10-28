# WORKFLOW: Escenario 9 – Registrar la toma de una muestra
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-9`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Administrativo`, `Paciente`, `Transportista` |
| **Objetos** | `Centro de extracción`, `Bot de Telegram`, `Muestra`, `Turno`, `Estudio`, `Aviso` |
| **Verbos** | `Armar sample set` *(posterior al retiro y llegada al laboratorio central)* |
| **Estados** | `Turno sacado`, `Lista para retirar` |

---

## Overview

- **Objetivo**: Registrar automáticamente que una `Muestra` de sangre fue obtenida en un `Centro de extracción` cuando el `Centro de extracción` envía el mensaje de confirmación al `Bot de Telegram` del laboratorio central, creando el registro de `Muestra`, marcando la asistencia al `Turno` (`Turno.asistio = True`) y pasando el `Estudio` al estado `Lista para retirar` (`EstadoEstudio.LISTA_PARA_RETIRAR`).
- **Contexto**: El `Paciente` concurrió al `Centro de extracción` tercerizado en la fecha y hora de su `Turno` (con su `Estudio` en estado `Turno sacado`) y se le extrajo la `Muestra` de sangre. Como los 100 `Centros de extracción` tercerizados no operan dentro de la interfaz web del sistema, envían un mensaje al `Bot de Telegram` del laboratorio central indicando que se tomó la `Muestra`. Al recibir dicho mensaje, el sistema automatiza el cambio de estado sin depender de llamadas telefónicas manuales.
- **Recursos**: Mensaje de confirmación recibido por el `Bot de Telegram`, `Turno` activo (`turno_id` / `estudio_id` / `dni`), `Muestra` de sangre (`muestras`), `Estudio` (`estudios`), `Aviso` interno.
- **Episodios**:
  1. El `Centro de extracción` informa la toma de la `Muestra` enviando un mensaje al `Bot de Telegram` del laboratorio central.
  2. El sistema recibe el aviso a través del webhook/integración del `Bot de Telegram`.
  3. El sistema registra la `Muestra` (`tomada_en`, `estudio_id`, `turno_id`, y opcionalmente `mililitros`), marca `Turno.asistio = True` y cambia el estado del `Estudio` de `Turno sacado` a `Lista para retirar` (`EstadoEstudio.LISTA_PARA_RETIRAR`).
  4. El sistema informa mediante `Aviso` (al `Administrativo` y para la planificación de la `Orden del día` del `Transportista` de esa provincia) que la `Muestra` está `Lista para retirar` en el `Centro de extracción`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Centro de extracción` | Objeto LEL (laboratorio tercerizado que no opera en la web del sistema) que extrae la sangre al `Paciente` y envía el mensaje al `Bot de Telegram`. |
| `Bot de Telegram` | Objeto LEL del laboratorio central que recibe el mensaje del `Centro de extracción` y lo entrega al backend vía webhook HTTP. |
| `Administrativo` | Sujeto LEL del laboratorio central que visualiza el cambio de estado del `Estudio` a `Lista para retirar` y recibe el `Aviso`. |
| `Transportista` | Sujeto LEL provincial cuya próxima `Orden del día` incluirá el `Centro de extracción` con la `Muestra` en estado `Lista para retirar`. |
| `router` (`telegram_webhook_router` / `muestras_router`) | Capa HTTP Flask (`POST /api/v1/webhooks/telegram/muestra-tomada`) que autentica la firma/token secreto del `Bot de Telegram` y parsea el payload. |
| `service` (`logistica_service`) | Capa de negocio que localiza el `Estudio` en `Turno sacado` y su `Turno` activo, marca `turno.asistio = True`, crea la `Muestra` y cambia `estudio.estado = EstadoEstudio.LISTA_PARA_RETIRAR`. |
| `repo` (`logistica_repo`, `turno_repo`, `estudio_repo`, `usuario_repo`) | Capa de acceso a datos SQLAlchemy sobre `muestras`, `turnos`, `estudios`, `avisos`. |
| `PostgreSQL` | Base de datos relacional donde se persisten la nueva `Muestra` y el nuevo estado `Lista para retirar`. |

---

## Prerequisites

- El `Estudio` (`estudios.id == estudio_id`) existe y se encuentra exactamente en `estudio.estado == EstadoEstudio.TURNO_SACADO` (`"Turno sacado"`).
- Existe un `Turno` activo (`turno.activo == True` y `turno.asistio is None`) asociado a ese `estudio_id`.
- El request entrante en el webhook proviene del `Bot de Telegram` autenticado mediante el header `X-Telegram-Bot-Api-Secret-Token` (o token configurado).

---

## Trigger

El `Centro de extracción` envía el mensaje de confirmación al `Bot de Telegram` del laboratorio central, el cual invoca el endpoint del sistema:
- **Endpoint HTTP**: `POST /api/v1/webhooks/telegram/muestra-tomada` (o endpoint administrativo de contingencia `POST /api/v1/estudios/{estudio_id}/muestras/toma`).

---

## Workflow Tree

### STEP 1: Autenticación del `Bot de Telegram` y validación del payload del mensaje
**Actor**: `router` (`telegram_webhook_router`) -> `service` (`logistica_service`)
**Action**:
1. Verifica el token de seguridad del webhook (`X-Telegram-Bot-Api-Secret-Token`) para impedir que terceros no autorizados inyecten confirmaciones falsas de muestras.
2. Extrae del mensaje/payload el identificador de referencia (`estudio_id`, `turno_id` o `paciente_dni` + `centro_id`) y, si fue informado, el volumen en `mililitros` del tubo.
**Timeout**: `2s`
**Input**: Header `X-Telegram-Bot-Api-Secret-Token` + Payload JSON del `Bot de Telegram`.
**Output on SUCCESS**: Datos normalizados (`estudio_id` / `turno_id`, `mililitros` opcional, `timestamp_mensaje`) -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Header `X-Telegram-Bot-Api-Secret-Token` ausente o inválido -> `return 403 Forbidden` (`{"ok": false, "error": "Token de bot de Telegram inválido", "code": "INVALID_TELEGRAM_SECRET", "retryable": false}`).
  - `FAILURE(validation_error)`: El mensaje no contiene un `estudio_id` ni `turno_id` / `dni` válido -> Responde al `Bot de Telegram` con mensaje de formato inválido y retorna `400 Bad Request` (`code: "FORMATO_MENSAJE_INVALIDO"`).

**Observable states during this step**:
  - **Customer/Actor (`Centro de extracción` en Telegram) sees**: Mensaje enviado al chat del `Bot de Telegram`.
  - **Operator (`Administrativo`) sees**: Evento de webhook entrante en logs.
  - **Database**: Sin cambios.
  - **Logs**: `[telegram_webhook_router] STEP 1 mensaje recibido estudio_id=<id> turno_id=<tid>`

---

### STEP 2: Localización y bloqueo del `Estudio` en estado `Turno sacado` y su `Turno` activo
**Actor**: `service` (`logistica_service`) -> `repo` (`estudio_repo`, `turno_repo`) -> `PostgreSQL`
**Action**:
1. Carga el `Estudio` (`SELECT ... FOR UPDATE`) y su `Turno` activo (`turno.activo == True`).
2. Verifica idempotencia: si el `Estudio` ya está en `EstadoEstudio.LISTA_PARA_RETIRAR` y ya existe una `Muestra` vigente (`motivo_descarte is None`) para ese `turno_id` (por reentrega duplicada del webhook de Telegram), devuelve `200 OK` de forma idempotente sin crear una segunda `Muestra`.
3. Verifica que `estudio.estado == EstadoEstudio.TURNO_SACADO`.
**Timeout**: `3s`
**Input**: `estudio_id` / `turno_id`
**Output on SUCCESS**: `Estudio` y `Turno` activo bloqueados en transacción -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(not_found)`: No existe el `Estudio` o el `Turno` indicado -> `return 404 Not Found` (`code: "ESTUDIO_O_TURNO_NO_ENCONTRADO"`).
  - `FAILURE(invalid_state)` / `FAILURE(conflict)`: El `Estudio` no está en `EstadoEstudio.TURNO_SACADO` (por ejemplo, el turno fue cancelado previamente o el estudio está en `Creado`) -> `return 409 Conflict` (`{"ok": false, "error": "El estudio no tiene un turno activo en estado Turno sacado", "code": "ESTADO_ESTUDIO_INVALIDO", "retryable": false}`).

**Observable states during this step**:
  - **Customer/Actor (`Centro de extracción`) sees**: Procesando confirmación en el bot.
  - **Operator (`Administrativo`) sees**: Lock transaccional sobre `estudios` y `turnos`.
  - **Database**: Lectura `FOR UPDATE` en `estudios`, `turnos` y `muestras`.
  - **Logs**: `[logistica_service] STEP 2 validado estudio_id=<eid> turno_id=<tid> estado_actual=Turno sacado`

---

### STEP 3: Creación de la `Muestra`, marcado de asistencia al `Turno` y transición a `Lista para retirar`
**Actor**: `service` (`logistica_service`) -> `repo` (`logistica_repo`, `turno_repo`, `estudio_repo`, `usuario_repo`) -> `PostgreSQL`
**Action**:
1. Marca en el `Turno`:
   - `turno.asistio = True`
2. Inserta una fila en la tabla `muestras`:
   - `estudio_id = estudio.id`
   - `turno_id = turno.id`
   - `sample_set_id = None`
   - `mililitros = input.mililitros` (puede ser `None` si los mililitros se miden al recepcionar en el laboratorio central, o un `Decimal` >= 2.00; si en el momento de la carga ya se informara `< 2` ml, el Escenario 10 de remuestreo aplica `MotivoDescarte.VOLUMEN_INSUFICIENTE`)
   - `tomada_en = func.now()`
   - `llegada_lab_central = None`
   - `motivo_descarte = None`
3. Actualiza el estado del `Estudio`:
   - `estudio.estado = EstadoEstudio.LISTA_PARA_RETIRAR` (`"Lista para retirar"`).
4. Inserta un `Aviso` en la tabla `avisos` para los usuarios con `Rol.ADMINISTRATIVO` y para el `Paciente` (`canal = CanalAviso.APP`):
   - `"La muestra del estudio #<id> fue tomada en el centro <centro.nombre> y se encuentra Lista para retirar."`
5. Ejecuta `session.commit()`.
**Timeout**: `4s`
**Input**: `Estudio`, `Turno`, `mililitros` (opcional)
**Output on SUCCESS**: `Muestra` creada (`muestra.id`) y `estudio.estado == EstadoEstudio.LISTA_PARA_RETIRAR` -> `GO TO STEP 4`
**Output on FAILURE**:
  - `FAILURE(db_error)` / `FAILURE(timeout)`: Error al insertar en `muestras` o actualizar `estudios` -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: En su panel, el estado de su `Estudio` cambia de `"Turno sacado"` a `"Lista para retirar"`.
  - **Operator (`Administrativo`) sees**: El `Estudio` pasa a `"Lista para retirar"` en el tablero del laboratorio central y la `Muestra` queda disponible para ser incluida en la `Orden del día` del `Transportista` de esa provincia.
  - **Database**: Fila insertada en `muestras` (`tomada_en != NULL`, `motivo_descarte = NULL`); `turnos.asistio = True`; `estudios.estado = EstadoEstudio.LISTA_PARA_RETIRAR`; filas en `avisos`.
  - **Logs**: `[logistica_repo] STEP 3 muestra_id=<mid> estudio_id=<eid> estado=Lista para retirar`

---

### STEP 4: Respuesta de confirmación al `Bot de Telegram`
**Actor**: `service` (`logistica_service`) -> `clients` (`telegram_client`) / HTTP Response
**Action**: Envía respuesta de acuse de recibo al `Bot de Telegram` confirmando que la `Muestra` del `Estudio` quedó registrada como `Lista para retirar`.
**Timeout**: `3s`
**Input**: `Muestra`, `Estudio`, `chat_id` (si proviene de webhook de Telegram).
**Output on SUCCESS**: Respuesta `200 OK` -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(transient_telegram_error)`: Si falla el mensaje de respuesta visual al chat de Telegram tras haberse hecho `session.commit()` en `STEP 3`, se registra un warning en logs pero NO se revierte la transacción en BD (la `Muestra` ya fue tomada y el `Estudio` ya está en `Lista para retirar`).

**Observable states during this step**:
  - **Customer/Actor (`Centro de extracción` en Telegram) sees**: Respuesta del `Bot de Telegram`: `"✅ Muestra registrada para el Estudio #<id>. Estado actualizado a: Lista para retirar."`
  - **Operator (`Administrativo`) sees**: `Aviso` activo en su lista de notificaciones.
  - **Database**: Estado final persistido (`EstadoEstudio.LISTA_PARA_RETIRAR`).
  - **Logs**: `[logistica_service] STEP 4 completado muestra_id=<mid> estudio_id=<eid>`

---

### ABORT_CLEANUP: Reversión del registro de toma de muestra
**Triggered by**: Fallo de base de datos en `STEP 3`.
**Actions**:
  1. Ejecutar `session.rollback()` revirtiendo la creación de la fila en `muestras`, el cambio de `turnos.asistio = True`, el cambio de `estudios.estado` y los `avisos`.
  2. Retornar HTTP `500` / `503` con `retryable: true` para que el webhook del `Bot de Telegram` reintente la entrega automáticamente.
**What actor (`Centro de extracción` / `Bot de Telegram`) sees**: Error transitorio (Telegram reintenta el webhook con backoff).
**What operator sees**: Log de error en el procesador de webhook; el `Estudio` permanece en `Turno sacado` hasta que el reintento tenga éxito.

---

## State Transitions

```
[Estudio.estado = TURNO_SACADO ("Turno sacado"), Turno.activo = True, Turno.asistio = None]
   |
   |-- (STEP 1-2 fallan: secreto inválido, turno inexistente o cancelado)
   |       --> [Rechazado (400 / 403 / 404 / 409), sin cambios en BD]
   |
   |-- (STEP 1-4 tienen éxito al recibir el mensaje del Bot de Telegram)
   |       --> Turno.asistio = True
   |       --> Muestra creada (estudio_id, turno_id, tomada_en = now(), motivo_descarte = None)
   |       --> Estudio.estado = EstadoEstudio.LISTA_PARA_RETIRAR ("Lista para retirar")
   |       --> Aviso generado: muestra lista para ser retirada por el Transportista
   |
   +-- (Fallo en STEP 3 -> ABORT_CLEANUP)
           --> [Rollback a Estudio.estado = TURNO_SACADO, Turno.asistio = None, sin Muestra]
```

---

## Handoff Contracts

### 1. `Bot de Telegram` -> Backend (`POST /api/v1/webhooks/telegram/muestra-tomada`)
**Endpoint**: `POST /api/v1/webhooks/telegram/muestra-tomada`
**Headers**:
- `X-Telegram-Bot-Api-Secret-Token: <secret>`
**Payload**:
```json
{
  "message_id": 88412,
  "chat_id": 10029384,
  "estudio_id": 101,
  "turno_id": 501,
  "mililitros": "4.50"
}
```
*(Nota: El endpoint también soporta el formato nativo de actualización de Telegram `{"update_id": ..., "message": {"text": "/muestra 101"}}` extrayendo `estudio_id` del texto del comando).*
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "muestra_id": 301,
    "estudio_id": 101,
    "turno_id": 501,
    "tomada_en": "2026-11-02T09:22:10Z",
    "mililitros": "4.50",
    "asistio": true,
    "estado_estudio": "Lista para retirar"
  }
}
```
**Failure response** (`400` / `403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "El estudio no tiene un turno activo en estado Turno sacado",
  "code": "ESTADO_ESTUDIO_INVALIDO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Si `retryable == true` (`5xx`), el `Bot de Telegram` reintenta el envío con exponential backoff; la operación es idempotente por `(estudio_id, turno_id)`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Registro en `muestras` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Actualización `turnos.asistio = True` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Actualización `estudios.estado = LISTA_PARA_RETIRAR` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Registros en `avisos` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/logistica.py`, `Muestra` tiene exactamente las columnas `estudio_id`, `turno_id`, `sample_set_id`, `mililitros` (`Numeric(5, 2)`), `tomada_en` (`# aviso por bot de Telegram`), `llegada_lab_central` y `motivo_descarte`. | Low | STEP 3 | 100% alineado con el modelo `Muestra`. |
| RC-2 | En `app/src/core/models/estudios.py`, la propiedad `Estudio.muestra_vigente` devuelve la última muestra con `m.motivo_descarte is None`. Al insertar la nueva `Muestra` con `motivo_descarte = None` en `STEP 3`, `estudio.muestra_vigente` pasa a apuntar automáticamente a esta muestra. | Low | STEP 3 | Verificado y compatible con el ciclo de remuestreo (Escenario 10). |
| RC-3 | En `app/src/core/models/enums.py`, el estado correspondiente del LEL es `EstadoEstudio.LISTA_PARA_RETIRAR = "Lista para retirar"` y el canal de aviso incluye `CanalAviso.TELEGRAM = "telegram"` y `CanalAviso.APP = "app"`. | Low | State Transitions | Nombres de enums exactos utilizados en toda la especificación. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path confirmación de toma de muestra vía Bot de Telegram** | `POST /api/v1/webhooks/telegram/muestra-tomada` con secreto válido para un estudio en `EstadoEstudio.TURNO_SACADO`. | Retorna `200 OK`; crea `Muestra` con `tomada_en != None` y `motivo_descarte == None`; marca `Turno.asistio == True`; cambia `Estudio.estado` a `EstadoEstudio.LISTA_PARA_RETIRAR`; crea `Aviso`. |
| **TC-02: Idempotencia ante reintento duplicado del webhook de Telegram** | Se envía dos veces el mismo webhook para el mismo `estudio_id` y `turno_id`. | La segunda llamada retorna `200 OK` devolviendo la misma `Muestra` sin duplicar filas en `muestras`. |
| **TC-03: Rechazo por token secreto de Telegram inválido o ausente** | `POST /api/v1/webhooks/telegram/muestra-tomada` sin header `X-Telegram-Bot-Api-Secret-Token` o con valor incorrecto. | Retorna `403 Forbidden` (`code: "INVALID_TELEGRAM_SECRET"`); no modifica el estudio ni crea muestra. |
| **TC-04: Rechazo cuando el estudio no está en estado Turno sacado** | `POST /api/v1/webhooks/telegram/muestra-tomada` para un estudio en `Creado` o cuyo turno fue cancelado (`activo == False`). | Retorna `409 Conflict` (`code: "ESTADO_ESTUDIO_INVALIDO"`); 0 filas creadas en `muestras`. |
| **TC-05: Toma de muestra luego de un Remuestreo requerido** | Un estudio que tenía una 1.ª muestra con `motivo_descarte = VOLUMEN_INSUFICIENTE`, sacó un 2.º turno (`Turno sacado`) y recibe confirmación de toma de muestra. | Retorna `200 OK`; se crea una 2.ª fila en `muestras` con `motivo_descarte = None`; `estudio.muestra_vigente` devuelve la 2.ª muestra y `Estudio.estado` pasa a `EstadoEstudio.LISTA_PARA_RETIRAR`. |
| **TC-06: Estudio o turno inexistente** | `POST /api/v1/webhooks/telegram/muestra-tomada` con `estudio_id = 99999`. | Retorna `404 Not Found` (`code: "ESTUDIO_O_TURNO_NO_ENCONTRADO"`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Los `Centros de extracción` tercerizados no se loguean en la web sino que informan la extracción al `Bot de Telegram` del laboratorio central indicando el número de estudio/turno o DNI del paciente. | `.ai/1-Entrevista.md` líneas 135-136, 225, 279 y `.ai/2-Glosario_LEL.md` (`Objeto: Bot de Telegram`, `Objeto: Centro de extracción`). | Bajo. |

## Open Questions

- ¿La medición de `mililitros` del tubo (`ML_MINIMOS_TUBO = 2`) se informa en el mensaje del `Bot de Telegram` al tomar la muestra o cuando el `Administrativo` / laboratorio central recepciona el tubo? *(El modelo `Muestra.mililitros` es `Optional[Decimal]`, por lo que este flujo soporta recibirlo opcionalmente en la toma o registrarlo en la recepción en el laboratorio central antes del Escenario 10).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/logistica.py`, `turnos.py` y `estudios.py`. | Marcada como `Approved`. |
