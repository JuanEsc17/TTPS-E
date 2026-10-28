# WORKFLOW: Escenario 11 – Transportar muestras al laboratorio central
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-11-Transportar-muestras-al-laboratorio-central`

## Símbolos LEL utilizados

| Categoría | Símbolo LEL | Modelo / Tabla en `app/src/core/models/` |
|---|---|---|
| **Sujeto** | `Transportista` | `Transportista` en `transportistas` / `Usuario` (`Rol.TRANSPORTISTA`) |
| **Objeto** | `Orden del día` | `OrdenDelDia` en `ordenes_del_dia` y `OrdenDelDiaParada` en `ordenes_del_dia_paradas` |
| **Objeto** | `API de optimización de recorridos` | Cliente HTTP en `app/src/clients/` |
| **Objeto** | `Centro de extracción` | `CentroExtraccion` en `centros_extraccion` |
| **Objeto** | `Muestra` | `Muestra` en `muestras` |
| **Objeto** | `Estudio` | `Estudio` en `estudios` |
| **Objeto** | `Mapa de seguimiento` | `PosicionTransporte` en `posiciones_transporte` |
| **Verbo** | `Armar sample set` | Disparo automático al llegar al laboratorio central (Escenario 12) |
| **Estado** | `Lista para retirar` | `EstadoEstudio.LISTA_PARA_RETIRAR` (`"Lista para retirar"`) |
| **Estado** | `En camino al laboratorio central` | `EstadoEstudio.EN_CAMINO_LAB_CENTRAL` (`"En camino al laboratorio central"`) |
| **Estado** | `En laboratorio central` | `EstadoEstudio.EN_LAB_CENTRAL` (`"En laboratorio central"`) |

---

## Overview

- **Objetivo**: Trasladar las `Muestra`s desde los `Centro de extracción` de cada provincia hasta el laboratorio central siguiendo la `Orden del día` asignada al `Transportista`.
- **Contexto**: Existen `Muestra`s con `Estudio` en estado `Lista para retirar` en uno o más `Centro de extracción`. Cada mañana hábil (lunes a viernes, salvo feriados), el sistema genera la `Orden del día` fija y ordenada para el `Transportista` de cada provincia utilizando la `API de optimización de recorridos`.
- **Recursos**: `Orden del día` (`ordenes_del_dia`, `ordenes_del_dia_paradas`), `Muestra` (`muestras`), `Estudio` (`estudios`), posiciones del `Mapa de seguimiento` (`posiciones_transporte`).
- **Episodios**:
  1. El `Transportista` recibe la `Orden del día` con la lista diaria y ordenada de `Centro de extracción` de su provincia.
  2. El `Transportista` retira las `Muestra`s de cada `Centro de extracción` y marca la recogida.
  3. El sistema registra las `Muestra`s (y sus `Estudio`s) como `En camino al laboratorio central`.
  4. El `Transportista` informa la llegada de las `Muestra`s al laboratorio central.
  5. El sistema actualiza el estado de los `Estudio`s a `En laboratorio central` y dispara automáticamente el armado del `Sample set` (Escenario 12).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Transportista` | Consulta su `Orden del día` (sin poder modificarla), marca la recogida en cada `Centro de extracción` y marca la llegada al laboratorio central. |
| `API de optimización de recorridos` | Servicio externo que recibe las direcciones/coordenadas de los `Centro de extracción` de la provincia y devuelve el orden óptimo de paradas. |
| Capa `router` (`Flask Blueprint`) | Expone los endpoints de generación/consulta de `Orden del día`, marca de recogida en parada y marca de llegada al laboratorio central. |
| Capa `service` (`LogisticaService`) | Coordina la generación de la `Orden del día`, valida el orden e inmutabilidad del recorrido, actualiza los estados de `Estudio` y `Muestra` e invoca `armar_sample_set`. |
| Capa `repo` (`OrdenDelDiaRepo`, `MuestraRepo`, `EstudioRepo`) | Persiste `OrdenDelDia`, `OrdenDelDiaParada`, `PosicionTransporte`, `Muestra` y `Estudio` en `PostgreSQL`. |
| Capa `clients` (`OptimizacionRecorridosClient`) | Realiza la petición HTTP (`httpx`) a la `API de optimización de recorridos`. |

---

## Prerequisites

- Existe un `Transportista` registrado en `transportistas` asociado a un `Usuario` activo con `Rol.TRANSPORTISTA` y una `provincia` única (`transportistas.provincia`).
- La fecha actual es un día hábil (lunes a viernes, no feriado, dentro de la franja operativa de 09:00 a 18:00).
- Existen `CentroExtraccion` en la misma `provincia` del `Transportista` que tienen al menos un `Estudio` en `EstadoEstudio.LISTA_PARA_RETIRAR` cuya `muestra_vigente` tiene `tomada_en IS NOT NULL` y `llegada_lab_central IS NULL`.

---

## Trigger

1. **Generación / Consulta de la Orden del día**: Job matutino o petición `GET /api/logistica/ordenes-del-dia/hoy` por parte del `Transportista` autenticado.
2. **Recogida en Centro de extracción**: El `Transportista` invoca `POST /api/logistica/ordenes-del-dia/{orden_id}/paradas/{parada_id}/recoger`.
3. **Llegada al laboratorio central**: El `Transportista` invoca `POST /api/logistica/ordenes-del-dia/{orden_id}/llegada-laboratorio-central`.

---

## Workflow Tree

### STEP 1: Generación y entrega de la Orden del día ordenada
**Actor**: Scheduler / `Transportista` -> `router` -> `service` (`LogisticaService.obtener_o_generar_orden_del_dia`) -> `clients` (`OptimizacionRecorridosClient`) -> `repo` (`OrdenDelDiaRepo`)
**Action**:
1. Verifica que la fecha no sea sábado, domingo ni feriado.
2. Si ya existe una `OrdenDelDia` en `ordenes_del_dia` para `(transportista_id, fecha)`, la retorna directamente con sus `paradas` ordenadas por `OrdenDelDiaParada.posicion` (garantizando inmutabilidad: la `Orden del día` está fijada y el `Transportista` no puede modificarla).
3. Si aún no existe para hoy, identifica todos los `CentroExtraccion` de `transportista.provincia` que posean muestras cuyos `Estudio`s estén en `EstadoEstudio.LISTA_PARA_RETIRAR`.
4. Envía la lista de centros (`id`, `direccion`, `latitud`, `longitud`) a la `API de optimización de recorridos` y recibe la secuencia ordenada.
5. Inserta `OrdenDelDia` y sus filas `OrdenDelDiaParada` con `posicion = 1..N`, `retirada_en = None`, `llegada_lab_central = None`.
**Timeout**: 8s
**Input**: `{ transportista_id: 3, fecha: "2026-10-28" }`
**Output on SUCCESS**: `{ orden_id: 77, fecha: "2026-10-28", paradas: [...] }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario autenticado no tiene `Rol.TRANSPORTISTA` -> retornar HTTP `403 Forbidden`.
  - `FAILURE(validation_error)`: La fecha solicitada es fin de semana o feriado -> retornar HTTP `400 Bad Request` (`code: "DIA_NO_HABIL_SIN_ORDEN_DEL_DIA"`).
  - `FAILURE(empty_route)`: Ningún `Centro de extracción` de la provincia tiene muestras en `Lista para retirar` -> retornar HTTP `200 OK` con `orden_del_dia: null, paradas: []`.
  - `FAILURE(external_api_timeout_or_error)`: La `API de optimización de recorridos` falla o excede 5s -> reintentar 2 veces con backoff de 1s; si persiste, aplicar fallback determinístico local (ordenar centros por cercanía euclídea/Haversine o por `CentroExtraccion.id`) para no bloquear la operación diaria del `Transportista`, registrando `warning` en logs.
  - `FAILURE(conflict)`: Condición de carrera en `UniqueConstraint("transportista_id", "fecha")` -> capturar `IntegrityError`, hacer rollback y leer la `OrdenDelDia` ya creada.

**Observable states during this step**:
  - Customer/Actor (`Transportista`) sees: Lista fija y numerada (`posicion 1..N`) de `Centro de extracción` por los que debe pasar hoy.
  - Operator (`Administrativo`) sees: `Orden del día` activa para la provincia del `Transportista`.
  - Database:
    - Tabla `ordenes_del_dia`: 1 fila `(id=77, transportista_id=3, fecha='2026-10-28')`.
    - Tabla `ordenes_del_dia_paradas`: N filas con `posicion = 1..N`, `retirada_en = NULL`, `llegada_lab_central = NULL`.
  - Logs: `[logistica_service] orden_del_dia_generada orden_id=77 transportista_id=3 paradas=3`

---

### STEP 2: Marca de recogida de muestras en cada Centro de extracción
**Actor**: `Transportista` -> `router` -> `service` (`LogisticaService.marcar_recogida_centro`) -> `repo` (`OrdenDelDiaRepo`, `EstudioRepo`, `MuestraRepo`)
**Action**: Cuando el `Transportista` pasa por el `Centro de extracción` correspondiente a una `OrdenDelDiaParada` y marca la recogida:
1. Verifica que la `OrdenDelDia` pertenezca al `Transportista` autenticado y que `parada.retirada_en` sea `None`.
2. Registra `parada.retirada_en = now()` en `ordenes_del_dia_paradas`.
3. Opcionalmente registra la coordenada del `CentroExtraccion` (`latitud`, `longitud`) como punto inicial en `posiciones_transporte` para el `Mapa de seguimiento`.
4. Selecciona todos los `Estudio`s cuyas `Muestra`s vigentes pertenezcan a turnos de ese `centro_id` y cuyo estado sea `EstadoEstudio.LISTA_PARA_RETIRAR`, y actualiza su estado a `EstadoEstudio.EN_CAMINO_LAB_CENTRAL`.
**Timeout**: 5s
**Input**:
```json
{
  "orden_id": 77,
  "parada_id": 201
}
```
**Output on SUCCESS**: `{ parada_id: 201, retirada_en: "2026-10-28T11:30:00", estudios_actualizados: [42, 45] }` -> Repetir STEP 2 para cada parada de la `Orden del día`, luego GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no tiene `Rol.TRANSPORTISTA` o la `OrdenDelDia` pertenece a otro transportista -> retornar HTTP `403 Forbidden`.
  - `FAILURE(not_found)`: `orden_id` o `parada_id` inexistente -> retornar HTTP `404 Not Found`.
  - `FAILURE(conflict)`: La parada ya había sido marcada como recogida (`parada.retirada_en IS NOT NULL`) -> retornar HTTP `409 Conflict` (`code: "PARADA_YA_RETIRADA"`).
  - `FAILURE(database_error)`: Error en transacción -> `ABORT_CLEANUP` (`session.rollback()`) y retornar HTTP `500 Internal Server Error`.

**Observable states during this step**:
  - Customer/Actor (`Transportista`) sees: Parada marcada como `"Retirada a las 11:30"`; el `Paciente` ve su `Estudio` en estado `En camino al laboratorio central` y puede consultar el `Mapa de seguimiento` (Escenario 32).
  - Operator sees: Parada con `retirada_en` completo y estudios en `En camino al laboratorio central`.
  - Database:
    - Tabla `ordenes_del_dia_paradas`: `retirada_en = '2026-10-28 11:30:00'` para `id = 201`.
    - Tabla `estudios`: `estado = 'En camino al laboratorio central'` para todos los estudios retirados en ese centro.
    - Tabla `posiciones_transporte`: nueva fila con `(orden_id=77, latitud=centro.latitud, longitud=centro.longitud)`.
  - Logs: `[logistica_service] muestras_retiradas_en_centro orden_id=77 parada_id=201 centro_id=12 estudios=[42, 45]`

---

### STEP 3: Marca de llegada al laboratorio central
**Actor**: `Transportista` -> `router` -> `service` (`LogisticaService.marcar_llegada_lab_central`) -> `repo` (`OrdenDelDiaRepo`, `MuestraRepo`, `EstudioRepo`)
**Action**: Al arribar al laboratorio central con las muestras recolectadas de las paradas retiradas:
1. Verifica que la `OrdenDelDia` pertenezca al `Transportista` y que exista al menos una parada con `retirada_en IS NOT NULL` y `llegada_lab_central IS NULL`.
2. Para todas las paradas retiradas pendientes de entrega en esa `OrdenDelDia`, actualiza `parada.llegada_lab_central = now()`.
3. Para todas las `Muestra`s vigentes de esos centros cuyos `Estudio`s estén en `EstadoEstudio.EN_CAMINO_LAB_CENTRAL`, actualiza `muestra.llegada_lab_central = now()` en `muestras` y cambia `estudio.estado = EstadoEstudio.EN_LAB_CENTRAL` en `estudios`.
**Timeout**: 5s
**Input**:
```json
{
  "orden_id": 77,
  "mililitros_por_muestra": [
    { "muestra_id": 149, "mililitros": 4.50 },
    { "muestra_id": 150, "mililitros": 3.00 }
  ]
}
```
**Output on SUCCESS**: `{ orden_id: 77, llegada_lab_central: "2026-10-28T16:10:00", muestras_recibidas_ids: [149, 150] }` -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Usuario distinto al `Transportista` asignado a la `OrdenDelDia` -> retornar HTTP `403 Forbidden`.
  - `FAILURE(invalid_state)`: Ninguna parada de la `OrdenDelDia` fue marcada como recogida (`retirada_en IS NULL` en todas las paradas) -> retornar HTTP `409 Conflict` (`code: "SIN_MUESTRAS_EN_CAMINO"`).
  - `FAILURE(conflict)`: Todas las paradas retiradas ya habían registrado su `llegada_lab_central` -> retornar HTTP `409 Conflict` (`code: "LLEGADA_YA_REGISTRADA"`).
  - `FAILURE(database_error)`: Error al actualizar `ordenes_del_dia_paradas`, `muestras` o `estudios` -> `ABORT_CLEANUP` (`session.rollback()`).

**Observable states during this step**:
  - Customer/Actor (`Transportista`) sees: `"Llegada al laboratorio central registrada exitosamente"`. El `Paciente` ve su `Estudio` en `En laboratorio central`.
  - Operator (`Administrativo`) sees: `Muestra`s recibidas en el laboratorio central con timestamp `llegada_lab_central`.
  - Database:
    - Tabla `ordenes_del_dia_paradas`: `llegada_lab_central = '2026-10-28 16:10:00'`.
    - Tabla `muestras`: `llegada_lab_central = '2026-10-28 16:10:00'`, `mililitros` actualizados si se informaron.
    - Tabla `estudios`: `estado = 'En laboratorio central'`.
  - Logs: `[logistica_service] llegada_laboratorio_central orden_id=77 muestras=[149, 150]`

---

### STEP 4: Disparo automático del armado de Sample Set
**Actor**: `service` (`LogisticaService.armar_sample_set_para_muestras_recibidas`) -> `repo` (`SampleSetRepo`, `MuestraRepo`, `EstudioRepo`)
**Action**: Sin intervención humana (tal como exige el LEL para `Armar sample set`), inmediatamente tras confirmar la llegada al laboratorio central en STEP 3, el sistema invoca el flujo del **Escenario 12** (`Formar un sample-set de muestras`) y **Escenario 14** (si alguna muestra corresponde a un `Pompe urgente`) para agrupar las muestras recién llegadas en un `SampleSet` abierto.
**Timeout**: 5s
**Input**: `{ muestras_recibidas_ids: [149, 150] }`
**Output on SUCCESS**: `{ sample_sets_afectados_ids: [12] }` -> FIN DEL WORKFLOW.
**Output on FAILURE**:
  - `FAILURE(database_error)`: Si falla la agrupación automática en `SampleSet`, se revierte o se reintenta la agrupación manteniendo las muestras en `EstadoEstudio.EN_LAB_CENTRAL` (`sample_set_id = NULL`) para no perder el registro físico de que el `Transportista` ya entregó los tubos en el laboratorio central.

**Observable states during this step**:
  - Customer/Actor (`Transportista`) sees: Recorrido del día finalizado.
  - Operator (`Administrativo`) sees: Las muestras recibidas ya aparecen asignadas al `SampleSet` en formación (o cerrado si llegó a 10 o incluye un `Pompe urgente`).
  - Database: `muestras.sample_set_id` asignado según reglas del Escenario 12.
  - Logs: `[logistica_service] disparo_automatico_sample_set orden_id=77 sample_sets=[12]`

---

### ABORT_CLEANUP: Reversión transaccional
**Triggered by**: Fallo de base de datos en STEP 1, STEP 2 o STEP 3.
**Actions** (in order):
  1. Ejecutar `session.rollback()` en SQLAlchemy para deshacer cambios parciales en `ordenes_del_dia`, `ordenes_del_dia_paradas`, `posiciones_transporte`, `muestras` y `estudios`.
  2. Registrar el error en los logs del sistema.
**What customer sees**: Mensaje de error en la interfaz del `Transportista` permitiendo reintentar la marcación de recogida o llegada.
**What operator sees**: Estado previo intacto en el panel de logística.

---

## State Transitions

```
Estudio (EstadoEstudio):
[Lista para retirar]
  -- (STEP 2: Transportista marca recogida en Centro de extracción) --> [En camino al laboratorio central]
[En camino al laboratorio central]
  -- (STEP 3: Transportista marca llegada al laboratorio central) ----> [En laboratorio central]
[En laboratorio central]
  -- (STEP 4: Disparo automático de Escenario 12 si cierra lote) -----> [En espera de retiro] (o permanece en [En laboratorio central] si el lote sigue abierto)

OrdenDelDiaParada (ordenes_del_dia_paradas):
[retirada_en = NULL, llegada_lab_central = NULL]
  -- (STEP 2: recogida) --> [retirada_en = <timestamp>, llegada_lab_central = NULL]
  -- (STEP 3: llegada) ---> [retirada_en = <timestamp>, llegada_lab_central = <timestamp>]
```

---

## Handoff Contracts

### 1. `Backend (service)` -> `API de optimización de recorridos (clients)`
**Endpoint**: `POST {OPTIMIZACION_RECORRIDOS_API_URL}/optimizar`
**Payload**:
```json
{
  "provincia": "Buenos Aires",
  "origen_destino_laboratorio_central": {
    "direccion": "Calle 50 Nro 1200, La Plata, Buenos Aires",
    "latitud": -34.9214,
    "longitud": -57.9544
  },
  "centros": [
    {
      "centro_id": 12,
      "nombre": "Centro Rossi",
      "direccion": "Av. Santa Fe 3100",
      "latitud": -34.5885,
      "longitud": -58.4091
    },
    {
      "centro_id": 19,
      "nombre": "Centro Dagostino",
      "direccion": "Av. 7 Nro 850",
      "latitud": -34.9152,
      "longitud": -57.9479
    }
  ]
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "recorrido_ordenado": [
    { "centro_id": 19, "posicion": 1 },
    { "centro_id": 12, "posicion": 2 }
  ]
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Servicio de optimización temporalmente no disponible",
  "code": "OPTIMIZER_UNAVAILABLE",
  "retryable": true
}
```
**Timeout**: 5s — tratado como `FAILURE` con 2 reintentos y fallback local determinístico.
**ON FAILURE**: Reintentar hasta 2 veces (backoff 1s); si continúa fallando, ordenar localmente por distancia geográfica (Haversine) para garantizar la entrega de la `Orden del día` al `Transportista`.

---

### 2. `Transportista (UI)` -> `Backend (router -> service)` (Marcar recogida en Centro de extracción)
**Endpoint**: `POST /api/logistica/ordenes-del-dia/{orden_id}/paradas/{parada_id}/recoger`
**Payload**: `{}`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "orden_id": 77,
  "parada_id": 201,
  "centro_id": 12,
  "retirada_en": "2026-10-28T11:30:00",
  "estudios_en_camino_ids": [42, 45]
}
```
**Failure response** (`403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "La recogida en este centro de extracción ya fue registrada.",
  "code": "PARADA_YA_RETIRADA",
  "retryable": false
}
```
**Timeout**: 5s
**ON FAILURE**: Rollback de transacción; las muestras permanecen en `Lista para retirar`.

---

### 3. `Transportista (UI)` -> `Backend (router -> service)` (Marcar llegada al laboratorio central)
**Endpoint**: `POST /api/logistica/ordenes-del-dia/{orden_id}/llegada-laboratorio-central`
**Payload**:
```json
{
  "mililitros_por_muestra": [
    { "muestra_id": 149, "mililitros": 4.50 }
  ]
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "orden_id": 77,
  "llegada_lab_central": "2026-10-28T16:10:00",
  "estudios_en_lab_central_ids": [42, 45],
  "sample_sets_afectados_ids": [12]
}
```
**Failure response** (`403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "No hay muestras retiradas en camino para registrar llegada.",
  "code": "SIN_MUESTRAS_EN_CAMINO",
  "retryable": false
}
```
**Timeout**: 8s
**ON FAILURE**: Rollback de transacción; las muestras permanecen en `En camino al laboratorio central`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Filas en `ordenes_del_dia` y `ordenes_del_dia_paradas` | Step 1 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Actualización de `retirada_en`, `posiciones_transporte` y `estudios.estado` | Step 2 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Actualización de `llegada_lab_central` en paradas y muestras, y `estudios.estado` | Step 3 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/logistica.py`, `OrdenDelDia` tiene `UniqueConstraint("transportista_id", "fecha")` y `OrdenDelDiaParada` tiene `UniqueConstraint("orden_id", "posicion")`. Esto garantiza en el nivel de esquema que haya una única orden diaria por transportista y un orden estricto de paradas. | Low | STEP 1 | Alineado con `logistica.py#L59-L87`. |
| RC-2 | El LEL establece que `"El transportista no puede modificar la orden del día"`. No debe exponerse ningún endpoint `PUT`/`PATCH`/`DELETE` sobre las paradas ni sobre su orden (`posicion`). | High | STEP 1 / Handoff Contracts | Especificado que los únicos endpoints de mutación permitidos al `Transportista` son `/recoger` sobre una parada existente y `/llegada-laboratorio-central`. |
| RC-3 | `Muestra` no se vincula por FK directa a `OrdenDelDiaParada`, sino a `Turno` (`muestras.turno_id -> turnos.centro_id`) y a `Estudio` (`muestras.estudio_id`). | Medium | STEP 2 & STEP 3 | Especificado que al marcar recogida en `parada.centro_id`, se seleccionan los `Estudio`s en `EstadoEstudio.LISTA_PARA_RETIRAR` cuya `muestra_vigente` provenga de un `Turno` en ese `centro_id`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Generación de `Orden del día` en día hábil con `API de optimización de recorridos` | `GET /api/logistica/ordenes-del-dia/hoy` un martes con 2 centros de la provincia con muestras en `Lista para retirar` | HTTP `200 OK`; se crea `OrdenDelDia` y 2 `OrdenDelDiaParada` con `posicion` 1 y 2 según el orden devuelto por la API externa. |
| `TC-02`: No generación de `Orden del día` en fin de semana o feriado | Solicitud de generación un sábado, domingo o feriado nacional | HTTP `400 Bad Request` (`DIA_NO_HABIL_SIN_ORDEN_DEL_DIA`); no se inserta fila en `ordenes_del_dia`. |
| `TC-03`: Inmutabilidad de la `Orden del día` | El `Transportista` consulta nuevamente su orden o intenta alterar el orden de paradas | Siempre recibe la misma `OrdenDelDia` generada para `(transportista_id, fecha)`; no existe operación para reordenar ni eliminar paradas. |
| `TC-04`: Fallback ante caída de `API de optimización de recorridos` | La API externa responde `503` o timeout en los 3 intentos | El sistema aplica ordenamiento local por cercanía y persiste la `OrdenDelDia` sin bloquear al `Transportista`. |
| `TC-05`: Marca de recogida en `Centro de extracción` | `POST /api/logistica/ordenes-del-dia/77/paradas/201/recoger` por el `Transportista` titular | HTTP `200 OK`; `parada.retirada_en` deja de ser `None` y todos los `Estudio`s con muestras listas en ese centro pasan de `EstadoEstudio.LISTA_PARA_RETIRAR` a `EstadoEstudio.EN_CAMINO_LAB_CENTRAL`. |
| `TC-06`: Rechazo de recogida por transportista de otra provincia | Un `Transportista` distinto al dueño de `orden_id = 77` invoca `/recoger` | HTTP `403 Forbidden`; sin cambios en base de datos. |
| `TC-07`: Marca de llegada al laboratorio central y disparo de `SampleSet` | `POST /api/logistica/ordenes-del-dia/77/llegada-laboratorio-central` tras haber recogido muestras | HTTP `200 OK`; `parada.llegada_lab_central` y `muestra.llegada_lab_central` se completan, los `Estudio`s pasan a `EstadoEstudio.EN_LAB_CENTRAL` (o `EN_ESPERA_RETIRO` si completan el `SampleSet` de 10) y las muestras quedan asociadas a un `SampleSet`. |
| `TC-08`: Rechazo de llegada al laboratorio central sin paradas recogidas | `POST /api/logistica/ordenes-del-dia/77/llegada-laboratorio-central` cuando todas las paradas tienen `retirada_en == None` | HTTP `409 Conflict` (`SIN_MUESTRAS_EN_CAMINO`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Cuando un `Transportista` marca la recogida en un `Centro de extracción`, retira **todas** las muestras que en ese instante se encuentran en estado `Lista para retirar` en dicho centro. | `.ai/1-Entrevista.md` (línea 265: `"pasa por el laboratorio uno y lo marca, diciendo que ya me estoy llevando unas muestras de acá. Automáticamente todas esas muestras que se está llevando tienen que cambiar de estado"`) | Low |
| A2 | Si un `Centro de extracción` no tiene ninguna muestra en `Lista para retirar` al momento de generar la `Orden del día`, no se incluye como parada en el recorrido de ese día. | `.ai/3-Escenarios.md` (Escenario 11) y `.ai/1-Entrevista.md` (líneas 273-275) | Low |

## Open Questions

- Ninguna pregunta abierta bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/logistica.py`, `turnos.py`, `perfiles.py`, `estudios.py` y `enums.py`. | Estado marcado como `Approved`. |
