# WORKFLOW: Escenario 4 – Autorizar un estudio por obra social
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-4`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Administrativo`, `Paciente` |
| **Objetos** | `Estudio`, `Presupuesto`, `Obra social`, `API de obras sociales`, `Cupón`, `API de cupones`, `Aviso` |
| **Verbos** | `Sacar turno` *(habilitado si el estudio resulta `Autorizado`)* |
| **Estados** | `Creado`, `Pendiente de autorización`, `Autorizado`, `Rechazado` |

---

## Overview

- **Objetivo**: Registrar la decisión de la `Obra social` (aprobación o rechazo) sobre un `Estudio` con `Presupuesto` emitido y, cuando la `Obra social` lo autoriza, pasar el `Estudio` al estado `Autorizado`, registrar automáticamente el movimiento financiero (`Pago` con `TipoPago.OBRA_SOCIAL`, asumido como pagado) y habilitar al `Paciente` para `Sacar turno`.
- **Contexto**: El `Presupuesto` ya fue emitido y el `Paciente` utiliza una `Obra social` (el `Estudio` se encuentra en `Pendiente de autorización`, o bien el `Paciente` acaba de elegir su `Obra social` desde el estado `Creado` pasando a `Pendiente de autorización`). El `Administrativo` gestiona la autorización con la `Obra social` (o recibe la resolución de la `API de obras sociales`) y carga en el sistema si la `Obra social` autorizó o rechazó el `Estudio`.
- **Recursos**: `Estudio` (`estudio_id`), `Presupuesto`, `Obra social` (`porcentaje_cobertura`), registro `Autorizacion` (`ResultadoAutorizacion`), registro financiero `Pago` (`TipoPago.OBRA_SOCIAL`), `Cupón` opcional acumulable.
- **Episodios**:
  1. El `Administrativo` gestiona la autorización del `Estudio` ante la `Obra social` (previa elección de `Obra social` por el `Paciente` si el `Estudio` estaba en `Creado`).
  2. El `Administrativo` registra el resultado de la decisión de la `Obra social` (`ResultadoAutorizacion.AUTORIZADA` o `ResultadoAutorizacion.RECHAZADA`).
  3. Cuando la `Obra social` aprueba el `Estudio`, el sistema actualiza el `Estudio` al estado `Autorizado` (`EstadoEstudio.AUTORIZADO`); si la `Obra social` lo rechaza, el sistema actualiza el `Estudio` al estado `Rechazado` (`EstadoEstudio.RECHAZADO`).
  4. Cuando el `Estudio` queda `Autorizado`, el sistema registra el movimiento financiero en `pagos` (`TipoPago.OBRA_SOCIAL`, calculando `cobertura_obra_social_usd`, eventual `descuento_cupon_usd` si se aplicó un `Cupón` acumulable, y `monto_usd`), notifica al `Paciente` mediante `Aviso` y mail, y le habilita `Sacar turno`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Administrativo` | Sujeto LEL del laboratorio central que gestiona el trámite y carga si la `Obra social` autorizó o rechazó el `Estudio`. |
| `Paciente` | Sujeto LEL que elige tramitar por `Obra social`, recibe la notificación de resolución (`Autorizado` o `Rechazado`) y, si fue autorizado, queda habilitado para `Sacar turno`. |
| `Obra social` / `API de obras sociales` | Objeto LEL que informa el porcentaje de cobertura y autoriza o rechaza el `Estudio`. |
| `router` (`autorizaciones_router`) | Capa HTTP Flask (`POST /api/v1/estudios/{estudio_id}/solicitar-autorizacion` y `POST /api/v1/estudios/{estudio_id}/autorizaciones`). |
| `service` (`economia_service`) | Capa de negocio que valida la máquina de estados (`Creado` -> `Pendiente de autorización` -> `Autorizado` \| `Rechazado`), calcula importes cubiertos y registra `Autorizacion` y `Pago`. |
| `repo` (`economia_repo`, `estudio_repo`, `usuario_repo`) | Capa de acceso a datos SQLAlchemy sobre `estudios`, `presupuestos`, `obras_sociales`, `autorizaciones`, `pagos`, `cupones`, `avisos`. |
| `clients` (`obras_sociales_client`, `cupones_client`, `notificacion_client`) | Clientes HTTP hacia `API de obras sociales`, `API de cupones` (si el paciente acumula cupón con obra social) y servicio de correo/avisos. |
| `PostgreSQL` | Base de datos relacional que asegura atomicidad entre el cambio a `Autorizado` y el registro del `Pago`. |

---

## Prerequisites

- Para que el `Administrativo` registre el resultado de la autorización:
  - El usuario autenticado posee `Usuario.rol == Rol.ADMINISTRATIVO`.
  - El `Estudio` (`estudios.id == estudio_id`) existe, tiene un `Presupuesto` emitido (`estudio.presupuesto is not None`), tiene una `Obra social` asociada (`estudio.obra_social_id is not None`) y se encuentra en `estudio.estado == EstadoEstudio.PENDIENTE_AUTORIZACION` (o en `EstadoEstudio.CREADO` si el administrativo inicia y resuelve el trámite en un mismo acto).
  - Si el `Estudio` estaba en `EstadoEstudio.CREADO` porque el `Paciente` aún no había elegido modalidad, el `Paciente` (o `Administrativo`) selecciona primero la `Obra social`, pasando el `Estudio` a `EstadoEstudio.PENDIENTE_AUTORIZACION`.

---

## Trigger

- **Subflujo A (Elección de Obra social por el Paciente si estaba en `Creado`)**: `POST /api/v1/estudios/{estudio_id}/obra-social` (autenticado como `Paciente` titular, pasa `Estudio` de `Creado` a `Pendiente de autorización`).
- **Flujo Principal (Registro de resolución de la Obra social por el Administrativo)**: El `Administrativo` ingresa el resultado de la gestión con la `Obra social` mediante `POST /api/v1/estudios/{estudio_id}/autorizaciones` (autenticado con rol `administrativo`).

---

## Workflow Tree

### STEP 1: Validación de rol del `Administrativo`, existencia de `Presupuesto`, `Obra social` y estado `Pendiente de autorización`
**Actor**: `router` (`autorizaciones_router`) -> `service` (`economia_service`) -> `repo` (`estudio_repo`, `economia_repo`)
**Action**:
1. Verifica que el usuario autenticado tenga `Usuario.rol == Rol.ADMINISTRATIVO`.
2. Carga el `Estudio` con bloqueo pesimista (`SELECT ... FOR UPDATE`), su `Presupuesto` y su `ObraSocial`.
3. Verifica que `estudio.presupuesto is not None` y `estudio.obra_social is not None`.
4. Verifica que `estudio.estado == EstadoEstudio.PENDIENTE_AUTORIZACION`.
5. Valida que el campo `resultado` del payload sea `"autorizada"` (`ResultadoAutorizacion.AUTORIZADA`) o `"rechazada"` (`ResultadoAutorizacion.RECHAZADA`).
**Timeout**: `2s`
**Input**: `estudio_id`, `resultado` (`"autorizada"` | `"rechazada"`), `codigo_cupon` (opcional), `solicitud_externa_id` (opcional), `usuario_actual`.
**Output on SUCCESS**: `Estudio`, `Presupuesto`, `ObraSocial` y `Autorizacion` pendiente (si existe) -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no tiene `Rol.ADMINISTRATIVO` -> `return 403 Forbidden` (`code: "FORBIDDEN_ROLE"`).
  - `FAILURE(not_found)`: `estudio_id` no existe -> `return 404 Not Found` (`code: "ESTUDIO_NO_ENCONTRADO"`).
  - `FAILURE(validation_error)`: El `Estudio` no tiene `Presupuesto` emitido o no tiene `Obra social` asociada, o `resultado` no es `"autorizada"` ni `"rechazada"` -> `return 422 Unprocessable Entity` (`code: "DATOS_AUTORIZACION_INVALIDOS"`).
  - `FAILURE(invalid_state)` / `FAILURE(conflict)`: `estudio.estado != EstadoEstudio.PENDIENTE_AUTORIZACION` (por ejemplo, ya estaba `Autorizado` o `Rechazado`) -> `return 409 Conflict` (`{"ok": false, "error": "El estudio no se encuentra en estado Pendiente de autorización", "code": "ESTADO_ESTUDIO_INVALIDO", "retryable": false}`).

**Observable states during this step**:
  - **Customer/Actor (`Administrativo`) sees**: Spinner `"Registrando resolución de la obra social..."`.
  - **Operator sees**: Lock transaccional sobre `estudios.id == estudio_id`.
  - **Database**: Lectura `FOR UPDATE` en `estudios`, `presupuestos`, `obras_sociales`, `autorizaciones`.
  - **Logs**: `[economia_service] STEP 1 iniciado estudio_id=<id> resultado=<res> admin_id=<uid>`

---

### STEP 2: Consulta de cobertura a `API de obras sociales` y validación de `Cupón` acumulable (si fue aprobado)
**Actor**: `service` (`economia_service`) -> `clients` (`obras_sociales_client`, `cupones_client`)
**Action**:
- **Rama 2A (`resultado == "rechazada"`)**: No requiere cálculo de pago ni validación de cupón -> pasa directo a `STEP 3`.
- **Rama 2B (`resultado == "autorizada"`)**:
  1. Obtiene `porcentaje_cobertura` de `estudio.obra_social.porcentaje_cobertura` (refrescándolo desde la `API de obras sociales` si está disponible).
  2. Calcula `cobertura_obra_social_usd = round(presupuesto.monto_total_usd * (porcentaje_cobertura / Decimal("100")), 2)`.
  3. Si existe un `Cupón` asignado/aplicado al estudio (`codigo_cupon`), consulta su vigencia en la `API de cupones` (`GET /api/v1/cupones/{codigo}/vigencia`) y verifica que `cupon.paciente_id == estudio.paciente_id` y `cupon.usado == False`. El descuento del cupón se acumula con la cobertura de la obra social:
     - `descuento_cupon_usd = min(presupuesto.monto_total_usd - cobertura_obra_social_usd, round(presupuesto.monto_total_usd * (cupon.descuento_porcentaje / Decimal("100")), 2))`
  4. Calcula el monto financiero registrado `monto_usd = presupuesto.monto_total_usd - descuento_cupon_usd` (según `.ai/2-Glosario_LEL.md`: *"Situación del estudio aprobado por la obra social, asumido como pagado"*).
**Timeout**: `5s`
**Input**: `Estudio`, `Presupuesto`, `ObraSocial`, `codigo_cupon` (opcional).
**Output on SUCCESS**: Importes calculados (`cobertura_obra_social_usd`, `descuento_cupon_usd`, `monto_usd`) -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(validation_error)`: Se indicó un `codigo_cupon` que no existe, pertenece a otro paciente o no está vigente en la `API de cupones` -> `return 422 Unprocessable Entity` (`code: "CUPON_NO_VIGENTE"`).
  - `FAILURE(transient_external_error)`: Si la `API de cupones` da timeout al validar un cupón provisto -> reintentar 2 veces con backoff `1s`, `2s`; si persiste -> `return 502 Bad Gateway` (`code: "CUPONES_API_UNAVAILABLE", "retryable": true`).

**Observable states during this step**:
  - **Customer/Actor (`Administrativo`) sees**: `"Calculando cobertura financiera de la obra social..."`.
  - **Operator sees**: Consulta a `API de obras sociales` / `API de cupones` (si aplica).
  - **Database**: Sin modificaciones aún.
  - **Logs**: `[economia_service] STEP 2 estudio_id=<id> cobertura_usd=<cob> descuento_cupon_usd=<desc>`

---

### STEP 3: Persistencia de `Autorizacion`, `Pago` (si fue autorizada) y transición de `EstadoEstudio`
**Actor**: `service` (`economia_service`) -> `repo` (`economia_repo`, `estudio_repo`) -> `PostgreSQL`
**Action**:
1. Actualiza la fila `Autorizacion` pendiente de ese `estudio_id` (o inserta una nueva fila en `autorizaciones` si no existía fila previa):
   - `estudio_id = estudio.id`
   - `resultado = ResultadoAutorizacion.AUTORIZADA` o `ResultadoAutorizacion.RECHAZADA`
   - `registrada_por_id = usuario_actual.id` (`Administrativo`)
   - `solicitud_externa_id = input.solicitud_externa_id` (si se informó)
   - `fecha = func.now()`
2. **Si `resultado == ResultadoAutorizacion.AUTORIZADA`**:
   - Cambia `estudio.estado = EstadoEstudio.AUTORIZADO` (`"Autorizado"`).
   - Inserta una fila en `pagos`:
     - `presupuesto_id = presupuesto.id`
     - `tipo = TipoPago.OBRA_SOCIAL`
     - `monto_usd = monto_usd`
     - `cupon_id = cupon.id if cupon else None`
     - `descuento_cupon_usd = descuento_cupon_usd`
     - `cobertura_obra_social_usd = cobertura_obra_social_usd`
     - `anulado = False`
   - Si se usó `Cupón`, marca `cupon.usado = True`, `cupon.usado_en = func.now()` e invoca a la `API de cupones` (`POST /api/v1/cupones/{codigo}/consumir`) para vencerlo.
3. **Si `resultado == ResultadoAutorizacion.RECHAZADA`**:
   - Cambia `estudio.estado = EstadoEstudio.RECHAZADO` (`"Rechazado"`).
   - No inserta fila en `pagos`.
**Timeout**: `5s`
**Input**: `Estudio`, `Presupuesto`, `ResultadoAutorizacion`, importes calculados, `Cupon` (opcional).
**Output on SUCCESS**: `Autorizacion` y `Pago` (si aplica) persistidos -> `GO TO STEP 4`
**Output on FAILURE**:
  - `FAILURE(transient_external_error)`: Si se usó `Cupón` y la `API de cupones` falla al consumirlo tras 2 reintentos -> `GO TO ABORT_CLEANUP` (`return 502 Bad Gateway`).
  - `FAILURE(db_error)` / `FAILURE(timeout)`: Error de escritura en `PostgreSQL` -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Administrativo`) sees**: `"Guardando estado del estudio y registro financiero..."`.
  - **Operator sees**: `estudios.estado` actualizado a `'Autorizado'` o `'Rechazado'`.
  - **Database**: `autorizaciones.resultado` actualizado; `estudios.estado` en `AUTORIZADO` o `RECHAZADO`; fila en `pagos` (`tipo = 'obra_social'`, `anulado = False`) si fue autorizado.
  - **Logs**: `[economia_repo] STEP 3 estudio_id=<id> nuevo_estado=<estado> pago_id=<pid>`

---

### STEP 4: Notificación (`Aviso` y mail) al `Paciente`
**Actor**: `service` (`economia_service`) -> `repo` (`usuario_repo`) + `clients` (`notificacion_client`)
**Action**:
1. Crea un `Aviso` en la tabla `avisos` para el `Paciente` (`usuario_id = estudio.paciente.usuario_id`):
   - Si `AUTORIZADA`: `"Su estudio #<id> fue autorizado por la obra social. Ya puede solicitar su turno de extracción."`
   - Si `RECHAZADA`: `"Su estudio #<id> fue rechazado por la obra social. Puede presentar una demanda con decisión judicial favorable en PDF para solicitar la reautorización."`
2. Envía el correo electrónico correspondiente al `Paciente` y ejecuta `session.commit()`.
**Timeout**: `4s`
**Input**: `Estudio`, `ResultadoAutorizacion`
**Output on SUCCESS**: Respuesta `200 OK` con el detalle de la autorización y del pago registrado -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(transient_mail_error)`: Si falla el envío de correo SMTP tras 2 reintentos, deja `avisos.enviado = False` para reintento por cola pero confirma la transacción en BD (`session.commit()`) para no revertir una autorización financiera ya aprobada.

**Observable states during this step**:
  - **Customer/Actor (`Administrativo`) sees**: Confirmación `"Autorización registrada: Estudio #<id> ahora en estado <Autorizado|Rechazado>"`.
  - **Actor (`Paciente`) sees**:
    - Si `Autorizado`: Botón `"Sacar turno"` habilitado en la vista de su `Estudio`.
    - Si `Rechazado`: Botón `"Cargar demanda judicial (PDF)"` habilitado (Escenario 5).
  - **Database**: Transacción confirmada en `autorizaciones`, `estudios`, `pagos` y `avisos`.
  - **Logs**: `[economia_service] STEP 4 completado estudio_id=<id> estado=<estado>`

---

### ABORT_CLEANUP: Reversión de registro de autorización
**Triggered by**: Fallos en `STEP 3` (error de base de datos o imposibilidad de consumir `Cupón` en `API de cupones`).
**Actions**:
  1. Ejecutar `session.rollback()` revirtiendo los cambios en `pagos`, `cupones`, `autorizaciones` y `estudios.estado` (que vuelve a `EstadoEstudio.PENDIENTE_AUTORIZACION`).
  2. Registrar el error en logs y retornar respuesta HTTP `500` / `502` con `retryable: true`.
**What customer (`Administrativo`) sees**: Mensaje de error indicando que no se pudo registrar la decisión de la obra social; el estudio permanece en `Pendiente de autorización`.
**What operator sees**: Alerta en logs sin pagos huérfanos ni cambios de estado parciales.

---

## State Transitions

```
[Estudio.estado = CREADO]
   |-- (Paciente/Administrativo asocia Obra social con Presupuesto emitido)
   v
[Estudio.estado = PENDIENTE_AUTORIZACION ("Pendiente de autorizacion")]
   |
   |-- (Administrativo registra resultado = AUTORIZADA en STEP 1-4)
   |       --> Autorizacion.resultado = ResultadoAutorizacion.AUTORIZADA ("autorizada")
   |       --> Pago creado (tipo = TipoPago.OBRA_SOCIAL, anulado = False)
   |       --> Estudio.estado = EstadoEstudio.AUTORIZADO ("Autorizado") [Habilita Sacar turno]
   |
   |-- (Administrativo registra resultado = RECHAZADA en STEP 1-4)
   |       --> Autorizacion.resultado = ResultadoAutorizacion.RECHAZADA ("rechazada")
   |       --> Sin registro en Pago
   |       --> Estudio.estado = EstadoEstudio.RECHAZADO ("Rechazado") [Habilita Cargar demanda]
   |
   +-- (Fallo en STEP 3 -> ABORT_CLEANUP)
           --> Permanece en Estudio.estado = EstadoEstudio.PENDIENTE_AUTORIZACION
```

---

## Handoff Contracts

### 1. Frontend Administrativo -> Backend (`router` -> `service`)
**Endpoint**: `POST /api/v1/estudios/{estudio_id}/autorizaciones`
**Payload**:
```json
{
  "resultado": "autorizada",
  "solicitud_externa_id": "OS-2026-00981",
  "codigo_cupon": null
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "autorizacion_id": 15,
    "estudio_id": 101,
    "resultado": "autorizada",
    "estado_estudio": "Autorizado",
    "registrada_por_id": 12,
    "pago": {
      "pago_id": 88,
      "presupuesto_id": 33,
      "tipo": "obra_social",
      "monto_usd": "560.00",
      "cobertura_obra_social_usd": "448.00",
      "descuento_cupon_usd": "0.00",
      "anulado": false
    }
  }
}
```
**Failure response** (`403` / `404` / `409` / `422` / `502`):
```json
{
  "ok": false,
  "error": "El estudio no se encuentra en estado Pendiente de autorización",
  "code": "ESTADO_ESTUDIO_INVALIDO",
  "retryable": false
}
```
**Timeout**: `10s`
**ON FAILURE**: Rollback completo mediante `ABORT_CLEANUP`.

---

### 2. Frontend Paciente -> Backend (Selección de Obra social desde estado `Creado`)
**Endpoint**: `POST /api/v1/estudios/{estudio_id}/obra-social`
**Payload**:
```json
{
  "obra_social_id": 5
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "estudio_id": 101,
    "obra_social_id": 5,
    "estado_estudio": "Pendiente de autorizacion",
    "autorizacion_id": 15,
    "resultado_autorizacion": "pendiente"
  }
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Solo se puede seleccionar obra social para un estudio en estado Creado",
  "code": "ESTADO_ESTUDIO_INVALIDO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: No modifica el estado del `Estudio`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Actualización/Inserción en `autorizaciones` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Inserción en `pagos` (`TipoPago.OBRA_SOCIAL`) | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Actualización de `estudios.estado` a `AUTORIZADO` o `RECHAZADO` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Marcado de `cupones.usado = True` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/economia.py`, `Autorizacion` tiene `estudio_id`, `resultado` (`Enum(ResultadoAutorizacion)`), `registrada_por_id`, `demanda_id` y `solicitud_externa_id`. | Low | STEP 3 | 100% alineado con las columnas de `Autorizacion`. |
| RC-2 | En `app/src/core/models/economia.py`, `Pago` tiene `presupuesto_id`, `tipo` (`TipoPago.OBRA_SOCIAL`), `monto_usd`, `cupon_id`, `descuento_cupon_usd`, `cobertura_obra_social_usd` y `anulado`. | Low | STEP 2 & STEP 3 | Coincidencia exacta con el modelo `Pago`. |
| RC-3 | Según `.ai/2-Glosario_LEL.md` (`Objeto: Cupón`), el `Cupón` *"se acumula con la cobertura de la obra social"*, por lo que `Pago` incluye tanto `cobertura_obra_social_usd` como `descuento_cupon_usd`. | Low | STEP 2 | Contemplada la acumulación en STEP 2. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path obra social autoriza el estudio** | `POST /api/v1/estudios/{id}/autorizaciones` con `{"resultado": "autorizada"}` por un `Administrativo` sobre un estudio en `Pendiente de autorización`. | Retorna `200 OK`; `Estudio.estado == EstadoEstudio.AUTORIZADO`; `Autorizacion.resultado == ResultadoAutorizacion.AUTORIZADA`; se crea `Pago` con `tipo = TipoPago.OBRA_SOCIAL` y `cobertura_obra_social_usd > 0`; se crea `Aviso` al `Paciente`. |
| **TC-02: Happy path obra social rechaza el estudio** | `POST /api/v1/estudios/{id}/autorizaciones` con `{"resultado": "rechazada"}` por un `Administrativo`. | Retorna `200 OK`; `Estudio.estado == EstadoEstudio.RECHAZADO`; `Autorizacion.resultado == ResultadoAutorizacion.RECHAZADA`; 0 filas creadas en `pagos`; se crea `Aviso` informando el rechazo. |
| **TC-03: Autorización con cupón acumulable con cobertura de obra social** | `POST /api/v1/estudios/{id}/autorizaciones` con `{"resultado": "autorizada", "codigo_cupon": "CUPON20"}` vigente. | Retorna `200 OK`; `Pago` registra tanto `cobertura_obra_social_usd` como `descuento_cupon_usd`; `Cupon.usado == True` y se vence en la `API de cupones`. |
| **TC-04: Paciente selecciona obra social desde estado Creado** | `POST /api/v1/estudios/{id}/obra-social` con `{"obra_social_id": 5}` por el `Paciente` titular. | Retorna `200 OK`; `Estudio.estado` cambia de `Creado` a `Pendiente de autorización` y se crea `Autorizacion` en `PENDIENTE`. |
| **TC-05: Intento de autorizar un estudio en estado inválido (ej. ya Autorizado o Turno sacado)** | `POST /api/v1/estudios/{id}/autorizaciones` cuando `estudio.estado == EstadoEstudio.AUTORIZADO`. | Retorna `409 Conflict` (`code: "ESTADO_ESTUDIO_INVALIDO"`); no duplica el `Pago`. |
| **TC-06: Intento de autorizar por usuario sin rol Administrativo** | `POST /api/v1/estudios/{id}/autorizaciones` invocado por el propio `Paciente` o un `Médico`. | Retorna `403 Forbidden` (`code: "FORBIDDEN_ROLE"`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Cuando la obra social autoriza el estudio, se asume que el estudio está pagado en su totalidad (la obra social transfiere a las 24 h sin fallar, según la entrevista líneas 293-295), por lo que el registro `Pago` se crea inmediatamente al autorizar y habilita `Sacar turno`. | `.ai/1-Entrevista.md` líneas 293-299, `.ai/2-Glosario_LEL.md` (`Estado: Autorizado`) y `.ai/3-Escenarios.md` (Escenario 4 Episodio 4). | Bajo. |

## Open Questions

- Cuando la `Obra social` cubre menos del 100% (por ejemplo 80%) y no hay `Cupón` por el 20% restante, ¿el coseguro se asume saldado junto con la autorización de la obra social o requiere un registro adicional? *(Según `.ai/2-Glosario_LEL.md`: `Estado: Autorizado — Situación del estudio aprobado por la obra social, asumido como pagado`, por lo que un único registro `Pago` al autorizar habilita directamente `Sacar turno`).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/economia.py` y `estudios.py`. | Marcada como `Approved`. |
