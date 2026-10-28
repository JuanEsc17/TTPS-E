# WORKFLOW: Escenario 32 – Seguir una muestra en el mapa
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-32`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Paciente** | `Usuario` (`rol = Rol.PACIENTE`) + `Paciente` (`pacientes.id`, titular del `Estudio`) |
| **Sujetos** | **Transportista** | `Usuario` (`rol = Rol.TRANSPORTISTA`) + `Transportista` (`transportistas.id`, asignado por `provincia`) |
| **Objetos** | **Mapa de seguimiento** | Vista y endpoint de geolocalización alimentado por `PosicionTransporte` (`posiciones_transporte`), `OrdenDelDiaParada` y `CentroExtraccion` |
| **Objetos** | **Muestra** | Modelo `Muestra` (tabla `muestras`: `id`, `estudio_id`, `turno_id`, `tomada_en`, `llegada_lab_central`, `motivo_descarte`) |
| **Objetos** | **Orden del día** | Modelos `OrdenDelDia` (`ordenes_del_dia`) y `OrdenDelDiaParada` (`ordenes_del_dia_paradas`) |
| **Objetos** | **Centro de extracción** | Modelo `CentroExtraccion` (`centros_extraccion`: `id`, `nombre`, `direccion`, `provincia`, `latitud`, `longitud`) |
| **Objetos** | **Estudio** | Modelo `Estudio` (`estudios`: `id`, `paciente_id`, `estado`, propiedad `muestra_vigente`) |
| **Objetos** | **Sample set** | Modelo `SampleSet` (`sample_sets`: se arma automáticamente al llegar al laboratorio central) |
| **Verbos** | **Armar sample set** | Se dispara automáticamente cuando el **transportista** marca la llegada al **laboratorio central** |
| **Estados** | **Lista para retirar**, **En camino al laboratorio central**, **En laboratorio central**, **En espera de retiro** | `EstadoEstudio.LISTA_PARA_RETIRAR` -> `EstadoEstudio.EN_CAMINO_LAB_CENTRAL` -> `EstadoEstudio.EN_LAB_CENTRAL` (y `EstadoEstudio.EN_ESPERA_RETIRO` si cierra el **sample set**) |

---

## Overview

- **Objetivo:** Mostrar en el **mapa de seguimiento** por dónde viaja la **muestra** de un **paciente** mientras es trasladada por el **transportista** desde el **centro de extracción** hacia el **laboratorio central**.
- **Contexto:** La **muestra** fue tomada en el **centro de extracción** (el **estudio** pasó a **Lista para retirar** tras el aviso al **bot de Telegram**), es retirada por el **transportista** en su **orden del día** pasando a **En camino al laboratorio central**, y el **paciente** consulta su ubicación hasta que llega al **laboratorio central**.
- **Recursos:** **Mapa de seguimiento**, **muestra** (`muestras`), **orden del día** (`ordenes_del_dia`, `ordenes_del_dia_paradas`), posiciones GPS (`posiciones_transporte`), estado del **estudio** (`estudios.estado`).
- **Episodios:**
  1. El **transportista** marca la **recogida** de la **muestra** en el **centro de extracción**.
  2. El sistema registra la **muestra** y su **estudio** como **En camino al laboratorio central** (y recibe las posiciones del **transportista** en `posiciones_transporte`).
  3. El **paciente** consulta el **mapa de seguimiento**.
  4. El sistema muestra la posición actual y el recorrido de la **muestra** en el **mapa de seguimiento**.
  5. El **transportista** marca la llegada al **laboratorio central**, pasando el **estudio** a **En laboratorio central** y disparando automáticamente **armar sample set**.

**Resumen del flujo:** El escenario abarca el ciclo logístico terrestre y su visualización en tiempo real:
1. En `STEP 1`, el **transportista** marca la recogida en una parada de su **orden del día** (`POST /api/ordenes-del-dia/{orden_id}/paradas/{parada_id}/recogida`), lo que sella `OrdenDelDiaParada.retirada_en = now()`, registra la posición inicial en `posiciones_transporte` (coordenadas del `CentroExtraccion` o GPS enviado) y transiciona todos los **estudios** con **muestra** en `EstadoEstudio.LISTA_PARA_RETIRAR` de ese **centro de extracción** a `EstadoEstudio.EN_CAMINO_LAB_CENTRAL`.
2. En `STEP 2`, mientras el **transportista** se desplaza, su aplicación reporta coordenadas (`POST /api/ordenes-del-dia/{orden_id}/posiciones`) que se insertan en `posiciones_transporte`.
3. En `STEP 3`, el **paciente** consulta `GET /api/estudios/{estudio_id}/mapa-seguimiento` y el sistema devuelve el estado del **estudio**, las coordenadas de origen (`CentroExtraccion`), las paradas de la **orden del día** posteriores a la recogida y la última `PosicionTransporte` registrada.
4. En `STEP 4`, el **transportista** marca la llegada al **laboratorio central** (`POST /api/ordenes-del-dia/{orden_id}/llegada-laboratorio`), actualizando `OrdenDelDiaParada.llegada_lab_central = now()`, `Muestra.llegada_lab_central = now()`, cambiando `Estudio.estado` a `EstadoEstudio.EN_LAB_CENTRAL` y ejecutando automáticamente la lógica de **armar sample set**.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Transportista** (Sujeto LEL) | Marca la recogida en cada **centro de extracción** de su **orden del día**, reporta su posición durante el traslado y marca la llegada al **laboratorio central**. |
| **Paciente** (Sujeto LEL) | Consulta el **mapa de seguimiento** de su **estudio** para ver por dónde viaja su **muestra**. |
| **Router HTTP** (`app/src/routers/logistica.py`) | Expone los endpoints para el **transportista** (`Rol.TRANSPORTISTA`) y el endpoint de consulta del **mapa de seguimiento** para el **paciente** (`Rol.PACIENTE`). |
| **Servicio de Logística** (`app/src/services/logistica_service.py`) | Gestiona las transiciones `LISTA_PARA_RETIRAR -> EN_CAMINO_LAB_CENTRAL -> EN_LAB_CENTRAL`, registra coordenadas en `posiciones_transporte`, resuelve la trazabilidad `Estudio -> Muestra -> Turno -> CentroExtraccion -> OrdenDelDia` e invoca a `sample_set_service.agregar_muestras()`. |
| **Repositorio de Logística** (`app/src/repos/logistica_repo.py`) | Ejecuta lecturas y escrituras sobre `ordenes_del_dia`, `ordenes_del_dia_paradas`, `posiciones_transporte`, `muestras`, `turnos`, `centros_extraccion` y `estudios`. |
| **PostgreSQL** (`db`) | Persiste de forma transaccional los cambios de estado de **estudios**, marcas temporales de paradas/muestras y puntos de geolocalización. |

---

## Prerequisites

- **Sesión y Rol:**
  - Para marcar recogida, reportar posición y marcar llegada: sesión activa con `Usuario.rol == Rol.TRANSPORTISTA` y perfil `Transportista` en `transportistas`.
  - Para consultar el **mapa de seguimiento**: sesión activa con `Usuario.rol == Rol.PACIENTE` (`Usuario.debe_cambiar_password == False`) titular del `Estudio`.
- **Datos existentes en `app/src/core/models/`:**
  - Existe una `OrdenDelDia` (`ordenes_del_dia`) para el `transportista_id` y la `fecha` actual, con sus filas `OrdenDelDiaParada` (`ordenes_del_dia_paradas`) ordenadas por `posicion`.
  - Existe un `Estudio` con `Turno` en un `CentroExtraccion` incluido en la `OrdenDelDia` y una `Muestra` vigente (`motivo_descarte is None`, `tomada_en is not None`).
- **Estado previo del `Estudio`:**
  - Antes del Episodio 1 (recogida): `Estudio.estado == EstadoEstudio.LISTA_PARA_RETIRAR`.
  - Durante los Episodios 3 y 4 (consulta del mapa): `Estudio.estado == EstadoEstudio.EN_CAMINO_LAB_CENTRAL`.

---

## Trigger

1. **Recogida en centro de extracción (Episodios 1-2):** El **transportista** presiona "Marcar recogida" en una parada de su **orden del día** -> `POST /api/ordenes-del-dia/{orden_id}/paradas/{parada_id}/recogida`.
2. **Actualización de ubicación en tránsito:** El dispositivo del **transportista** envía coordenadas -> `POST /api/ordenes-del-dia/{orden_id}/posiciones`.
3. **Consulta del mapa de seguimiento (Episodios 3-4):** El **paciente** abre el **mapa de seguimiento** de su **estudio** -> `GET /api/estudios/{estudio_id}/mapa-seguimiento`.
4. **Llegada al laboratorio central (Episodio 5):** El **transportista** presiona "Marcar llegada al laboratorio central" -> `POST /api/ordenes-del-dia/{orden_id}/llegada-laboratorio`.

---

## Workflow Tree

### STEP 1: El transportista marca la recogida en el centro de extracción
**Actor**: **Transportista** -> Router (`logistica.py`) -> Servicio (`logistica_service.py`) -> Repositorio (`logistica_repo.py`)
**Action**:
  1. Verifica que la `OrdenDelDia` pertenezca al **transportista** autenticado y que la `OrdenDelDiaParada` (`parada_id`) pertenezca a dicha orden y tenga `retirada_en == NULL`.
  2. Obtiene con `SELECT ... FOR UPDATE` todos los `Estudio` en `EstadoEstudio.LISTA_PARA_RETIRAR` cuya `muestra_vigente` (`Muestra.motivo_descarte is None`) corresponda a un `Turno` en `parada.centro_id`.
  3. Actualiza `parada.retirada_en = now()`.
  4. Actualiza cada `Estudio` encontrado a `Estudio.estado = EstadoEstudio.EN_CAMINO_LAB_CENTRAL`.
  5. Inserta una fila inicial en `posiciones_transporte` (`orden_id`, `latitud`, `longitud`, `registrada_en = now()`) usando las coordenadas GPS enviadas o, en su defecto, `parada.centro.latitud` y `parada.centro.longitud`.
**Timeout**: `3s`
**Input**:
```json
{
  "transportista_usuario_id": 19,
  "orden_id": 14,
  "parada_id": 41,
  "latitud": -34.9214,
  "longitud": -57.9544
}
```
**Output on SUCCESS**: `{ parada_id: 41, retirada_en: datetime, estudios_en_camino_ids: list[int], posicion_id: int }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: La `OrdenDelDia` pertenece a otro **transportista** o el usuario no tiene `Rol.TRANSPORTISTA` -> retornar `403 Forbidden` (`ORDEN_AJENA`).
  - `FAILURE(invalid_state)`: La parada ya fue marcada como retirada (`parada.retirada_en is not None`) o la orden ya finalizó su llegada al laboratorio central -> retornar `409 Conflict` (`PARADA_YA_RETIRADA`).
  - `FAILURE(validation_error)`: `orden_id` o `parada_id` inexistentes, o coordenadas fuera de rango (`latitud` no en `[-90, 90]`, `longitud` no en `[-180, 180]`) -> retornar `404` / `422`.
  - `FAILURE(database_error)`: Fallo al actualizar -> `ABORT_CLEANUP` (`rollback`) -> retornar `500 Internal Server Error`.

**Observable states during this step**:
  - Customer/Actor sees:
    - **Transportista**: La parada en la **orden del día** aparece como "Recogida completada" con la cantidad de **muestras** retiradas.
    - **Paciente**: El estado de su **estudio** cambia inmediatamente a **En camino al laboratorio central** y se habilita el **mapa de seguimiento**.
  - Operator sees: `estudios.estado = 'En camino al laboratorio central'` para todas las muestras retiradas en ese centro.
  - Database:
    - `ordenes_del_dia_paradas`: `retirada_en = now()`.
    - `estudios`: `estado = EstadoEstudio.EN_CAMINO_LAB_CENTRAL`, `updated_at = now()`.
    - `posiciones_transporte`: nueva fila con `orden_id = 14`, `latitud`, `longitud`, `registrada_en = now()`.
  - Logs: `[logistica_service] step=1_recogida orden_id=14 parada_id=41 centro_id=7 estudios_actualizados=[88, 91]`

---

### STEP 2: Registro de posiciones del transportista durante el recorrido
**Actor**: **Transportista** -> Router (`logistica.py`) -> Servicio (`logistica_service.py`) -> Repositorio (`logistica_repo.py`)
**Action**: El dispositivo del **transportista** envía su ubicación actual (`latitud`, `longitud`). El servicio valida que la `OrdenDelDia` pertenezca al **transportista** y tenga al menos una parada retirada aún no entregada en el **laboratorio central**, e inserta un nuevo registro en `posiciones_transporte`.
**Timeout**: `2s`
**Input**: `{ orden_id: 14, latitud: -34.9150, longitud: -57.9480 }`
**Output on SUCCESS**: `{ posicion_id: int, latitud: float, longitud: float, registrada_en: datetime }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(validation_error)`: Coordenadas GPS inválidas (`NaN`, fuera de `[-90, 90]` / `[-180, 180]`) -> retornar `422 Unprocessable Entity` (`COORDENADAS_INVALIDAS`).
  - `FAILURE(invalid_state)`: La **orden del día** aún no inició recogidas o ya registró llegada de todas sus paradas al **laboratorio central** -> retornar `409 Conflict` (`RECORRIDO_NO_ACTIVO`).

**Observable states during this step**:
  - Customer/Actor (**Transportista**) sees: Indicador de GPS activo en su vista de **orden del día**.
  - Operator sees: Nuevos puntos en `posiciones_transporte` para `orden_id = 14`.
  - Database:
    - Tabla `posiciones_transporte`: nueva fila insertada (`id`, `orden_id`, `latitud`, `longitud`, `registrada_en`).
  - Logs: `[logistica_repo] step=2_posicion_registrada orden_id=14 lat=-34.9150 lon=-57.9480`

---

### STEP 3: El paciente consulta el mapa de seguimiento de su muestra
**Actor**: **Paciente** -> Router (`logistica.py`) -> Servicio (`logistica_service.py`) -> Repositorio (`logistica_repo.py`)
**Action**:
  1. Verifica que el `Estudio` (`estudio_id`) pertenezca al **paciente** autenticado (`estudio.paciente.usuario_id == usuario.id`).
  2. Obtiene la `muestra_vigente` del `Estudio`, su `Turno` asociado y el `CentroExtraccion` de origen.
  3. Localiza la `OrdenDelDiaParada` y su `OrdenDelDia` correspondiente a la recogida de esa **muestra**.
  4. Recupera las posiciones de `posiciones_transporte` de esa `OrdenDelDia` registradas desde `parada.retirada_en` en adelante (ordenadas por `registrada_en ASC`), identificando la última posición como `posicion_actual`.
**Timeout**: `2s`
**Input**: `{ estudio_id: 88, paciente_usuario_id: 52 }`
**Output on SUCCESS**: Payload completo del **mapa de seguimiento** (`estado_estudio`, `centro_extraccion_origen`, `posicion_actual`, `historial_posiciones`, `retirada_en`, `llegada_lab_central`) -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El `Estudio` pertenece a otro **paciente** -> retornar `403 Forbidden` (`ESTUDIO_AJENO`).
  - `FAILURE(invalid_state)`: El `Estudio` aún no fue retirado por el **transportista** (por ejemplo, está en `EstadoEstudio.TURNO_SACADO` o `EstadoEstudio.LISTA_PARA_RETIRAR`) -> retornar `409 Conflict` (`MUESTRA_AUN_NO_EN_CAMINO`) indicando el estado actual del estudio.
  - `FAILURE(not_found)`: `estudio_id` inexistente -> retornar `404 Not Found`.

**Observable states during this step**:
  - Customer/Actor (**Paciente**) sees: El **mapa de seguimiento** interactivo con el marcador del **centro de extracción** de origen, el marcador actual del **transportista** con su **muestra**, el trazado del recorrido y la hora de recogida.
  - Operator sees: Consulta `GET /api/estudios/88/mapa-seguimiento` respondida en `< 100ms`.
  - Database: Solo lecturas (`SELECT`) sobre `estudios`, `muestras`, `turnos`, `centros_extraccion`, `ordenes_del_dia_paradas` y `posiciones_transporte`.
  - Logs: `[logistica_service] step=3_consulta_mapa estudio_id=88 estado='En camino al laboratorio central' puntos=5`

---

### STEP 4: El transportista marca la llegada al laboratorio central
**Actor**: **Transportista** -> Router (`logistica.py`) -> Servicio (`logistica_service.py`) -> Repositorio (`logistica_repo.py`)
**Action**:
  1. Verifica que la `OrdenDelDia` pertenezca al **transportista** autenticado y posea paradas con `retirada_en is not None` y `llegada_lab_central is None`.
  2. Obtiene con `SELECT ... FOR UPDATE` todos los `Estudio` en `EstadoEstudio.EN_CAMINO_LAB_CENTRAL` cuyas muestras vigentes fueron retiradas en dichas paradas.
  3. Actualiza `OrdenDelDiaParada.llegada_lab_central = now()` en todas las paradas retiradas de la orden.
  4. Actualiza `Muestra.llegada_lab_central = now()` y `Estudio.estado = EstadoEstudio.EN_LAB_CENTRAL` para cada muestra entregada.
  5. Dispara automáticamente el verbo LEL **Armar sample set** (`sample_set_service.incorporar_muestras_recibidas(muestras)`): asigna `Muestra.sample_set_id` al `SampleSet` en `EstadoSampleSet.ABIERTO` (y si llega a `MUESTRAS_POR_SAMPLE_SET = 10` o alguna pertenece a un `Estudio` con `es_pompe_urgente == True`, cierra el `SampleSet` y pasa sus estudios a `EstadoEstudio.EN_ESPERA_RETIRO`).
**Timeout**: `5s`
**Input**: `{ transportista_usuario_id: 19, orden_id: 14 }`
**Output on SUCCESS**: `{ orden_id: 14, llegada_lab_central: datetime, muestras_recibidas_ids: list[int], estudios_actualizados_ids: list[int] }` -> Retornar `200 OK` (FIN DEL WORKFLOW).
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no es el **transportista** titular de la `OrdenDelDia` -> retornar `403 Forbidden`.
  - `FAILURE(invalid_state)`: Ninguna parada de la `OrdenDelDia` fue marcada como recogida previamente, o todas ya registraron llegada -> retornar `409 Conflict` (`SIN_MUESTRAS_EN_CAMINO`).
  - `FAILURE(database_error)`: Error durante la actualización de estados o armado de `SampleSet` -> ejecutar `ABORT_CLEANUP` (`rollback`) -> retornar `500 Internal Server Error`.

**Observable states during this step**:
  - Customer/Actor sees:
    - **Transportista**: **Orden del día** completada con estado "Entregado en laboratorio central".
    - **Paciente**: Su **estudio** figura ahora en estado **En laboratorio central** (o **En espera de retiro** si completó el **sample set**).
  - Operator sees: `muestras.llegada_lab_central` completado, `estudios.estado` actualizado y `sample_sets` actualizado.
  - Database:
    - `ordenes_del_dia_paradas`: `llegada_lab_central = now()`.
    - `muestras`: `llegada_lab_central = now()`, `sample_set_id = <id>`.
    - `estudios`: `estado = EstadoEstudio.EN_LAB_CENTRAL` (o `EstadoEstudio.EN_ESPERA_RETIRO` si el lote se cerró).
  - Logs: `[logistica_service] step=4_llegada_lab_central orden_id=14 muestras=[33, 34] estudios=[88, 91]`

---

### ABORT_CLEANUP: Rollback transaccional ante fallo en recogida o llegada
**Triggered by**: Fallo de base de datos o excepción no controlada durante `STEP 1` o `STEP 4`.
**Actions** (in order):
  1. Ejecutar `db.session.rollback()` para revertir cambios parciales en `ordenes_del_dia_paradas`, `estudios`, `muestras`, `posiciones_transporte` y `sample_sets`.
  2. Registrar en logs el `orden_id`, `parada_id` y el estado de las muestras afectadas.
**What customer/actor (**Transportista** / **Paciente**) sees**: Mensaje de error indicando que la operación no pudo completarse y que puede reintentar (`retryable = true`).
**What operator sees**: Log `ERROR` con trazabilidad de la transacción revertida; ningún `Estudio` queda en estado inconsistente respecto a su `OrdenDelDiaParada`.

---

## State Transitions

```
Estudio (estudios.estado):
  [EstadoEstudio.LISTA_PARA_RETIRAR]
    -- (STEP 1: Transportista marca recogida en centro de extracción) -->
  [EstadoEstudio.EN_CAMINO_LAB_CENTRAL]
    -- (STEP 2 y STEP 3: Posiciones registradas y consultadas en el Mapa de seguimiento) -->
  [EstadoEstudio.EN_CAMINO_LAB_CENTRAL]
    -- (STEP 4: Transportista marca llegada al laboratorio central) -->
  [EstadoEstudio.EN_LAB_CENTRAL]
    -- (Automático en STEP 4 si SampleSet llega a 10 muestras o hay Pompe urgente) -->
  [EstadoEstudio.EN_ESPERA_RETIRO]

OrdenDelDiaParada (ordenes_del_dia_paradas):
  [Pendiente (retirada_en=NULL, llegada_lab_central=NULL)]
    -- (STEP 1) --> [En tránsito (retirada_en=now(), llegada_lab_central=NULL)]
    -- (STEP 4) --> [Entregada (retirada_en=<ts1>, llegada_lab_central=now())]
```

---

## Handoff Contracts

### 1. Transportista -> Backend: Marcar recogida en centro de extracción
**Endpoint**: `POST /api/ordenes-del-dia/{orden_id}/paradas/{parada_id}/recogida`
**Payload**:
```json
{
  "latitud": -34.9214,
  "longitud": -57.9544
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "orden_id": 14,
    "parada_id": 41,
    "centro_id": 7,
    "retirada_en": "2026-10-28T11:15:00Z",
    "estudios_en_camino_ids": [88, 91],
    "nuevo_estado_estudios": "En camino al laboratorio central"
  }
}
```
**Failure response** (`403` / `404` / `409` / `422`):
```json
{
  "ok": false,
  "error": "La recogida en esta parada ya fue registrada previamente.",
  "code": "PARADA_YA_RETIRADA",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: No alterar `retirada_en` ni el estado de los estudios.

---

### 2. Transportista -> Backend: Registrar posición en tránsito
**Endpoint**: `POST /api/ordenes-del-dia/{orden_id}/posiciones`
**Payload**:
```json
{
  "latitud": -34.9150,
  "longitud": -57.9480
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "posicion_id": 502,
    "orden_id": 14,
    "latitud": -34.9150,
    "longitud": -57.9480,
    "registrada_en": "2026-10-28T11:25:00Z"
  }
}
```
**Failure response** (`403` / `409` / `422`):
```json
{
  "ok": false,
  "error": "Las coordenadas de latitud o longitud se encuentran fuera de rango.",
  "code": "COORDENADAS_INVALIDAS",
  "retryable": false
}
```
**Timeout**: `3s`
**ON FAILURE**: Reintentar en el próximo ciclo de telemetría si fue un error de red transitorio.

---

### 3. Paciente -> Backend: Consultar mapa de seguimiento de la muestra
**Endpoint**: `GET /api/estudios/{estudio_id}/mapa-seguimiento`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "estudio_id": 88,
    "estado_estudio": "En camino al laboratorio central",
    "muestra_id": 33,
    "centro_extraccion": {
      "id": 7,
      "nombre": "Centro de Extracción Rossi La Plata",
      "direccion": "Calle 7 N° 850, La Plata",
      "provincia": "Buenos Aires",
      "latitud": -34.9214,
      "longitud": -57.9544
    },
    "retirada_en": "2026-10-28T11:15:00Z",
    "llegada_lab_central": null,
    "posicion_actual": {
      "latitud": -34.9150,
      "longitud": -57.9480,
      "registrada_en": "2026-10-28T11:25:00Z"
    },
    "historial_posiciones": [
      {
        "latitud": -34.9214,
        "longitud": -57.9544,
        "registrada_en": "2026-10-28T11:15:00Z"
      },
      {
        "latitud": -34.9150,
        "longitud": -57.9480,
        "registrada_en": "2026-10-28T11:25:00Z"
      }
    ]
  }
}
```
**Failure response** (`403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "La muestra aún no se encuentra en camino al laboratorio central.",
  "code": "MUESTRA_AUN_NO_EN_CAMINO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Mostrar al **paciente** el estado actual del **estudio** sin renderizar el marcador en tránsito.

---

### 4. Transportista -> Backend: Marcar llegada al laboratorio central
**Endpoint**: `POST /api/ordenes-del-dia/{orden_id}/llegada-laboratorio`
**Payload**: `{}`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "orden_id": 14,
    "llegada_lab_central": "2026-10-28T12:10:00Z",
    "muestras_entregadas_ids": [33, 34],
    "estudios_actualizados": [
      { "estudio_id": 88, "estado": "En laboratorio central", "sample_set_id": 5 },
      { "estudio_id": 91, "estado": "En laboratorio central", "sample_set_id": 5 }
    ]
  }
}
```
**Failure response** (`403` / `409` / `500`):
```json
{
  "ok": false,
  "error": "No existen paradas recogidas pendientes de entrega en esta orden del día.",
  "code": "SIN_MUESTRAS_EN_CAMINO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Mantener las muestras en `EstadoEstudio.EN_CAMINO_LAB_CENTRAL` y permitir reintentar.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| `OrdenDelDiaParada.retirada_en` y cambio a `EN_CAMINO_LAB_CENTRAL` | Step 1 | `ABORT_CLEANUP` | `db.session.rollback()` |
| Fila en `posiciones_transporte` | Step 1 / Step 2 | `ABORT_CLEANUP` | `db.session.rollback()` |
| `llegada_lab_central` en paradas/muestras, cambio a `EN_LAB_CENTRAL` y asignación a `SampleSet` | Step 4 | `ABORT_CLEANUP` | `db.session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/logistica.py` existe el modelo `PosicionTransporte` (`posiciones_transporte`) vinculado a `OrdenDelDia` (`orden_id`, `latitud`, `longitud`, `registrada_en`) con el docstring explícito: `"Posiciones registradas para el mapa de seguimiento (escenario 32)."`. | Low | Overview, STEP 2, STEP 3 | El diseño utiliza directamente `PosicionTransporte` asociado a la `OrdenDelDia` del **transportista**. |
| RC-2 | `Muestra` se relaciona con `Turno` (`turno_id`) y `Turno` con `CentroExtraccion` (`centro_id`), mientras que `OrdenDelDiaParada` vincula `orden_id` con `centro_id` y `retirada_en`. | Medium | STEP 1, STEP 3 | Para filtrar solo el tramo donde la muestra del paciente efectivamente viaja con el transportista, `STEP 3` filtra `PosicionTransporte.registrada_en >= parada.retirada_en`. |
| RC-3 | Según el LEL (`Estado: Lista para retirar` y `Estado: En camino al laboratorio central`), al marcar la recogida el estudio pasa siempre a `En camino al laboratorio central`, y al marcar la llegada pasa a `En laboratorio central`. | Low | State Transitions | Ambos cambios de `EstadoEstudio` están contemplados de forma atómica en `STEP 1` y `STEP 4`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Transportista marca recogida en centro de extracción | `POST /api/ordenes-del-dia/{orden_id}/paradas/{parada_id}/recogida` por el transportista titular | Actualiza `parada.retirada_en`, cambia los estudios con muestras `LISTA_PARA_RETIRAR` de ese centro a `EstadoEstudio.EN_CAMINO_LAB_CENTRAL` y crea posición inicial en `posiciones_transporte`. |
| `TC-02`: Happy path – Registro de posiciones y consulta del mapa por el paciente | `POST /api/ordenes-del-dia/{orden_id}/posiciones` seguido de `GET /api/estudios/{estudio_id}/mapa-seguimiento` por el paciente titular | Retorna `200 OK` con `estado_estudio = "En camino al laboratorio central"`, datos del `CentroExtraccion`, `posicion_actual` e `historial_posiciones`. |
| `TC-03`: Happy path – Llegada al laboratorio central actualiza estado y arma sample set | `POST /api/ordenes-del-dia/{orden_id}/llegada-laboratorio` | Sella `llegada_lab_central` en paradas y muestras, cambia estudios a `EN_LAB_CENTRAL` y asocia las muestras al `SampleSet` abierto. |
| `TC-04`: Paciente intenta consultar mapa de un estudio de otro paciente | `GET /api/estudios/{estudio_id}/mapa-seguimiento` autenticado como otro paciente | Retorna `403 Forbidden` (`ESTUDIO_AJENO`). |
| `TC-05`: Paciente consulta el mapa antes de la recogida (`LISTA_PARA_RETIRAR`) | `GET /api/estudios/{estudio_id}/mapa-seguimiento` cuando `estudio.estado == EstadoEstudio.LISTA_PARA_RETIRAR` | Retorna `409 Conflict` (`MUESTRA_AUN_NO_EN_CAMINO`). |
| `TC-06`: Transportista intenta marcar recogida en una orden de otra provincia | `POST /api/ordenes-del-dia/{orden_id}/paradas/{parada_id}/recogida` por un transportista distinto al de `orden.transportista_id` | Retorna `403 Forbidden` (`ORDEN_AJENA`); no modifica estados. |
| `TC-07`: Doble marcación de recogida en la misma parada | Segundo `POST .../recogida` sobre una parada con `retirada_en != None` | Retorna `409 Conflict` (`PARADA_YA_RETIRADA`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Cuando el **transportista** marca la recogida en un **centro de extracción**, retira todas las **muestras** cuyos **estudios** están en `EstadoEstudio.LISTA_PARA_RETIRAR` en ese centro. | Verificado en `.ai/1-Entrevista.md` (línea 265: "pasa por el laboratorio uno y lo marca, diciendo que ya me estoy llevando unas muestras de acá. Automáticamente todas esas muestras que se está llevando tienen que cambiar de estado"). | Bajo. |
| A2 | El **mapa de seguimiento** muestra las posiciones de `PosicionTransporte` posteriores a la hora de recogida (`parada.retirada_en`) del centro donde se tomó la muestra del paciente. | Verificado en `app/src/core/models/logistica.py` (`OrdenDelDiaParada.retirada_en` y `PosicionTransporte.registrada_en`). | Bajo; evita mostrar el recorrido previo del transportista antes de pasar por el centro del paciente. |

## Open Questions

- ¿Se desea mostrar en el **mapa de seguimiento** también la coordenada fija del **laboratorio central** en La Plata como punto de destino final del recorrido?

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada alineada con `OrdenDelDia`, `OrdenDelDiaParada`, `PosicionTransporte`, `Muestra` y `Estudio` en `app/src/core/models/`. | Aprobada. |
