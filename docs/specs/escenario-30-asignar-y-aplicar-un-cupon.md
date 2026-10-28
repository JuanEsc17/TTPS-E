# WORKFLOW: Escenario 30 – Asignar y aplicar un cupón
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-30`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Gerente médico** | `Usuario` (`rol = Rol.GERENTE_MEDICO`) + `Medico` (`Cupon.gerente_id`) |
| **Sujetos** | **Médico** | `Usuario` (`rol = Rol.MEDICO` o `Rol.GERENTE_MEDICO`) + `Medico` (`Cupon.medico_id`, médico tratante) |
| **Sujetos** | **Paciente** | `Usuario` (`rol = Rol.PACIENTE`) + `Paciente` (`Cupon.paciente_id`, `Estudio.paciente_id`) |
| **Objetos** | **Cupón** | Modelo `Cupon` (tabla `cupones`) |
| **Objetos** | **Presupuesto** | Modelo `Presupuesto` (tabla `presupuestos`) y modelo `Pago` (tabla `pagos`) |
| **Objetos** | **Estudio** | Modelo `Estudio` (tabla `estudios`) |
| **Objetos** | **Obra social** | Modelo `ObraSocial` (tabla `obras_sociales`: `porcentaje_cobertura`) |
| **Objetos** | **API de cupones** | Cliente HTTP externo (`app/src/clients/cupones_client.py`) para validar vigencia y consumir/vencer el cupón |
| **Verbos** | **Pagar presupuesto** | Acción del **paciente** que abona el **presupuesto** aplicando el **cupón** y habilita **sacar turno** |
| **Estados** | **Creado**, **Autorizado** | `EstadoEstudio.CREADO` (pago particular) o `EstadoEstudio.AUTORIZADO` (copago remanente con **obra social**) |

---

## Overview

- **Objetivo:** Entregar un **cupón** a un **paciente** y que este lo utilice al pagar el **presupuesto** de su **estudio**, acumulando el descuento con la cobertura de su **obra social** si corresponde.
- **Contexto:** Existe un **cupón** creado (Escenario 29) y un **paciente** con un **estudio** que cuenta con **presupuesto** emitido pendiente de pago.
- **Recursos:** **Cupón** (`cupones`), **paciente** (`pacientes`), **presupuesto** (`presupuestos`), **pago** (`pagos`), **obra social** (`obras_sociales`), **API de cupones**.
- **Episodios:**
  1. El **médico** asigna el **cupón** al **paciente** (habiendo sido previamente asignado el cupón al **médico** por el **gerente médico**).
  2. El **paciente** aplica el **cupón** (mediante código numérico o archivo PDF/QR) al pagar el **presupuesto**.
  3. El sistema consulta a la **API de cupones** si el **cupón** está vigente.
  4. El sistema aplica el descuento, que se acumula con la cobertura de la **obra social**, y registra financieramente el pago en la tabla `pagos`.
  5. El sistema avisa a la **API de cupones** que el **cupón** fue usado, para que venza, y marca `cupones.usado = True`.

**Resumen del flujo:** El escenario se compone de dos etapas encadenadas sobre la entidad `Cupon`:
1. **Asignación (`STEP 1` y `STEP 2`):** El **gerente médico** asigna un **cupón** disponible a un **médico** (`PATCH /api/cupones/{cupon_id}/asignar-medico`, si no lo asignó al crearlo), y el **médico** tratante asigna uno de sus **cupones** disponibles a su **paciente** (`PATCH /api/cupones/{cupon_id}/asignar-paciente`).
2. **Aplicación en el pago (`STEP 3` a `STEP 5`):** Cuando el **paciente** abona el **presupuesto** (`POST /api/estudios/{estudio_id}/pagos` incluyendo `codigo_cupon`), el servicio bloquea la fila del **cupón** (`SELECT ... FOR UPDATE`), verifica que pertenezca al **paciente** y no esté usado, consulta su vigencia en la **API de cupones**, calcula el monto neto acumulando `ObraSocial.porcentaje_cobertura` + `Cupon.descuento_porcentaje` (truncado a un máximo del 100% del `Presupuesto.monto_total_usd`), notifica el consumo a la **API de cupones** para que venza y persiste atómicamente el registro en `pagos` junto con `cupones.usado = True` y `cupones.usado_en = now()`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Gerente médico** (Sujeto LEL) | Asigna un **cupón** creado a un **médico** tratante (si no fue asignado durante el Escenario 29). |
| **Médico** (Sujeto LEL) | Asigna uno de sus **cupones** disponibles a un **paciente** que atiende. |
| **Paciente** (Sujeto LEL) | Aplica el **cupón** (código o QR) en el momento de **pagar presupuesto**. |
| **Router HTTP** (`cupones.py` / `pagos.py`) | Valida sesión, rol (`GERENTE_MEDICO`, `MEDICO`, `PACIENTE`) y estructura de los payloads. |
| **Servicio de Cupones y Pagos** (`cupon_service.py` / `pago_service.py`) | Ejecuta las reglas de asignación, cálculo acumulado de descuento + cobertura de **obra social**, coordinación con la **API de cupones** y atomicidad transaccional. |
| **Cliente API de Cupones** (`cupones_client.py`) | Consulta vigencia (`GET /external/vouchers/{codigo}/vigencia`) y notifica el uso/vencimiento (`POST /external/vouchers/{codigo}/consumir`). |
| **Repositorio** (`cupon_repo.py` / `economia_repo.py`) | Lee y actualiza `cupones`, `presupuestos`, `estudios`, `obras_sociales` e inserta en `pagos` usando bloqueo pesimista (`FOR UPDATE`) para evitar doble uso concurrente. |
| **PostgreSQL** (`db`) | Garantiza integridad referencial y aislamiento transaccional. |

---

## Prerequisites

- **Sesión y Rol:**
  - Para asignar a un **médico**: sesión activa con `Rol.GERENTE_MEDICO`.
  - Para asignar a un **paciente**: sesión activa con `Rol.MEDICO` (o `Rol.GERENTE_MEDICO` actuando como médico tratante).
  - Para aplicar el **cupón** al pagar: sesión activa con `Rol.PACIENTE` (`Usuario.debe_cambiar_password == False`).
- **Datos existentes en `app/src/core/models/`:**
  - Existe una fila en `cupones` con `usado == False`.
  - Existe una fila en `pacientes` vinculada al **médico** tratante (`pacientes.medico_id == medicos.id` o un `Estudio` de ese paciente con `estudios.medico_id == medicos.id`).
  - Existe un `Estudio` del **paciente** con un `Presupuesto` emitido en la tabla `presupuestos` (`presupuestos.estudio_id == estudios.id`) que aún no posee un `Pago` activo (`pagos.anulado == False`).
- **Estado previo del `Estudio`:**
  - `Estudio.estado == EstadoEstudio.CREADO` (para pago particular) o `Estudio.estado == EstadoEstudio.AUTORIZADO` (cuando existe cobertura parcial de **obra social** y el paciente abona el copago aplicando el **cupón**).

---

## Trigger

1. **Asignación a paciente (Episodio 1):** El **médico** selecciona un **cupón** de su cartera y lo asigna a un **paciente** vía `PATCH /api/cupones/{cupon_id}/asignar-paciente` (precedido opcionalmente por `PATCH /api/cupones/{cupon_id}/asignar-medico` ejecutado por el **gerente médico**).
2. **Aplicación al pagar (Episodios 2-5):** El **paciente** confirma el pago del **presupuesto** enviando `POST /api/estudios/{estudio_id}/pagos` con el campo `codigo_cupon`.

---

## Workflow Tree

### STEP 1: Asignación del cupón al médico y del médico al paciente
**Actor**: **Gerente médico** / **Médico** -> Router (`cupones.py`) -> Servicio (`cupon_service.py`) -> Repositorio (`cupon_repo.py`)
**Action**:
  1. *(Si `cupon.medico_id` es `NULL`)*: El **gerente médico** asigna el **cupón** al **médico** (`PATCH /api/cupones/{cupon_id}/asignar-medico`).
  2. El **médico** tratante asigna el **cupón** (`cupon.medico_id == medico_actual.id`, `cupon.usado == False`, `cupon.paciente_id == NULL`) al **paciente** (`PATCH /api/cupones/{cupon_id}/asignar-paciente`), actualizando `cupones.paciente_id = paciente.id` y creando un `Aviso` (`CanalAviso.APP`) para informar al **paciente** que dispone de un **cupón** de descuento.
**Timeout**: `2s`
**Input**:
```json
{
  "cupon_id": 105,
  "medico_autenticado_id": 12,
  "paciente_id": 45
}
```
**Output on SUCCESS**: `{ cupon_id: 105, medico_id: 12, paciente_id: 45, usado: False }` -> GO TO STEP 2 (cuando el paciente inicia el pago)
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no es el **médico** titular del **cupón** (`cupon.medico_id != medico.id`) o el **paciente** no es atendido por dicho **médico** -> retornar `403 Forbidden` (`CUPON_NO_PERTENECE_AL_MEDICO` / `PACIENTE_NO_VINCULADO`).
  - `FAILURE(invalid_state)`: El **cupón** ya fue usado (`cupon.usado == True`) o ya está asignado a otro **paciente** (`cupon.paciente_id is not None`) -> retornar `409 Conflict` (`CUPON_YA_ASIGNADO_O_USADO`).
  - `FAILURE(validation_error)`: `cupon_id` o `paciente_id` inexistentes -> retornar `404 Not Found`.

**Observable states during this step**:
  - Customer/Actor sees:
    - **Médico**: El **cupón** figura como "Asignado al paciente `<nombre apellido>`".
    - **Paciente**: Ve el **cupón** disponible y un **aviso** en su bandeja de entrada.
  - Operator sees: Actualización de `cupones.paciente_id` en base de datos.
  - Database:
    - `cupones`: `medico_id = 12`, `paciente_id = 45`, `usado = False`, `updated_at = now()`.
    - `avisos`: nueva fila para `paciente.usuario_id` informando el código de cupón asignado.
  - Logs: `[cupon_service] step=1_asignar_paciente cupon_id=105 medico_id=12 paciente_id=45`

---

### STEP 2: Inicio de pago del presupuesto y bloqueo local del cupón
**Actor**: **Paciente** -> Router (`pagos.py`) -> Servicio (`pago_service.py`) -> Repositorio (`economia_repo.py`)
**Action**: El **paciente** solicita pagar el **presupuesto** de su `estudio_id` indicando `codigo_cupon`. El repositorio verifica que el `Estudio` pertenezca al **paciente**, que esté en `EstadoEstudio.CREADO` (o `EstadoEstudio.AUTORIZADO`), que exista `Presupuesto` emitido sin un `Pago` activo (`anulado == False`), y obtiene el `Cupon` por `codigo` con `SELECT ... FOR UPDATE NOWAIT` verificando que `cupon.paciente_id == paciente.id` y `cupon.usado == False`.
**Timeout**: `2s`
**Input**:
```json
{
  "estudio_id": 88,
  "paciente_autenticado_id": 45,
  "codigo_cupon": "EXOMA-2026-88412"
}
```
**Output on SUCCESS**: `{ estudio: Estudio, presupuesto: Presupuesto, cupon: Cupon }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El `Estudio` no pertenece al **paciente** autenticado, o el `Cupon` está asignado a otro `paciente_id` -> retornar `403 Forbidden` (`CUPON_AJENO` o `ESTUDIO_AJENO`).
  - `FAILURE(invalid_state)`:
    - El `Estudio` no tiene `Presupuesto` emitido -> retornar `409 Conflict` (`PRESUPUESTO_NO_EMITIDO`).
    - Ya existe un `Pago` con `anulado == False` para ese `Presupuesto` -> retornar `409 Conflict` (`PRESUPUESTO_YA_PAGADO`).
    - El `Cupon` tiene `usado == True` -> retornar `409 Conflict` (`CUPON_YA_UTILIZADO`).
  - `FAILURE(conflict)`: Otra transacción concurrente está intentando usar el mismo `Cupon` o pagar el mismo `Presupuesto` (`LockNotAvailable`) -> retornar `409 Conflict` (`OPERACION_EN_CURSO`, `retryable=True`).
  - `FAILURE(validation_error)`: `codigo_cupon` no existe en la tabla `cupones` -> retornar `404 Not Found` (`CUPON_NO_ENCONTRADO`).

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: Botón de pago deshabilitado con estado "Validando cupón y procesando pago...".
  - Operator sees: Transacción iniciada sobre `cupones` y `presupuestos`.
  - Database: Lectura con bloqueo de fila sobre `cupones`; sin escrituras aún.
  - Logs: `[pago_service] step=2_validacion_previa estudio_id=88 cupon_codigo=EXOMA-2026-88412`

---

### STEP 3: Consulta de vigencia del cupón en la API de cupones
**Actor**: Servicio (`pago_service.py`) -> Cliente API de Cupones (`cupones_client.py`) -> **API de cupones**
**Action**: Consulta `GET /external/vouchers/{codigo}/vigencia` en la **API de cupones** para confirmar que el **cupón** sigue vigente y no ha expirado ni sido revocado externamente.
**Timeout**: `4s` por intento (hasta 2 reintentos con backoff de `0.4s`, `0.8s`).
**Input**: `{ codigo: "EXOMA-2026-88412" }`
**Output on SUCCESS**: `{ codigo: "EXOMA-2026-88412", vigente: True, descuento_porcentaje: Decimal("25.00") }` -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(invalid_state / cupón vencido)`: La **API de cupones** responde `vigente == False` (expirado o ya usado) -> retornar `409 Conflict` (`CUPON_NO_VIGENTE`, `retryable=False`), sin registrar el pago.
  - `FAILURE(timeout)`: Timeout tras reintentos -> retornar `504 Gateway Timeout` (`CUPONES_API_TIMEOUT`, `retryable=True`), liberando la transacción sin aplicar cargos.
  - `FAILURE(transient_external_error)`: Error `5xx` en la **API de cupones** -> retornar `502 Bad Gateway` (`CUPONES_API_UNAVAILABLE`, `retryable=True`).

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: Indicador "Verificando vigencia del cupón...".
  - Operator sees: Request `GET /external/vouchers/EXOMA-2026-88412/vigencia`.
  - Database: Sin cambios persistidos.
  - Logs: `[cupones_client] step=3_consulta_vigencia codigo=EXOMA-2026-88412 vigente=true`

---

### STEP 4: Cálculo del descuento acumulado (Obra social + Cupón) y consumo en API de cupones
**Actor**: Servicio (`pago_service.py`) -> Cliente API de Cupones (`cupones_client.py`) -> **API de cupones**
**Action**:
  1. Calcula la cobertura de la **obra social** (si el `Estudio` tiene `obra_social_id` autorizada):
     `cobertura_obra_social_usd = round(presupuesto.monto_total_usd * (obra_social.porcentaje_cobertura / 100), 2)` (o `0.00` si es pago particular sin cobertura).
  2. Calcula el descuento del **cupón** acumulable con la **obra social**:
     `descuento_bruto_usd = round(presupuesto.monto_total_usd * (cupon.descuento_porcentaje / 100), 2)`
     `remanente_tras_os = presupuesto.monto_total_usd - cobertura_obra_social_usd`
     `descuento_cupon_usd = min(descuento_bruto_usd, remanente_tras_os)`
     `monto_usd = max(Decimal("0.00"), presupuesto.monto_total_usd - cobertura_obra_social_usd - descuento_cupon_usd)`
  3. Envía `POST /external/vouchers/{codigo}/consumir` a la **API de cupones** para notificar que el **cupón** fue usado y que venza inmediatamente.
**Timeout**: `4s` por intento (hasta 2 reintentos en caso de fallo de red).
**Input**:
```json
{
  "codigo": "EXOMA-2026-88412",
  "estudio_id": 88,
  "presupuesto_id": 51,
  "monto_total_usd": "500.00",
  "cobertura_obra_social_usd": "200.00",
  "descuento_cupon_usd": "125.00",
  "monto_final_paciente_usd": "175.00"
}
```
**Output on SUCCESS**: `{ consumido_en_api: True, timestamp_vencimiento: datetime }` -> GO TO STEP 5
**Output on FAILURE**:
  - `FAILURE(conflict)`: La **API de cupones** devuelve `409 Conflict` porque el cupón acaba de ser consumido en otra petición -> abortar sin crear `Pago`, retornar `409 Conflict` (`CUPON_YA_CONSUMIDO`).
  - `FAILURE(timeout / external_error)`: Fallo al vencer el cupón en la **API de cupones** -> abortar antes de persistir el `Pago` y retornar `502`/`504` (`retryable=True`) para mantener consistencia estricta entre la API externa y la base de datos local.

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: Desglose de importes ("Aplicando descuento del cupón y registrando pago...").
  - Operator sees: Llamada `POST /external/vouchers/EXOMA-2026-88412/consumir` exitosa.
  - Database: El **cupón** ya figura vencido en la **API de cupones**; pendiente de `COMMIT` en PostgreSQL en `STEP 5`.
  - Logs: `[pago_service] step=4_calculo_y_consumo estudio_id=88 total=500.00 os=200.00 cupon=125.00 neto=175.00`

---

### STEP 5: Persistencia atómica del Pago y marcación del Cupón como usado
**Actor**: Servicio (`pago_service.py`) -> Repositorio (`economia_repo.py`) -> PostgreSQL
**Action**: En una única transacción en PostgreSQL:
  1. Inserta una fila en `pagos` con `presupuesto_id`, `tipo = TipoPago.PARTICULAR` (o `TipoPago.OBRA_SOCIAL` según corresponda), `monto_usd`, `cupon_id = cupon.id`, `descuento_cupon_usd`, `cobertura_obra_social_usd`, `anulado = False`, `fecha = now()`.
  2. Actualiza la fila en `cupones`: `usado = True`, `usado_en = now()`.
  3. Ejecuta `COMMIT`.
**Timeout**: `3s`
**Input**: `{ presupuesto_id: 51, cupon_id: 105, monto_usd: Decimal("175.00"), descuento_cupon_usd: Decimal("125.00"), cobertura_obra_social_usd: Decimal("200.00") }`
**Output on SUCCESS**: `{ pago: Pago, cupon: Cupon, habilitado_sacar_turno: True }` -> Retornar `201 Created` al **paciente** (FIN DEL WORKFLOW).
**Output on FAILURE**:
  - `FAILURE(database_error / timeout)`: Falla el `COMMIT` en PostgreSQL luego de haber vencido el cupón en la **API de cupones** -> ejecutar `ABORT_CLEANUP`.

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: Comprobante de pago con el monto total, cobertura de **obra social**, descuento del **cupón**, monto final abonado y botón habilitado para **Sacar turno**.
  - Operator sees: Registro financiero en `pagos` con `anulado = False` y `cupones.usado = True`.
  - Database:
    - Tabla `pagos`: nueva fila con `presupuesto_id`, `tipo`, `monto_usd`, `cupon_id`, `descuento_cupon_usd`, `cobertura_obra_social_usd`, `anulado = False`, `fecha`.
    - Tabla `cupones`: `usado = True`, `usado_en = now()`, `updated_at = now()`.
    - Tabla `estudios`: `estado` permanece en `EstadoEstudio.CREADO` (o `EstadoEstudio.AUTORIZADO`) y queda habilitado para pasar a `EstadoEstudio.TURNO_SACADO` cuando el **paciente** reserve su **turno**.
  - Logs: `[economia_repo] step=5_pago_registrado pago_id=<id> estudio_id=88 cupon_id=105 monto_usd=175.00`

---

### ABORT_CLEANUP: Reversión ante fallo en STEP 5 tras consumir cupón en API externa
**Triggered by**: Error de base de datos en `STEP 5` después de que `STEP 4` consumió el **cupón** en la **API de cupones**.
**Actions** (in order):
  1. Ejecutar `db.session.rollback()` para revertir cualquier inserción parcial en `pagos` y actualización en `cupones`.
  2. Invocar `cupones_client.restaurar_cupon(codigo)` (`POST /external/vouchers/{codigo}/restaurar`) en la **API de cupones** para rehabilitar la vigencia del cupón que no llegó a aplicarse en un pago persistido.
  3. Si la restauración externa falla, emitir log `CRITICAL` (`VOUCHER_DESYNC_ALERT`) con `cupon_id`, `codigo`, `paciente_id` y `estudio_id` para intervención de soporte.
**What customer/actor (**Paciente**) sees**: Mensaje de error indicando que el pago no pudo completarse y que no se realizó ningún cargo; su cupón permanece asignado.
**What operator sees**: Alerta `VOUCHER_DESYNC_ALERT` o confirmación de compensación exitosa en logs.

---

## State Transitions

```
Cupon (cupones):
  [Creado (medico_id=NULL, paciente_id=NULL, usado=False)]
    -- (Gerente médico asigna a médico) --> [Asignado a Médico (medico_id=<M>, paciente_id=NULL, usado=False)]
    -- (Médico asigna a paciente - STEP 1) --> [Asignado a Paciente (medico_id=<M>, paciente_id=<P>, usado=False)]
    -- (Paciente paga presupuesto aplicando cupón - STEP 2 a 5) --> [Usado / Vencido (usado=True, usado_en=now())]

Pago (pagos):
  [Inexistente]
    -- (STEP 5 exitoso) --> [Registrado (anulado=False, cupon_id=<C>, descuento_cupon_usd=<D>, cobertura_obra_social_usd=<OS>, monto_usd=<M>)]

Estudio (estudios.estado):
  [EstadoEstudio.CREADO] -- (Pago particular con cupón registrado en `pagos`) --> [EstadoEstudio.CREADO (con pago activo -> habilitado para Sacar turno -> pasará a EstadoEstudio.TURNO_SACADO)]
  [EstadoEstudio.AUTORIZADO] -- (Copago con cupón registrado en `pagos`) --> [EstadoEstudio.AUTORIZADO (habilitado para Sacar turno -> pasará a EstadoEstudio.TURNO_SACADO)]
```

---

## Handoff Contracts

### 1. Médico -> Backend: Asignar cupón a paciente
**Endpoint**: `PATCH /api/cupones/{cupon_id}/asignar-paciente`
**Payload**:
```json
{
  "paciente_id": 45
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "id": 105,
    "codigo": "EXOMA-2026-88412",
    "descuento_porcentaje": 25.00,
    "gerente_id": 4,
    "medico_id": 12,
    "paciente_id": 45,
    "usado": false,
    "vigente_hasta": "2026-12-31T23:59:59Z"
  }
}
```
**Failure response** (`403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "El cupón ya fue asignado a un paciente o ya fue utilizado.",
  "code": "CUPON_YA_ASIGNADO_O_USADO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: No modificar `cupones.paciente_id`; informar al **médico** en la interfaz.

---

### 2. Paciente -> Backend: Pagar presupuesto aplicando cupón
**Endpoint**: `POST /api/estudios/{estudio_id}/pagos`
**Payload**:
```json
{
  "codigo_cupon": "EXOMA-2026-88412"
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "pago_id": 301,
    "estudio_id": 88,
    "presupuesto_id": 51,
    "tipo": "particular",
    "monto_total_presupuesto_usd": 500.00,
    "cobertura_obra_social_usd": 200.00,
    "descuento_cupon_usd": 125.00,
    "monto_usd": 175.00,
    "cupon_id": 105,
    "codigo_cupon": "EXOMA-2026-88412",
    "anulado": false,
    "fecha": "2026-10-28T20:05:12Z",
    "habilitado_sacar_turno": true
  }
}
```
**Failure response** (`403` / `404` / `409` / `422` / `502` / `504`):
```json
{
  "ok": false,
  "error": "El cupón informado ya no se encuentra vigente según la API de cupones.",
  "code": "CUPON_NO_VIGENTE",
  "retryable": false
}
```
**Timeout**: `10s`
**ON FAILURE**: Si `retryable == true`, permitir al **paciente** reintentar el pago; si el cupón no es vigente, permitir pagar sin cupón o ingresar otro código.

---

### 3. Backend (`cupones_client`) -> API de cupones (Validación y Consumo)
**Endpoint 3A (Consultar vigencia)**: `GET /external/vouchers/{codigo}/vigencia`
**Success response** (`200 OK`):
```json
{
  "codigo": "EXOMA-2026-88412",
  "vigente": true,
  "descuento_porcentaje": 25.00,
  "vigente_hasta": "2026-12-31T23:59:59Z"
}
```
**Endpoint 3B (Consumir / Vencer cupón)**: `POST /external/vouchers/{codigo}/consumir`
**Payload**:
```json
{
  "usado_en": "2026-10-28T20:05:11Z",
  "estudio_id": 88,
  "paciente_id": 45
}
```
**Success response** (`200 OK`):
```json
{
  "codigo": "EXOMA-2026-88412",
  "vigente": false,
  "usado": true,
  "usado_en": "2026-10-28T20:05:11Z"
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "El cupón ya se encuentra vencido o utilizado",
  "code": "CUPON_NO_VIGENTE",
  "retryable": false
}
```
**Timeout**: `4s` por llamada.
**ON FAILURE**: Abortar el registro de `Pago` en PostgreSQL y devolver error controlado al cliente.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Marcación de consumo en **API de cupones** (`vigente = false`) | Step 4 | `ABORT_CLEANUP` | `POST /external/vouchers/{codigo}/restaurar` vía `cupones_client` + alerta `VOUCHER_DESYNC_ALERT` si falla |
| Fila en `pagos` y cambio `cupones.usado = True` (en sesión SQLAlchemy) | Step 5 | `ABORT_CLEANUP` | `db.session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | El modelo `Pago` en `app/src/core/models/economia.py` ya incluye `cupon_id`, `descuento_cupon_usd` y `cobertura_obra_social_usd`, soportando de forma nativa la acumulación entre descuento de **cupón** y cobertura de **obra social**. | Low | STEP 4, STEP 5 | La especificación mapea exactamente los 3 importes (`monto_usd`, `descuento_cupon_usd`, `cobertura_obra_social_usd`) sobre `Pago`. |
| RC-2 | El LEL establece que `EstadoEstudio` solo pasa a `Turno sacado` cuando el **paciente** reserva el **turno** (`Sacar turno`), no al pagar. | Medium | State Transitions, STEP 5 | Confirmado: el pago con cupón inserta en `pagos` (`anulado = False`) y habilita la acción `Sacar turno`, manteniendo `Estudio.estado` en `Creado` (o `Autorizado`) hasta que el paciente elija su turno. |
| RC-3 | Si la suma de `ObraSocial.porcentaje_cobertura` + `Cupon.descuento_porcentaje` supera el `100%`, el monto a pagar no debe ser negativo. | Medium | STEP 4 | Se especificó `descuento_cupon_usd = min(descuento_bruto_usd, remanente_tras_os)` y `monto_usd >= 0.00`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Asignación de cupón por el médico al paciente | `PATCH /api/cupones/{id}/asignar-paciente` por el médico titular del cupón | Retorna `200 OK`, actualiza `cupones.paciente_id = paciente.id` y genera `Aviso` para el paciente. |
| `TC-02`: Happy path – Pago particular aplicando cupón vigente | `POST /api/estudios/{id}/pagos` con `codigo_cupon` de `20%` sobre presupuesto de `500 USD` (sin obra social) | Consulta vigencia y vence cupón en **API de cupones**; crea `Pago` con `descuento_cupon_usd=100.00`, `cobertura_obra_social_usd=0.00`, `monto_usd=400.00`, y marca `cupones.usado=True`. |
| `TC-03`: Happy path – Acumulación de cupón con cobertura de obra social | `POST /api/estudios/{id}/pagos` con `ObraSocial` al `40%` (`200 USD`) + `Cupon` al `25%` (`125 USD`) sobre presupuesto de `500 USD` | Crea `Pago` con `cobertura_obra_social_usd=200.00`, `descuento_cupon_usd=125.00` y `monto_usd=175.00`; marca `cupones.usado=True`. |
| `TC-04`: Tope del 100% cuando cupón + obra social superan el total | `ObraSocial` cubre `80%` (`400 USD`) y `Cupon` es de `50%` (`250 USD` teóricos) sobre `500 USD` | `cobertura_obra_social_usd=400.00`, `descuento_cupon_usd=100.00` (topeado al remanente), `monto_usd=0.00` (nunca negativo). |
| `TC-05`: Rechazo por intentar usar un cupón asignado a otro paciente | `POST /api/estudios/{id}/pagos` con `codigo_cupon` cuyo `cupon.paciente_id` pertenece a otro paciente | Retorna `403 Forbidden` (`CUPON_AJENO`), no llama a la **API de cupones** ni crea fila en `pagos`. |
| `TC-06`: Rechazo cuando la API de cupones informa que el cupón no está vigente | `POST /api/estudios/{id}/pagos` cuando `GET /external/vouchers/{codigo}/vigencia` devuelve `vigente=False` | Retorna `409 Conflict` (`CUPON_NO_VIGENTE`), no invoca `/consumir` ni inserta en `pagos`. |
| `TC-07`: Intento de reutilizar un cupón ya usado (`cupon.usado == True`) | Segundo `POST /api/estudios/{id}/pagos` con el mismo `codigo_cupon` | Retorna `409 Conflict` (`CUPON_YA_UTILIZADO`) en `STEP 2` antes de contactar a la API externa. |
| `TC-08`: Fallo de BD en `STEP 5` ejecuta compensación en `ABORT_CLEANUP` | Simulación de `OperationalError` al hacer `commit()` en `pagos` tras consumir el cupón en `STEP 4` | Se hace `rollback()` en BD, se invoca `restaurar_cupon` en `cupones_client` y no queda pago huérfano. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Cuando el **paciente** sube el PDF con QR o ingresa el código numérico, el frontend o el router extrae el `codigo` unificado (`Cupon.codigo`) para procesarlo. | Verificado en `app/src/core/models/economia.py` (`codigo: Mapped[str] = mapped_column(String(80), unique=True) # codigo numerico o contenido del QR`). | Bajo; ambos formatos se normalizan sobre `Cupon.codigo`. |
| A2 | La acumulación de descuento de **cupón** y **obra social** se calcula sobre el `monto_total_usd` del `Presupuesto`, truncando el descuento al saldo remanente para que el monto a pagar nunca sea menor que `0.00 USD`. | Verificado en `.ai/2-Glosario_LEL.md` ("se acumula con la cobertura de la obra social") y `.ai/3-Escenarios.md#Escenario-30`. | Bajo. |

## Open Questions

- Si un **paciente** aplica un **cupón** en un pago y posteriormente pierde el pago por faltar 5 veces al turno de extracción (`Pago.anulado = True`, Escenario 33), ¿el **cupón** permanece definitivamente vencido (`usado = True`)? *(Se asume que sí: el cupón ya fue consumido en el pago anulado y no se rehabilita).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada alineada con `Cupon`, `Presupuesto`, `Pago` y `ObraSocial` en `app/src/core/models/economia.py`. | Aprobada. |
