# WORKFLOW: Escenario 14 – Enviar una muestra de Pompe urgente
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-14-Enviar-una-muestra-de-Pompe-urgente`

## Símbolos LEL utilizados

| Categoría | Símbolo LEL | Modelo / Tabla en `app/src/core/models/` |
|---|---|---|
| **Sujeto** | `Administrativo` | `Usuario` (`Rol.ADMINISTRATIVO`) en `usuarios` |
| **Sujeto** | `Transportista` | `Transportista` en `transportistas` / `Usuario` (`Rol.TRANSPORTISTA`) |
| **Sujeto** | `Bioinformático` | `Usuario` (`Rol.BIOINFORMATICO`) (ve primero los estudios `Pompe urgente`) |
| **Objeto** | `Pompe urgente` | `Estudio.es_pompe_urgente == True` (`estudios`) y `SampleSet.es_pompe_urgente == True` (`sample_sets`) |
| **Objeto** | `Patología` | `Patologia` en `patologias` (`nombre == "Pompe"`) |
| **Objeto** | `Paciente` | `Paciente` en `pacientes` (`fecha_nacimiento`: menor de 4 meses) |
| **Objeto** | `Muestra` | `Muestra` en `muestras` |
| **Objeto** | `Sample set` | `SampleSet` en `sample_sets` (lote parcial de 1 a 10 muestras) |
| **Objeto** | `CSV` | `SampleSet.csv_path` |
| **Objeto** | `Autorización del Ministerio` | `SampleSet.autorizacion_ministerio_pdf_path` |
| **Objeto** | `FedEx` | Retiro del paquete urgente (`SampleSet.retiro_fedex_*`) |
| **Verbo** | `Armar sample set` | Cierre inmediato del `Sample set` parcial al ingresar un `Pompe urgente` |
| **Verbo** | `Retirar sample set` | Programación y retiro del paquete hacia Corea |
| **Estado** | `En laboratorio central` | `EstadoEstudio.EN_LAB_CENTRAL` (`"En laboratorio central"`) |
| **Estado** | `En espera de retiro` | `EstadoEstudio.EN_ESPERA_RETIRO` (`"En espera de retiro"`) |
| **Estado** | `En viaje a Corea` | `EstadoEstudio.EN_VIAJE_COREA` (`"En viaje a Corea"`) / `EstadoSampleSet.EN_VIAJE_COREA` |

---

## Overview

- **Objetivo**: Enviar de inmediato a Corea un `Sample set` parcial (con entre 1 y 10 muestras, aprovechando las muestras que ya estuvieran acumuladas en el lote abierto) sin esperar a completar diez muestras cuando ingresa una muestra correspondiente a un caso de `Pompe urgente`.
- **Contexto**: Un `Paciente` con diagnóstico presuntivo de `Patología` `"Pompe"` tiene menos de 4 meses de edad (`Estudio.es_pompe_urgente == True`), situación de riesgo vital en recién nacidos/lactantes. Cuando el `Transportista` entrega su `Muestra` en el laboratorio central, el sistema detecta que es un `Pompe urgente`, la incluye en el `Sample set` abierto actual (por ejemplo, si había 5 muestras, queda un lote de 6; si no había ninguna, queda un lote de 1) y cierra inmediatamente el `Sample set` para gestionar su autorización ministerial y retiro hacia Corea.
- **Recursos**: `Muestra` (`muestras`), `Sample set` parcial (`sample_sets`), `Autorización del Ministerio` (`autorizacion_ministerio_pdf_path`), paquete y datos de retiro (`retiro_fedex_*`).
- **Episodios**:
  1. El sistema identifica el caso de `Pompe urgente` (`estudio.es_pompe_urgente == True`, patología `Pompe` en menor de 4 meses).
  2. Al ingresar la `Muestra` al laboratorio central, el sistema la incorpora al `Sample set` abierto y lo cierra inmediatamente como lote parcial (`sample_set.es_pompe_urgente = True`), emitiendo el `CSV` y la `Autorización del Ministerio`.
  3. El `Administrativo` prepara y programa el envío urgente del `Sample set` parcial.
  4. El servicio de retiro (`FedEx`) retira el paquete en el horario programado.
  5. El sistema cambia el estado del `Sample set` parcial y de todas las `Muestra`s / `Estudio`s incluidos en él a `En viaje a Corea`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Transportista` | Entrega la `Muestra` en el laboratorio central (disparando la recepción en el sistema). |
| Sistema (`EstudioService` / `LogisticaService`) | Determina `estudio.es_pompe_urgente = True` (menor de 4 meses + patología `Pompe`), cierra inmediatamente el `SampleSet` parcial al recibir la muestra en el laboratorio central y gestiona `CSV` + `Autorización del Ministerio`. |
| `Administrativo` | Recibe el `Aviso` prioritario de `Sample set` urgente cerrado y programa su retiro con `FedEx`. |
| `FedEx` (Transportista internacional / módulo de retiro) | Retira el paquete sellado con el `Sample set` parcial y notifica el retiro vía webhook para pasar los estudios a `En viaje a Corea`. |
| Capa `router` -> `service` -> `repo` + `clients` | Capas de aplicación y persistencia sobre `PostgreSQL` y APIs externas (`API del Ministerio de Salud`, `FedEx`). |

---

## Prerequisites

- Existe un `Paciente` en `pacientes` cuya edad al momento del alta del `Estudio` es estrictamente menor a 4 meses (`fecha_referencia < fecha_nacimiento + 4 meses`).
- El `Estudio` en `estudios` tiene `patologia_sospechada` correspondiente a `"Pompe"` y por lo tanto tiene `estudio.es_pompe_urgente == True`.
- El `Estudio` cumplió el circuito único previo (pago o autorización de obra social, reserva de `Turno`, toma de `Muestra` en `Centro de extracción` y traslado por el `Transportista` hasta el laboratorio central).
- La `Muestra` vigente tiene volumen apto (`mililitros >= Decimal("2")`).

---

## Trigger

El `Transportista` registra la llegada al laboratorio central (`POST /api/logistica/ordenes-del-dia/{orden_id}/llegada-laboratorio-central`) o se registra la recepción en el laboratorio central (`POST /api/logistica/muestras/{muestra_id}/recepcion-lab-central`) de una `Muestra` cuyo `Estudio` tiene `es_pompe_urgente == True`.

---

## Workflow Tree

### STEP 1: Identificación del caso de Pompe urgente en el laboratorio central
**Actor**: `service` (`LogisticaService.procesar_ingreso_muestra_lab_central`) -> `repo` (`MuestraRepo`, `EstudioRepo`)
**Action**:
1. Al ingresar la `Muestra` al laboratorio central y validar que su volumen sea `>= ML_MINIMOS_TUBO` (`2.00` ml), el sistema inspecciona `muestra.estudio`.
2. Verifica la condición de `Pompe urgente`: `estudio.es_pompe_urgente == True` (determinada al dar de alta el `Estudio` verificando que `patologia_sospechada.nombre.lower() == "pompe"` y que la edad de `estudio.paciente.fecha_nacimiento` sea `< 4 meses`).
**Timeout**: 2s
**Input**: `{ muestra_id: 155, estudio_id: 48, mililitros: "2.50" }`
**Output on SUCCESS**: `{ muestra_id: 155, estudio_id: 48, es_pompe_urgente: true }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(volumen_insuficiente)`: Si `mililitros < 2.00`, aun siendo un `Pompe urgente`, la muestra no puede enviarse a Corea sin volumen mínimo -> se descarta con `MotivoDescarte.VOLUMEN_INSUFICIENTE` y se dispara el **Escenario 10** (`Remuestrear un estudio`) con notificación urgente al `Paciente` (padre/responsable) y al `Médico`.

**Observable states during this step**:
  - Customer/Actor (`Paciente` / padre responsable) sees: `Estudio` ingresado en `En laboratorio central`.
  - Operator (`Administrativo`) sees: Indicador de prioridad `"POMPE URGENTE (< 4 meses)"` en el estudio `#48`.
  - Database: `estudios.id = 48` con `es_pompe_urgente = True`, `estado = 'En laboratorio central'`.
  - Logs: `[logistica_service] pompe_urgente_detectado estudio_id=48 muestra_id=155 paciente_id=22`

---

### STEP 2: Inclusión en el Sample Set abierto y cierre inmediato del lote parcial
**Actor**: `service` (`LogisticaService.armar_sample_set`) -> `repo` (`SampleSetRepo`, `MuestraRepo`, `EstudioRepo`, `AvisoRepo`)
**Action**:
1. Obtiene con bloqueo `SELECT ... FOR UPDATE` el `SampleSet` actualmente en `EstadoSampleSet.ABIERTO` (que puede tener entre `0` y `9` muestras previas; si no existe ninguno abierto, crea uno nuevo).
2. Agrega la `Muestra` de `Pompe urgente` a ese `SampleSet` (`muestra.sample_set_id = sample_set.id`).
3. De acuerdo con la regla de negocio del LEL (`"Si entra un lote de 5 y aparece este pompe, ¿se manda en este lote aprovechando o se manda solo? Se manda todo el lote. Quedaría un lote de 6"`), **cierra inmediatamente** ese `SampleSet` aunque tenga menos de 10 muestras (`1 <= len(sample_set.muestras) <= 10`):
   - `sample_set.es_pompe_urgente = True`
   - `sample_set.estado = EstadoSampleSet.CERRADO`
   - `sample_set.cerrado_en = now()`
4. Actualiza el estado de **todos** los `Estudio`s cuyas muestras integran ese `SampleSet` parcial (tanto el `Pompe urgente` como las muestras normales que ya estaban en ese lote abierto) de `EstadoEstudio.EN_LAB_CENTRAL` a `EstadoEstudio.EN_ESPERA_RETIRO`.
5. Genera un `Aviso` prioritario en `avisos` para todos los usuarios con `Rol.ADMINISTRATIVO` alertando que se cerró un `SampleSet` parcial por `Pompe urgente`.
**Timeout**: 5s
**Input**: `{ sample_set_id: 13, muestra_urgente_id: 155 }`
**Output on SUCCESS**: `{ sample_set_id: 13, estado: "cerrado", es_pompe_urgente: true, cantidad_muestras: 6, estudios_en_espera_retiro_ids: [43, 44, 45, 46, 47, 48] }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(database_error)`: Fallo en la transacción -> `ABORT_CLEANUP` (`session.rollback()`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`s de los estudios 43..48) sees: Sus `Estudio`s avanzan inmediatamente a `En espera de retiro` sin esperar a completar 10 muestras.
  - Operator (`Administrativo`) sees: `SampleSet #13` cerrado con etiqueta `"POMPE URGENTE (6/10 muestras)"` en estado `cerrado` y estudios en `En espera de retiro`.
  - Database:
    - Tabla `sample_sets`: `id = 13`, `estado = 'cerrado'`, `es_pompe_urgente = True`, `cerrado_en = now()`.
    - Tabla `muestras`: Las 6 muestras tienen `sample_set_id = 13`.
    - Tabla `estudios`: Los 6 estudios tienen `estado = 'En espera de retiro'`.
  - Logs: `[logistica_service] sample_set_parcial_cerrado_por_pompe_urgente sample_set_id=13 cantidad_muestras=6 estudio_urgente_id=48`

---

### STEP 3: Generación automática del CSV y obtención de Autorización del Ministerio para el lote parcial
**Actor**: `service` -> `clients` (`MinisterioSaludClient`) -> `repo` (`SampleSetRepo`)
**Action**:
1. Genera automáticamente el archivo `CSV` incluyendo únicamente los `N` pacientes (`1 <= N <= 10`) que conforman el `SampleSet` parcial cerrado (de modo que el permiso coincida exactamente con los tubos físicos dentro de la bolsa sellada).
2. Envía el `CSV` a la `API del Ministerio de Salud` y guarda el PDF recibido en `sample_set.autorizacion_ministerio_pdf_path`.
**Timeout**: 15s
**Input**: `{ sample_set_id: 13 }`
**Output on SUCCESS**: `{ csv_path: "storage/sample_sets/sample_set_13.csv", autorizacion_ministerio_pdf_path: "storage/sample_sets/autorizacion_ministerio_13.pdf" }` -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(external_api_error)`: Reintentar 3 veces con backoff exponencial (2s, 4s, 8s); si falla, notificar con prioridad alta al `Administrativo`.

**Observable states during this step**:
  - Customer/Actor sees: `Estudio` en `En espera de retiro`.
  - Operator (`Administrativo`) sees: `SampleSet #13` (Pompe urgente) autorizado por el Ministerio de Salud y listo para programar retiro con `FedEx`.
  - Database: `sample_sets.csv_path` y `sample_sets.autorizacion_ministerio_pdf_path` poblados para `id = 13`.
  - Logs: `[ministerio_client] autorizacion_lote_parcial_pompe_recibida sample_set_id=13 cantidad_pacientes=6`

---

### STEP 4: Preparación y programación del envío urgente por el Administrativo
**Actor**: `Administrativo` -> `router` (`POST /api/sample-sets/{sample_set_id}/retiro-fedex`) -> `service` -> `clients` (`FedExClient`) -> `repo`
**Action**: El `Administrativo` sella la bolsa con las `N` muestras del `SampleSet` parcial junto con la `Autorización del Ministerio` y programa el retiro con `FedEx` (lunes a viernes de 09:00 a 18:00). Si mientras tanto ingresan nuevas muestras al laboratorio central, **no se agregan** a este `SampleSet` parcial porque ya está cerrado y sellado (`"No, una vez que el lote ya cambió de estado ya está... la bolsa va con la autorización, se sella y ya no se puede abrir"`, `.ai/1-Entrevista.md` línea 476).
**Timeout**: 10s
**Input**:
```json
{
  "sample_set_id": 13,
  "fecha_retiro": "2026-10-28T17:00:00",
  "lugar_retiro": "Laboratorio Central - Calle 50 Nro 1200, La Plata"
}
```
**Output on SUCCESS**: `{ sample_set_id: 13, retiro_fedex_pedido_id: "FDX-2026-0013" }` -> GO TO STEP 5
**Output on FAILURE**:
  - `FAILURE(validation_error | forbidden | conflict | external_api_error)`: Mismas ramas de validación y recuperación que en STEP 3 del Escenario 13.

**Observable states during this step**:
  - Customer/Actor sees: `Estudio` en `En espera de retiro`.
  - Operator (`Administrativo`) sees: Retiro urgente programado con `FedEx` (`FDX-2026-0013`).
  - Database: `sample_sets` actualizado con `retiro_fedex_fecha`, `retiro_fedex_lugar`, `retiro_fedex_url`, `retiro_fedex_pedido_id`.
  - Logs: `[fedex_client] retiro_pompe_urgente_programado sample_set_id=13 pedido_id="FDX-2026-0013"`

---

### STEP 5: Retiro del paquete y transición del Sample Set parcial a `En viaje a Corea`
**Actor**: `FedEx` -> `router` (`POST /api/webhooks/fedex/sample-sets/{sample_set_id}/retirado`) -> `service` -> `repo`
**Action**: Cuando `FedEx` retira el paquete en el horario programado e invoca el callback:
1. Actualiza `sample_set.estado = EstadoSampleSet.EN_VIAJE_COREA`.
2. Actualiza todos los `Estudio`s incluidos en el `SampleSet` parcial a `EstadoEstudio.EN_VIAJE_COREA`.
3. El flag `estudio.es_pompe_urgente = True` se conserva en `estudios` para que, una vez cargados los `Datos crudos` de Corea (Escenario 15), el estudio aparezca **primero en la lista** de trabajo del `Bioinformático`.
**Timeout**: 5s
**Input**: `{ sample_set_id: 13, pedido_id: "FDX-2026-0013", retirado_en: "2026-10-28T17:00:00" }`
**Output on SUCCESS**: `{ sample_set_id: 13, estado_sample_set: "en_viaje_a_corea", estudios_en_viaje_ids: [43, 44, 45, 46, 47, 48] }` -> FIN DEL WORKFLOW.
**Output on FAILURE**:
  - `FAILURE(unauthorized | invalid_state | database_error)`: Rollback transaccional (`ABORT_CLEANUP`) y respuesta de error correspondiente.

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: `Estudio` en `En viaje a Corea`.
  - Operator (`Administrativo`) sees: `SampleSet #13` parcial (`6/10` muestras, `es_pompe_urgente = True`) en `En viaje a Corea`.
  - Database: `sample_sets.estado = 'en_viaje_a_corea'`; `estudios.estado = 'En viaje a Corea'` para los 6 estudios del paquete.
  - Logs: `[logistica_service] sample_set_pompe_urgente_en_viaje_a_corea sample_set_id=13 estudios=[43,44,45,46,47,48]`

---

### ABORT_CLEANUP: Reversión transaccional
**Triggered by**: Fallo en cualquiera de los pasos de persistencia o comunicación externa.
**Actions** (in order):
  1. Ejecutar `session.rollback()` en SQLAlchemy.
  2. Eliminar archivos parciales de `CSV` o `PDF` no confirmados en base de datos.
  3. Notificar al `Administrativo` en caso de error con servicios externos.
**What customer sees**: Estado consistente previo (`En laboratorio central` o `En espera de retiro`).
**What operator sees**: Alerta prioritaria sobre el lote de `Pompe urgente` para reintento inmediato.

---

## State Transitions

```
SampleSet (EstadoSampleSet):
[abierto] (con 0..9 muestras previas)
  -- (STEP 1-2: ingresa Muestra con estudio.es_pompe_urgente == True) --> [cerrado] (es_pompe_urgente = True, 1..10 muestras, inmutable)
[cerrado]
  -- (STEP 3-5: Autorización del Ministerio + Retiro FedEx) ------------> [en_viaje_a_corea]

Estudio de Pompe urgente y demás Estudios del mismo SampleSet parcial (EstadoEstudio):
[En laboratorio central]
  -- (STEP 2: cierre inmediato del SampleSet parcial) ------------------> [En espera de retiro]
[En espera de retiro]
  -- (STEP 5: retiro del paquete por FedEx) ----------------------------> [En viaje a Corea]
```

---

## Handoff Contracts

### 1. Determinación de `es_pompe_urgente` al crear Estudio y cierre de `SampleSet` parcial al recepcionar Muestra
**Endpoint**: `POST /api/logistica/muestras/{muestra_id}/recepcion-lab-central`
**Payload**:
```json
{
  "mililitros": 2.50
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "muestra_id": 155,
  "estudio_id": 48,
  "es_pompe_urgente": true,
  "sample_set": {
    "id": 13,
    "estado": "cerrado",
    "es_pompe_urgente": true,
    "cantidad_muestras": 6,
    "cerrado_en": "2026-10-28T15:20:00",
    "csv_path": "storage/sample_sets/sample_set_13.csv",
    "autorizacion_ministerio_pdf_path": "storage/sample_sets/autorizacion_ministerio_13.pdf"
  },
  "estudios_en_espera_retiro_ids": [43, 44, 45, 46, 47, 48]
}
```
**Failure response** (`400` / `409`):
```json
{
  "ok": false,
  "error": "La muestra presenta volumen insuficiente (< 2 ml) y requiere remuestreo.",
  "code": "VOLUMEN_INSUFICIENTE_REMUESTREO",
  "retryable": false
}
```
**Timeout**: 15s
**ON FAILURE**: Si el volumen es `< 2 ml`, transicionar a `Remuestreo requerido`; si falla base de datos, rollback.

*(Los contratos de `API del Ministerio de Salud` y `FedEx` son idénticos a los definidos en el Escenario 13, operando aquí con `cantidad_pacientes_autorizados` entre `1` y `10`).*

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Vinculación `muestras.sample_set_id` y cierre de `SampleSet` parcial | Step 2 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Archivos `CSV` y `PDF` del lote parcial | Step 3 | `ABORT_CLEANUP` | `os.remove()` + `session.rollback()` |
| Datos de retiro `FedEx` y transición a `EN_VIAJE_COREA` | Step 4 & 5 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | Tanto `Estudio` (`estudios.py#L31`) como `SampleSet` (`logistica.py#L30`) poseen el campo booleano `es_pompe_urgente: Mapped[bool] = mapped_column(Boolean, default=False)`. | Low | Todos los pasos | Alineado 100%: `Estudio.es_pompe_urgente` identifica el estudio urgente (y ordena la bandeja del bioinformático), mientras que `SampleSet.es_pompe_urgente` documenta por qué ese `SampleSet` se cerró con menos de 10 muestras. |
| RC-2 | En `.ai/1-Entrevista.md` (líneas 442-445 y 475-476), el cliente especifica que si había 5 muestras en el lote abierto y entra el `Pompe urgente`, se envían las 6 juntas cerrando ese lote, y si luego llega una séptima muestra mientras el lote espera a `FedEx`, no se puede abrir la bolsa sellada sino que va a un nuevo lote. | High | STEP 2 & STEP 4 | Reflejado exactamente en STEP 2 y STEP 4. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: `Pompe urgente` ingresa cuando no hay muestras previas (lote de 1) | Ingresa muestra de un paciente de 2 meses con patología `Pompe` (`es_pompe_urgente=True`) sin `SampleSet` abierto | Se crea un `SampleSet`, se agrega la única muestra (`1/10`), y el `SampleSet` se cierra inmediatamente (`estado == EstadoSampleSet.CERRADO`, `es_pompe_urgente == True`), pasando el estudio a `EstadoEstudio.EN_ESPERA_RETIRO`. |
| `TC-02`: `Pompe urgente` ingresa cuando hay 5 muestras en el `SampleSet` abierto (lote de 6) | `SampleSet` abierto tiene 5 muestras normales; ingresa 1 muestra de `Pompe urgente` | El `SampleSet` incluye las 6 muestras (`6/10`), pasa a `EstadoSampleSet.CERRADO` con `es_pompe_urgente == True`, y los **6** `Estudio`s pasan a `EstadoEstudio.EN_ESPERA_RETIRO`. |
| `TC-03`: Paciente con patología `Pompe` pero mayor de 4 meses **no** cierra el lote incompleto | Ingresa muestra de paciente de 6 meses con patología `Pompe` (`es_pompe_urgente=False`) a un lote con 5 muestras | El `SampleSet` queda con 6 muestras pero permanece en `EstadoSampleSet.ABIERTO` y los estudios permanecen en `EstadoEstudio.EN_LAB_CENTRAL`. |
| `TC-04`: Paciente menor de 4 meses pero con otra patología (`Fabry`) **no** cierra el lote incompleto | Ingresa muestra de paciente de 1 mes con patología `Fabry` (`es_pompe_urgente=False`) | El `SampleSet` permanece en `EstadoSampleSet.ABIERTO` hasta llegar a 10 muestras. |
| `TC-05`: Nueva muestra llega después de que el `SampleSet` parcial de `Pompe urgente` ya se cerró | El `SampleSet #13` (6 muestras, `CERRADO` en espera de `FedEx`) existe cuando llega otra muestra al laboratorio central | La nueva muestra no se agrega al `SampleSet #13` sellado; crea un nuevo `SampleSet #14` en `EstadoSampleSet.ABIERTO`. |
| `TC-06`: Retiro de `FedEx` pasa el lote parcial a `En viaje a Corea` | Callback `POST /api/webhooks/fedex/sample-sets/13/retirado` | El `SampleSet #13` (de 6 muestras) y sus 6 `Estudio`s pasan a `En viaje a Corea`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El cálculo de `"menor de 4 meses"` se evalúa comparando la fecha de creación del `Estudio` (o fecha actual) contra `paciente.fecha_nacimiento` (`edad < 4 meses` calendario / `< 120 días`). | `.ai/2-Glosario_LEL.md` (`Pompe urgente`: `"Estudio de Pompe de un menor de 4 meses"`) y `estudios.py#L31` | Low |
| A2 | Aunque sea un `Pompe urgente`, debe cumplir igualmente el pago o autorización previa y esperar el horario de retiro de `FedEx` en días hábiles de lunes a viernes de 09:00 a 18:00. | `.ai/1-Entrevista.md` (líneas 439-440 y 472-491) | Low |

## Open Questions

- Ninguna pregunta abierta bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/estudios.py`, `logistica.py`, `perfiles.py` y `enums.py`. | Estado marcado como `Approved`. |
