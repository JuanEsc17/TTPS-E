# WORKFLOW: Escenario 12 – Formar un sample-set de muestras
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-12-Formar-un-sample-set-de-muestras`

## Símbolos LEL utilizados

| Categoría | Símbolo LEL | Modelo / Tabla en `app/src/core/models/` |
|---|---|---|
| **Sujeto** | `Administrativo` | `Usuario` (`Rol.ADMINISTRATIVO`) en `usuarios` (receptor de aviso cuando el lote se cierra) |
| **Objeto** | `Muestra` | `Muestra` en `muestras` (`ML_MINIMOS_TUBO = Decimal("2")`) |
| **Objeto** | `Sample set` | `SampleSet` en `sample_sets` (`EstadoSampleSet`, `MUESTRAS_POR_SAMPLE_SET = 10`) |
| **Objeto** | `Estudio` | `Estudio` en `estudios` |
| **Objeto** | `Pompe urgente` | `Estudio.es_pompe_urgente` / `SampleSet.es_pompe_urgente` |
| **Objeto** | `CSV` | `SampleSet.csv_path` (disparado al cerrar el `Sample set`) |
| **Objeto** | `Autorización del Ministerio` | `SampleSet.autorizacion_ministerio_pdf_path` |
| **Verbo** | `Armar sample set` | Servicio `armar_sample_set` (`LogisticaService`) |
| **Verbo** | `Remuestrear` | Desvío automático al Escenario 10 si `muestra.mililitros < 2` |
| **Estado** | `En laboratorio central` | `EstadoEstudio.EN_LAB_CENTRAL` (`"En laboratorio central"`) |
| **Estado** | `En espera de retiro` | `EstadoEstudio.EN_ESPERA_RETIRO` (`"En espera de retiro"`) |
| **Estado** | `Remuestreo requerido` | `EstadoEstudio.REMUESTREO_REQUERIDO` (`"Remuestreo requerido"`) |

---

## Overview

- **Objetivo**: Agrupar automáticamente las `Muestra`s recibidas en el laboratorio central en conjuntos de diez (`MUESTRAS_POR_SAMPLE_SET = 10`) dentro de un `Sample set` para su envío sin multa a Corea.
- **Contexto**: Las `Muestra`s llegaron al laboratorio central entregadas por el `Transportista` (Escenario 11) y sus `Estudio`s están en estado `En laboratorio central`. El sistema debe agruparlas automáticamente en lotes de hasta 10 muestras y mantener el `Sample set` sellado e inmutable una vez cerrado y pasado al siguiente estado (`En espera de retiro`).
- **Recursos**: `Muestra` (`muestras`), `Sample set` (`sample_sets`), `Estudio` (`estudios`).
- **Episodios**:
  1. El sistema recibe las `Muestra`s en el laboratorio central y verifica que sean aptas (`mililitros >= 2`).
  2. El sistema agrupa las `Muestra`s en conjuntos de hasta diez (`MUESTRAS_POR_SAMPLE_SET = 10`).
  3. El sistema crea o actualiza el `Sample set` correspondiente y, al llegar a 10 muestras (o ante un `Pompe urgente`), lo cierra y pasa sus `Estudio`s a `En espera de retiro`.
  4. El sistema mantiene el `Sample set` sin modificar una vez iniciado el siguiente estado (`EstadoSampleSet.CERRADO` / `EstadoEstudio.EN_ESPERA_RETIRO`).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| Sistema (`LogisticaService`) | Actor principal: ejecuta de forma 100% automática la agrupación de `Muestra`s en `SampleSet` al registrarse su llegada al laboratorio central. |
| `Administrativo` | Visualiza el `Sample set` en formación o cerrado (`En espera de retiro`) y recibe un `Aviso` cuando un `Sample set` se cierra. |
| Capa `router` (`Flask Blueprint`) | Expone los endpoints de consulta de `SampleSet` (`GET /api/sample-sets`, `GET /api/sample-sets/{id}`) y el registro de mililitros al recepcionar muestras. |
| Capa `service` (`LogisticaService`) | Aplica las reglas `MUESTRAS_POR_SAMPLE_SET = 10` y `ML_MINIMOS_TUBO = Decimal("2")`, gestiona el cierre del lote y garantiza su inmutabilidad posterior. |
| Capa `repo` (`SampleSetRepo`, `MuestraRepo`, `EstudioRepo`, `AvisoRepo`) | Ejecuta operaciones atómicas con bloqueo `SELECT ... FOR UPDATE` sobre `sample_sets`, `muestras` y `estudios` en `PostgreSQL`. |

---

## Prerequisites

- Una o más `Muestra`s acaban de llegar al laboratorio central (`muestra.llegada_lab_central IS NOT NULL`, `muestra.motivo_descarte IS NULL`, `muestra.sample_set_id IS NULL`).
- Los `Estudio`s asociados a dichas `Muestra`s se encuentran en `EstadoEstudio.EN_LAB_CENTRAL`.
- La base de datos `PostgreSQL` se encuentra disponible.

---

## Trigger

Evento interno disparado automáticamente al finalizar el **STEP 3 del Escenario 11** (`marcar_llegada_lab_central`), o al confirmarse la medición de mililitros de una `Muestra` en el laboratorio central (`POST /api/logistica/muestras/{muestra_id}/recepcion-lab-central`).

---

## Workflow Tree

### STEP 1: Validación de aptitud física y volumen de cada Muestra recibida
**Actor**: `service` (`LogisticaService.procesar_ingreso_muestra_lab_central`) -> `repo` (`MuestraRepo`, `EstudioRepo`)
**Action**: Para cada `Muestra` recién ingresada al laboratorio central:
1. Verifica que `estudio.estado == EstadoEstudio.EN_LAB_CENTRAL`, que `muestra.motivo_descarte IS NULL` y que `muestra.sample_set_id IS NULL`.
2. Si `muestra.mililitros` está informado y es `< ML_MINIMOS_TUBO` (`Decimal("2")`), la muestra **no se incluye** en ningún `SampleSet`: se invoca automáticamente el flujo del **Escenario 10** (`Remuestrear un estudio`) con `MotivoDescarte.VOLUMEN_INSUFICIENTE`, pasando el `Estudio` a `EstadoEstudio.REMUESTREO_REQUERIDO`.
3. Si `muestra.mililitros is None` o `muestra.mililitros >= Decimal("2")`, la muestra es apta para integrar un `SampleSet`.
**Timeout**: 3s
**Input**: `{ muestra_id: 149, estudio_id: 42, mililitros: "4.50" }`
**Output on SUCCESS**:
  - Si `mililitros >= 2.00`: Muestra apta -> GO TO STEP 2.
  - Si `mililitros < 2.00`: Muestra descartada -> Desvío a Escenario 10 (`EstadoEstudio.REMUESTREO_REQUERIDO`), fin del flujo para esta muestra.
**Output on FAILURE**:
  - `FAILURE(invalid_state)`: `estudio.estado != EstadoEstudio.EN_LAB_CENTRAL` o la muestra ya tiene `motivo_descarte IS NOT NULL` -> retornar error `409 Conflict` (`code: "MUESTRA_NO_APTA_PARA_SAMPLE_SET"`).
  - `FAILURE(conflict)`: `muestra.sample_set_id IS NOT NULL` (la muestra ya fue agrupada en un `SampleSet` por otra ejecución concurrente) -> operación idempotente: retornar el `sample_set_id` actual sin duplicar asignación.

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: `Estudio` en `En laboratorio central` (o `Remuestreo requerido` si `< 2 ml`).
  - Operator (`Administrativo`) sees: `Muestra` validada en recepción del laboratorio central.
  - Database: `muestras.mililitros = 4.50`, `muestras.llegada_lab_central IS NOT NULL`.
  - Logs: `[logistica_service] muestra_validada_para_sample_set muestra_id=149 estudio_id=42 ml=4.50`

---

### STEP 2: Obtención o creación del Sample Set abierto con control de concurrencia
**Actor**: `service` (`LogisticaService.armar_sample_set`) -> `repo` (`SampleSetRepo`) -> `PostgreSQL`
**Action**:
1. Busca en la tabla `sample_sets` el registro con `estado == EstadoSampleSet.ABIERTO` aplicando bloqueo de fila `SELECT ... FOR UPDATE` para serializar llegadas simultáneas de múltiples transportistas.
2. Verifica que la cantidad de muestras válidas (`motivo_descarte IS NULL`) actualmente asociadas a ese `SampleSet` sea `< MUESTRAS_POR_SAMPLE_SET` (`10`).
3. Si no existe ningún `SampleSet` en `EstadoSampleSet.ABIERTO` (porque todos los anteriores ya se cerraron), inserta una nueva fila en `sample_sets` con `estado = EstadoSampleSet.ABIERTO`, `es_pompe_urgente = False`, `cerrado_en = None`.
**Timeout**: 3s
**Input**: `{ muestra_id: 149 }`
**Output on SUCCESS**: `{ sample_set_abierto }` (con `< 10` muestras) -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(invariant_violation)`: Se encuentra un `SampleSet` con `estado == EstadoSampleSet.CERRADO` o `EN_VIAJE_COREA` intentando recibir muestras -> rechazar inmediatamente (`code: "SAMPLE_SET_INMUTABLE"`); un `SampleSet` cerrado jamás puede reabrirse ni admitir nuevas muestras.
  - `FAILURE(timeout)`: Bloqueo `FOR UPDATE` supera 3s -> reintentar hasta 2 veces con backoff de 300ms; si persiste, `ABORT_CLEANUP`.

**Observable states during this step**:
  - Customer/Actor sees: Sin cambios visibles para el `Paciente` (`En laboratorio central`).
  - Operator (`Administrativo`) sees: `SampleSet` en estado `abierto` en el panel de laboratorio central.
  - Database: Tabla `sample_sets` cuenta con un registro activo con `estado = 'abierto'` bloqueado para la transacción actual.
  - Logs: `[logistica_service] sample_set_abierto_seleccionado sample_set_id=12 muestras_actuales=9`

---

### STEP 3: Asociación de la Muestra al Sample Set y evaluación de cierre (lote de 10)
**Actor**: `service` (`LogisticaService.armar_sample_set`) -> `repo` (`SampleSetRepo`, `MuestraRepo`, `EstudioRepo`, `AvisoRepo`)
**Action**:
1. Asigna `muestra.sample_set_id = sample_set.id` en la tabla `muestras`.
2. Si el `Estudio` de la muestra tiene `estudio.es_pompe_urgente == True`, marca `sample_set.es_pompe_urgente = True` (ver detalle en Escenario 14).
3. Recuenta las muestras válidas del `SampleSet` (`cantidad = len([m for m in sample_set.muestras if m.motivo_descarte is None])`).
4. **Rama A – Lote aún incompleto (`cantidad < 10` y `not sample_set.es_pompe_urgente`)**:
   - Mantiene `sample_set.estado = EstadoSampleSet.ABIERTO`.
   - Mantiene `estudio.estado = EstadoEstudio.EN_LAB_CENTRAL` para todas las muestras del lote (esperando a que ingresen más muestras ese mismo día o en los días siguientes hasta llegar a 10).
5. **Rama B – Lote completo (`cantidad == 10`) o cierre urgente (`sample_set.es_pompe_urgente == True`)**:
   - Sella el lote: actualiza `sample_set.estado = EstadoSampleSet.CERRADO` y `sample_set.cerrado_en = now()`.
   - Actualiza el estado de **todos** los `Estudio`s cuyas muestras integran ese `SampleSet` de `EstadoEstudio.EN_LAB_CENTRAL` a `EstadoEstudio.EN_ESPERA_RETIRO`.
   - Crea un `Aviso` interno (`CanalAviso.APP`) para los usuarios con `Rol.ADMINISTRATIVO` informando que el `SampleSet` está cerrado y `En espera de retiro`.
   - Si en la misma entrega del `Transportista` quedaron más muestras pendientes de agrupar, abre un nuevo `SampleSet` (`EstadoSampleSet.ABIERTO`) y repite STEP 2–3 para las muestras restantes.
**Timeout**: 5s
**Input**: `{ sample_set_id: 12, muestra_id: 149 }`
**Output on SUCCESS**:
  - Si Rama A (`cantidad < 10`): `{ sample_set_id: 12, estado: "abierto", cantidad_muestras: cantidad }` -> FIN DEL WORKFLOW (aguarda nuevas muestras).
  - Si Rama B (`cantidad == 10` o `es_pompe_urgente`): `{ sample_set_id: 12, estado: "cerrado", cantidad_muestras: cantidad }` -> GO TO STEP 4.
**Output on FAILURE**:
  - `FAILURE(database_error)`: Error al actualizar `muestras`, `sample_sets` o `estudios` -> `ABORT_CLEANUP` (`session.rollback()`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees:
    - Rama A: Su `Estudio` permanece en `En laboratorio central`.
    - Rama B: Su `Estudio` avanza a `En espera de retiro`.
  - Operator (`Administrativo`) sees:
    - Rama A: `SampleSet #12` en estado `abierto` con `N/10` muestras.
    - Rama B: `SampleSet #12` en estado `cerrado` (`10/10` muestras) y sus 10 estudios en `En espera de retiro`.
  - Database:
    - Tabla `muestras`: `sample_set_id = 12`.
    - Tabla `sample_sets`: Si cerró, `estado = 'cerrado'`, `cerrado_en = <timestamp>`.
    - Tabla `estudios`: Si cerró, `estado = 'En espera de retiro'` para los 10 estudios del lote.
  - Logs: `[logistica_service] sample_set_actualizado sample_set_id=12 estado=cerrado cantidad_muestras=10`

---

### STEP 4: Garantía de inmutabilidad post-cierre y disparo de trámites de envío a Corea
**Actor**: `service` (`LogisticaService`)
**Action**:
1. Una vez que `sample_set.estado` pasa a `EstadoSampleSet.CERRADO` (y los estudios a `EstadoEstudio.EN_ESPERA_RETIRO`), el sistema bloquea cualquier intento posterior de agregar o quitar muestras a ese `SampleSet`. Toda nueva muestra que ingrese al laboratorio central con posterioridad se asigna a un **nuevo** `SampleSet` con `estado = EstadoSampleSet.ABIERTO`.
2. Dispara automáticamente los pasos iniciales del **Escenario 13** (generación del archivo `CSV` de pacientes y solicitud de `Autorización del Ministerio` a la `API del Ministerio de Salud`).
**Timeout**: 10s
**Input**: `{ sample_set_id: 12 }`
**Output on SUCCESS**: `{ sample_set_id: 12, estado: "cerrado", inmutable: true }` -> FIN DEL WORKFLOW (continúa en Escenario 13).
**Output on FAILURE**:
  - `FAILURE(immutable_modification_attempt)`: Cualquier llamada que intente asociar una `Muestra` a un `SampleSet` cuyo `estado != EstadoSampleSet.ABIERTO` -> rechazar con HTTP `409 Conflict` (`code: "SAMPLE_SET_CERRADO_INMUTABLE"`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: `Estudio` en estado `En espera de retiro`.
  - Operator (`Administrativo`) sees: `SampleSet #12` sellado, con su `CSV` y `Autorización del Ministerio` listos para programar retiro con `FedEx`.
  - Database: `sample_sets.id = 12` con `estado = 'cerrado'`, `cerrado_en IS NOT NULL`.
  - Logs: `[logistica_service] sample_set_sellado_e_inmutable sample_set_id=12`

---

### ABORT_CLEANUP: Reversión transaccional
**Triggered by**: Fallo de base de datos o timeout de bloqueo en STEP 1, STEP 2 o STEP 3.
**Actions** (in order):
  1. Ejecutar `session.rollback()` en SQLAlchemy.
  2. Mantener la `Muestra` en el laboratorio central (`llegada_lab_central IS NOT NULL`, `sample_set_id = NULL`) y el `Estudio` en `EstadoEstudio.EN_LAB_CENTRAL` para que pueda ser agrupada en el siguiente intento sin pérdida de trazabilidad.
**What customer sees**: `Estudio` en `En laboratorio central`.
**What operator sees**: Alerta en el panel de muestras pendientes de asignación a `SampleSet` en `En laboratorio central`.

---

## State Transitions

```
SampleSet (EstadoSampleSet):
(inexistente)
  -- (STEP 2: primera muestra llega al lab central) -------------> [abierto] (1/10 muestras)
[abierto] (1..9 muestras)
  -- (STEP 3 Rama A: llega muestra 2..9 no urgente) -------------> [abierto] (permanece abierto)
[abierto] (9 muestras)
  -- (STEP 3 Rama B: llega 10ma muestra válida) -----------------> [cerrado] (inmutable; cerrado_en = now())

Estudio (EstadoEstudio):
[En laboratorio central]
  -- (STEP 1: muestra < 2 ml) -----------------------------------> [Remuestreo requerido] (Escenario 10)
[En laboratorio central]
  -- (STEP 3 Rama A: lote aún tiene < 10 muestras) --------------> [En laboratorio central]
[En laboratorio central]
  -- (STEP 3 Rama B: el SampleSet llega a 10 muestras y cierra) -> [En espera de retiro]
```

---

## Handoff Contracts

### 1. `Recepción Lab Central / Transportista` -> `LogisticaService.armar_sample_set` (Recepción y armado automático)
**Endpoint**: `POST /api/logistica/muestras/{muestra_id}/recepcion-lab-central` (o invocación interna directa desde `POST /api/logistica/ordenes-del-dia/{orden_id}/llegada-laboratorio-central`)
**Payload**:
```json
{
  "mililitros": 4.50
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "muestra_id": 149,
  "estudio_id": 42,
  "descartada": false,
  "sample_set": {
    "id": 12,
    "estado": "cerrado",
    "cantidad_muestras": 10,
    "es_pompe_urgente": false,
    "cerrado_en": "2026-10-28T16:10:05"
  },
  "estado_estudio": "En espera de retiro"
}
```
**Failure response** (`400` / `404` / `409`):
```json
{
  "ok": false,
  "error": "El sample-set indicado ya se encuentra cerrado y no admite modificaciones.",
  "code": "SAMPLE_SET_CERRADO_INMUTABLE",
  "retryable": false
}
```
**Timeout**: 5s
**ON FAILURE**: Rollback transaccional; la muestra permanece en `En laboratorio central` sin `sample_set_id`.

---

### 2. `Administrativo (UI)` -> `Backend (router -> service)` (Consultar sample-sets)
**Endpoint**: `GET /api/sample-sets?estado=abierto|cerrado|en_viaje_a_corea`
**Payload**: Query params opcionales `estado`.
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "sample_sets": [
    {
      "id": 12,
      "estado": "cerrado",
      "es_pompe_urgente": false,
      "cantidad_muestras": 10,
      "cerrado_en": "2026-10-28T16:10:05",
      "csv_path": "/storage/sample_sets/sample_set_12.csv",
      "autorizacion_ministerio_pdf_path": "/storage/sample_sets/autorizacion_12.pdf",
      "muestras_ids": [140, 141, 142, 143, 144, 145, 146, 147, 148, 149]
    }
  ]
}
```
**Failure response** (`403`):
```json
{
  "ok": false,
  "error": "Acceso restringido a personal administrativo.",
  "code": "FORBIDDEN",
  "retryable": false
}
```
**Timeout**: 3s
**ON FAILURE**: Retornar error HTTP correspondiente sin mutar estado.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Nuevo registro `SampleSet` en `sample_sets` | Step 2 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Vinculación `muestras.sample_set_id` | Step 3 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Transición de `sample_sets.estado` a `CERRADO` y `estudios.estado` a `EN_ESPERA_RETIRO` | Step 3 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/reglas.py` están definidas las constantes `MUESTRAS_POR_SAMPLE_SET = 10` y `ML_MINIMOS_TUBO = Decimal("2")`. | Low | Overview / STEP 1 & 3 | Se utilizan exactamente dichas constantes del modelo de dominio. |
| RC-2 | En `.ai/3-Escenarios.md` (Escenario 12), el campo `Actores` está vacío porque es un proceso 100% automático del sistema cuando las muestras llegan al laboratorio central (`.ai/1-Entrevista.md` línea 271: `"automáticamente, sin que nadie opere, tiene que dispararse la lógica que le conté de los lotes, que a los lotes le vamos a llamar sample sets"`). | Low | Actors / Trigger | Especificado como proceso automático disparado por la llegada de muestras al laboratorio central. |
| RC-3 | Si un `Transportista` entrega de una sola vez 12 muestras cuando el `SampleSet` actual ya tenía 5 muestras (total 17), un bucle ingenuo podría meter las 17 en el mismo `SampleSet`. | High | STEP 3 | Especificado que al llegar a `MUESTRAS_POR_SAMPLE_SET = 10` se cierra inmediatamente el `SampleSet` actual (`10/10`) y las 7 muestras excedentes crean un nuevo `SampleSet` en `EstadoSampleSet.ABIERTO` (`7/10`). |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Creación de nuevo `SampleSet` abierto al llegar la primera muestra | Ingresa 1 muestra válida (`4.0 ml`) sin ningún `SampleSet` abierto previo | Se crea un `SampleSet` con `estado == EstadoSampleSet.ABIERTO`, `len(sample_set.muestras) == 1`; el `Estudio` permanece en `EstadoEstudio.EN_LAB_CENTRAL`. |
| `TC-02`: Acumulación de muestras sin cerrar lote (`< 10` muestras) | Ingresan 8 muestras adicionales no urgentes al `SampleSet` abierto (total 9) | El `SampleSet` sigue en `EstadoSampleSet.ABIERTO` (`cerrado_en is None`) y los 9 estudios permanecen en `EstadoEstudio.EN_LAB_CENTRAL`. |
| `TC-03`: Cierre automático del `SampleSet` al llegar la décima muestra | Ingresa la muestra número 10 (`3.5 ml`) al `SampleSet` que tenía 9 muestras | `sample_set.estado == EstadoSampleSet.CERRADO`, `sample_set.cerrado_en is not None`, y los **10** `Estudio`s pasan atómicamente a `EstadoEstudio.EN_ESPERA_RETIRO`. |
| `TC-04`: Partición automática en múltiples lotes cuando ingresan más de 10 muestras | `SampleSet` abierto tiene 8 muestras e ingresan 5 muestras nuevas en el mismo viaje | Las primeras 2 completan y cierran el `SampleSet #1` (`10/10`, `CERRADO`, estudios en `EN_ESPERA_RETIRO`); las 3 restantes abren un nuevo `SampleSet #2` (`3/10`, `ABIERTO`, estudios en `EN_LAB_CENTRAL`). |
| `TC-05`: Inmutabilidad de un `SampleSet` cerrado | Llega una nueva muestra luego de que el `SampleSet #1` pasó a `EstadoSampleSet.CERRADO` | El `SampleSet #1` no se modifica jamás; la nueva muestra se asigna a un `SampleSet #2` nuevo. |
| `TC-06`: Exclusión automática de muestra con menos de 2 ml | Ingresa una muestra al laboratorio central con `mililitros = Decimal("1.80")` | La muestra no se agrega al `SampleSet` (`sample_set_id is None`), se marca con `MotivoDescarte.VOLUMEN_INSUFICIENTE` y su `Estudio` pasa a `EstadoEstudio.REMUESTREO_REQUERIDO`. |
| `TC-07`: Concurrencia al cerrar lote entre dos entregas simultáneas | Dos transacciones concurrentes intentan agregar las muestras 10 y 11 al mismo tiempo | El bloqueo `SELECT ... FOR UPDATE` sobre el `SampleSet` abierto garantiza que el primer lote quede exactamente con 10 muestras y la muestra 11 cree un segundo `SampleSet`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Si al finalizar el horario laboral (18:00) un `SampleSet` tiene menos de 10 muestras (y ninguna es `Pompe urgente`), permanece en `EstadoSampleSet.ABIERTO` esperando las muestras de los días hábiles siguientes para no pagar penalidad de envío. | `.ai/1-Entrevista.md` (línea 145: `"Si no se llega a 10 muestras aún si terminó el día hay que esperar al día siguiente para completar ese lote de 10"`) | Low |

## Open Questions

- Ninguna pregunta abierta bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/logistica.py`, `estudios.py`, `enums.py` y `reglas.py`. | Estado marcado como `Approved`. |
