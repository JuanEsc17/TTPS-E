# WORKFLOW: Escenario 15 – Analizar un estudio mediante bioinformática
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-15-Analizar-un-estudio-mediante-bioinformatica`

## Símbolos LEL utilizados

| Categoría | Símbolo LEL | Modelo / Tabla en `app/src/core/models/` |
|---|---|---|
| **Sujeto** | `Administrativo` | `Usuario` (`Rol.ADMINISTRATIVO`) en `usuarios` (`DatosCrudos.cargado_por_id`) |
| **Sujeto** | `Bioinformático` | `Usuario` (`Rol.BIOINFORMATICO`) en `usuarios` (`Analisis.bioinformatico_id`) |
| **Objeto** | `Datos crudos` | `DatosCrudos` en `datos_crudos` |
| **Objeto** | `Estudio` | `Estudio` en `estudios` y `EstudioGen` en `estudios_genes` |
| **Objeto** | `Pompe urgente` | `Estudio.es_pompe_urgente` (ordena primero la lista del `Bioinformático`) |
| **Objeto** | `Gen` | `Gen` en `genes` y `AnalisisGen` en `analisis_genes` |
| **Objeto** | `Hallazgo secundario` | `Gen.es_hallazgo_secundario` / `OrigenGen.HALLAZGO_SECUNDARIO` |
| **Objeto** | `Variante` | `Variante` en `variantes` y `AnalisisVariante` en `analisis_variantes` |
| **Objeto** | `VUS` | `ClasificacionVariante.VUS` (`"vus"`) |
| **Objeto** | `API de bioinformática` | Cliente HTTP en `app/src/clients/` |
| **Objeto** | `Aviso` | `Aviso` en `avisos` (notificación al mail compartido del equipo de bioinformática) |
| **Verbo** | `Cargar resultado` | Carga de variantes del `Analisis` que desemboca en `Resultado cargado` (Escenario 16) |
| **Estado** | `En viaje a Corea` | `EstadoEstudio.EN_VIAJE_COREA` (`"En viaje a Corea"`) |
| **Estado** | `En análisis por bioinformática` | `EstadoEstudio.EN_ANALISIS_BIOINFORMATICA` (`"En analisis por bioinformatica"`) |
| **Estado** | `En análisis de un bioinformático` | `EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` (`"En analisis de un bioinformatico"`) |
| **Estado** | `Resultado cargado` | `EstadoEstudio.RESULTADO_CARGADO` (`"Resultado cargado"`) |

---

## Overview

- **Objetivo**: Recibir los `Datos crudos` provenientes de Corea para un `Estudio` individual, permitir que un `Bioinformático` tome el `Estudio` (priorizando los casos de `Pompe urgente`), consulte las `Variante`s conocidas de cada `Gen` a través de la `API de bioinformática` y registre las `Variante`s encontradas junto con su `ClasificacionVariante`.
- **Contexto**: El `Sample set` viajó a Corea, pero los resultados de secuenciación llegan de manera individual por cada `Estudio`. El `Administrativo` carga el archivo de `Datos crudos` (secuencia con letras `A, C, T, G`), lo que pasa el `Estudio` a `En análisis por bioinformática` y avisa al mail del equipo de bioinformática. Un `Bioinformático` toma el `Estudio` (pasándolo a `En análisis de un bioinformático` para que otro integrante no lo tome simultáneamente), selecciona los `Gen`es a evaluar, consulta las `Variante`s y su clasificación en la `API de bioinformática` y registra las `Variante`s halladas.
- **Recursos**: `Datos crudos` (`datos_crudos`), `Estudio` (`estudios`), `Analisis` (`analisis`), `Gen` (`genes`, `estudios_genes`, `analisis_genes`), `Variante` y su clasificación (`variantes`, `analisis_variantes`, `ClasificacionVariante`).
- **Episodios**:
  1. El `Administrativo` carga en el sistema los `Datos crudos` provenientes de Corea, pasando el `Estudio` a `En análisis por bioinformática` y notificando al equipo de bioinformática.
  2. El `Bioinformático` toma el `Estudio` (pasándolo a `En análisis de un bioinformático`) y selecciona los `Gen`es a analizar.
  3. El sistema consulta a la `API de bioinformática` las `Variante`s conocidas para cada `Gen` seleccionado.
  4. El `Bioinformático` registra las `Variante`s encontradas en el `Estudio` (o indica ausencia de variantes patogénicas).
  5. El sistema registra la `ClasificacionVariante` (`patogenica`, `benigna`, `inocua`, `vus`) de cada variante y genera el `Resultado` del estudio (Escenario 16).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Administrativo` | Carga el archivo de `Datos crudos` (`A, C, T, G`) recibido de Corea para un `Estudio` en estado `En viaje a Corea`. |
| `Bioinformático` | Recibe aviso en el mail compartido del equipo, visualiza primero los estudios de `Pompe urgente`, toma un `Estudio`, consulta variantes por `Gen` y registra las `Variante`s encontradas. |
| `API de bioinformática` | Módulo externo que devuelve la lista de `Variante`s conocidas asociadas a un `Gen` junto con su `clinvar_id` y `ClasificacionVariante` (`patogenica`, `benigna`, `inocua`, `vus`). |
| Capa `router` (`Flask Blueprint`) | Expone los endpoints de carga de `Datos crudos`, listado priorizado de estudios, toma de estudio, consulta de variantes por gen y registro de análisis bioinformático. |
| Capa `service` (`BioinformaticaService`) | Gestiona las transiciones `EN_VIAJE_COREA -> EN_ANALISIS_BIOINFORMATICA -> EN_ANALISIS_BIOINFORMATICO -> RESULTADO_CARGADO`, la sincronización de variantes con la `API de bioinformática` y la creación de `Analisis`. |
| Capa `repo` (`DatosCrudosRepo`, `AnalisisRepo`, `EstudioRepo`, `GenRepo`, `VarianteRepo`, `AvisoRepo`) | Persiste `DatosCrudos`, `Analisis`, `AnalisisGen`, `Variante`, `AnalisisVariante` y `Estudio` en `PostgreSQL`. |
| Capa `clients` (`BioinformaticaClient`, `MailClient`) | Consulta la `API de bioinformática` y envía el aviso por correo al equipo de bioinformática. |

---

## Prerequisites

- Para el **Episodio 1 (Carga de Datos crudos)**:
  - Usuario autenticado con `Rol.ADMINISTRATIVO`.
  - El `Estudio` existe en `estudios` con `estado == EstadoEstudio.EN_VIAJE_COREA` y aún no tiene registro en `datos_crudos`.
- Para los **Episodios 2–5 (Análisis bioinformático)**:
  - Usuario autenticado con `Rol.BIOINFORMATICO`.
  - El `Estudio` tiene sus `DatosCrudos` cargados en `datos_crudos` y se encuentra en `EstadoEstudio.EN_ANALISIS_BIOINFORMATICA` (para ser tomado) o en `EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` asignado a ese `Bioinformático`.
  - El `Estudio` tiene sus `EstudioGen` definidos en `estudios_genes` (provenientes de `OrigenGen.PATOLOGIA`, `OrigenGen.MANUAL` y/o `OrigenGen.HALLAZGO_SECUNDARIO`).

---

## Trigger

1. **Carga de datos crudos**: El `Administrativo` invoca `POST /api/estudios/{estudio_id}/datos-crudos` subiendo el archivo de texto de secuencia (`A, C, T, G`).
2. **Toma del estudio**: El `Bioinformático` selecciona un estudio de su bandeja (`GET /api/bioinformatica/estudios`, ordenada por `es_pompe_urgente DESC, updated_at ASC`) e invoca `POST /api/bioinformatica/estudios/{estudio_id}/tomar`.
3. **Consulta de variantes de un gen**: El `Bioinformático` selecciona un `Gen` del estudio (`GET /api/bioinformatica/genes/{gen_id}/variantes`).
4. **Registro de variantes encontradas**: El `Bioinformático` envía `POST /api/bioinformatica/estudios/{estudio_id}/analisis`.

---

## Workflow Tree

### STEP 1: Carga de Datos crudos por el Administrativo y paso a `En análisis por bioinformática`
**Actor**: `Administrativo` -> `router` -> `service` (`BioinformaticaService.cargar_datos_crudos`) -> `repo` (`DatosCrudosRepo`, `AnalisisRepo`, `EstudioRepo`, `AvisoRepo`) -> `clients` (`MailClient`)
**Action**:
1. Verifica que el usuario tenga `Rol.ADMINISTRATIVO` y que `estudio.estado == EstadoEstudio.EN_VIAJE_COREA`.
2. Valida que el archivo de `Datos crudos` no esté vacío y contenga únicamente caracteres válidos de bases nucleotídicas (`A`, `C`, `T`, `G` y saltos de línea/encabezados permitidos).
3. Guarda el archivo en almacenamiento (`storage/datos_crudos/estudio_{estudio_id}.txt`) e inserta una fila en `datos_crudos` (`estudio_id`, `cargado_por_id = usuario.id`, `archivo_path`, `cargado_en = now()`).
4. Crea la fila de `Analisis` inicial en la tabla `analisis` con `estudio_id = estudio.id`, `tipo = TipoAnalisis.INICIAL`, `bioinformatico_id = None`, y copia en `analisis_genes` los `gen_id` de `estudio.genes` (`estudios_genes`).
5. Actualiza `estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICA`.
6. Crea `Aviso`s (`CanalAviso.APP` y `CanalAviso.MAIL`) para los integrantes del equipo de bioinformática (`Rol.BIOINFORMATICO`) y envía correo al mail compartido del equipo avisando que el estudio (indicando si es `Pompe urgente`) está disponible para analizar.
**Timeout**: 10s
**Input**: `multipart/form-data` con archivo `archivo_datos_crudos` o JSON `{ "contenido_actg": "ATCGGCTA..." }` para `estudio_id = 42`.
**Output on SUCCESS**: `{ estudio_id: 42, datos_crudos_id: 19, analisis_id: 25, estado_estudio: "En analisis por bioinformatica" }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no tiene `Rol.ADMINISTRATIVO` -> retornar HTTP `403 Forbidden`.
  - `FAILURE(invalid_state)`: `estudio.estado != EstadoEstudio.EN_VIAJE_COREA` -> retornar HTTP `409 Conflict` (`code: "ESTUDIO_NO_ESTA_EN_VIAJE_A_COREA"`).
  - `FAILURE(conflict)`: Ya existen `DatosCrudos` para este `estudio_id` (`UniqueConstraint` en `datos_crudos.estudio_id`) -> retornar HTTP `409 Conflict` (`code: "DATOS_CRUDOS_YA_CARGADOS"`).
  - `FAILURE(validation_error)`: El archivo está vacío o contiene caracteres inválidos distintos de `A, C, T, G` -> retornar HTTP `400 Bad Request` (`code: "ARCHIVO_DATOS_CRUDOS_INVALIDO"`).

**Observable states during this step**:
  - Customer/Actor (`Paciente` y `Médico`) sees: `Estudio` en estado `En análisis por bioinformática`.
  - Operator (`Bioinformático`) sees: Nuevo estudio en la bandeja de pendientes (en primer lugar si `es_pompe_urgente == True`), correo recibido en la casilla del equipo de bioinformática.
  - Database:
    - Tabla `datos_crudos`: 1 fila `(id=19, estudio_id=42, cargado_por_id=7, archivo_path='...')`.
    - Tabla `analisis`: 1 fila `(id=25, estudio_id=42, tipo='inicial', bioinformatico_id=NULL)`.
    - Tabla `analisis_genes`: filas para cada `gen_id` del estudio.
    - Tabla `estudios`: `estado = 'En analisis por bioinformatica'`.
  - Logs: `[bioinformatica_service] datos_crudos_cargados estudio_id=42 datos_crudos_id=19 analisis_id=25`

---

### STEP 2: Listado priorizado y toma del Estudio por un Bioinformático (`En análisis de un bioinformático`)
**Actor**: `Bioinformático` -> `router` -> `service` (`BioinformaticaService.tomar_estudio`) -> `repo` (`EstudioRepo`, `AnalisisRepo`)
**Action**:
1. Al listar la bandeja (`GET /api/bioinformatica/estudios`), el sistema devuelve los estudios en `EstadoEstudio.EN_ANALISIS_BIOINFORMATICA` ordenados por `Estudio.es_pompe_urgente.desc(), Estudio.updated_at.asc()` para garantizar que cualquier `Pompe urgente` aparezca primero.
2. Cuando un `Bioinformático` decide tomar un `Estudio` (`POST /api/bioinformatica/estudios/{estudio_id}/tomar`), el sistema bloquea la fila de `estudios` (`SELECT ... FOR UPDATE`).
3. Verifica que `estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA`.
4. Asigna `analisis_activo.bioinformatico_id = usuario_bioinformatico.id` en la tabla `analisis` y cambia `estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` en `estudios` para informar al resto del equipo de bioinformática que el estudio ya fue tomado.
**Timeout**: 3s
**Input**: `{ estudio_id: 42, bioinformatico_usuario_id: 14 }`
**Output on SUCCESS**: `{ estudio_id: 42, analisis_id: 25, bioinformatico_id: 14, estado_estudio: "En analisis de un bioinformatico", genes_a_analizar: [...] }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario autenticado no tiene `Rol.BIOINFORMATICO` -> retornar HTTP `403 Forbidden`.
  - `FAILURE(conflict)`: Otro `Bioinformático` tomó el estudio un instante antes (`estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` con `bioinformatico_id != usuario.id`) -> retornar HTTP `409 Conflict` (`code: "ESTUDIO_YA_TOMADO_POR_OTRO_BIOINFORMATICO"`).
  - `FAILURE(invalid_state)`: `estudio.estado != EstadoEstudio.EN_ANALISIS_BIOINFORMATICA` -> retornar HTTP `409 Conflict`.

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: `Estudio` en `En análisis de un bioinformático`.
  - Operator (otros `Bioinformático`s) sees: El `Estudio #42` figura como `"En análisis de un bioinformático (asignado a Bioinformático #14)"` y no puede ser tomado por otro.
  - Database:
    - Tabla `estudios`: `estado = 'En analisis de un bioinformatico'`.
    - Tabla `analisis`: `bioinformatico_id = 14` en `analisis.id = 25`.
  - Logs: `[bioinformatica_service] estudio_tomado estudio_id=42 analisis_id=25 bioinformatico_id=14`

---

### STEP 3: Selección de Gen y consulta de Variantes conocidas en la API de bioinformática
**Actor**: `Bioinformático` -> `router` (`GET /api/bioinformatica/genes/{gen_id}/variantes`) -> `service` -> `clients` (`BioinformaticaClient`) -> `repo` (`VarianteRepo`)
**Action**:
1. El `Bioinformático` selecciona uno de los `Gen`es asociados al `Analisis` del estudio (por ejemplo `GLA`, `GAA`, etc.).
2. El sistema consulta a la `API de bioinformática` pasando el `simbolo` del `Gen` para obtener todas las `Variante`s conocidas en la especie humana para ese gen y su clasificación clínica (`patogenica`, `benigna`, `inocua`, `vus`).
3. El sistema sincroniza (upsert por `UniqueConstraint("gen_id", "notacion")`) las variantes devueltas en la tabla local `variantes` (`gen_id`, `notacion`, `clinvar_id`, `clasificacion`) y las presenta al `Bioinformático` en el selector.
**Timeout**: 8s
**Input**: `{ gen_id: 3, simbolo: "GAA" }`
**Output on SUCCESS**: Lista de variantes `[ { id, gen_id, notacion: "c.1935C>A", clinvar_id: "VCV000004025", clasificacion: "patogenica" }, ... ]` -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(external_api_timeout_or_error)`: La `API de bioinformática` tarda más de 8s o devuelve 5xx -> reintentar 2 veces con backoff de 1s; si persiste y existen variantes previamente cacheadas en la tabla `variantes` para ese `gen_id`, retornar el catálogo local con `warning: "USANDO_CATALOGO_LOCAL_CACHEADO"`; si no hay datos en caché, retornar HTTP `502 Bad Gateway` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Bioinformático`) sees: Desplegable con las variantes conocidas del `Gen` elegido y la insignia de su `ClasificacionVariante` (`patogenica`, `benigna`, `inocua`, `vus`).
  - Operator sees: Sin cambio de estado del estudio (`En análisis de un bioinformático`).
  - Database: Tabla `variantes` actualizada con las variantes conocidas de `gen_id = 3`.
  - Logs: `[bioinformatica_client] variantes_consultadas gen_id=3 simbolo="GAA" cantidad=14`

---

### STEP 4: Registro de las Variantes encontradas y su Clasificación en el Estudio
**Actor**: `Bioinformático` -> `router` (`POST /api/bioinformatica/estudios/{estudio_id}/analisis`) -> `service` (`BioinformaticaService.registrar_variantes_analisis`) -> `repo` (`AnalisisRepo`, `VarianteRepo`, `EstudioRepo`)
**Action**:
1. Verifica que el usuario tenga `Rol.BIOINFORMATICO`, que `estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` y que `analisis_activo.bioinformatico_id == usuario.id`.
2. Valida que todas las `variantes_ids` seleccionadas por el `Bioinformático` existan en la tabla `variantes` y pertenezcan a los `Gen`es incluidos en `analisis_activo.genes` (`analisis_genes`). (Se admite lista vacía `variantes_ids: []` cuando el paciente no presenta ninguna variante respecto del genoma de referencia en los genes estudiados).
3. Inserta las filas correspondientes en la tabla `analisis_variantes` (`analisis_id`, `variante_id`), quedando registrada para cada variante su `ClasificacionVariante` (`PATOGENICA`, `BENIGNA`, `INOCUA`, `VUS`) a través de `Variante.clasificacion`.
4. Invoca inmediatamente en la misma unidad de trabajo la generación del `Resultado` y notificaciones definida en el **Escenario 16** (`Informar el resultado de un estudio`), pasando `estudio.estado` a `EstadoEstudio.RESULTADO_CARGADO`.
**Timeout**: 10s
**Input**:
```json
{
  "estudio_id": 42,
  "variantes_ids": [101, 104]
}
```
**Output on SUCCESS**: `{ estudio_id: 42, analisis_id: 25, variantes_registradas: 2, resultado_id: 18, positivo: true, estado_estudio: "Resultado cargado" }` -> FIN DEL WORKFLOW (continúa/finaliza con Escenario 16).
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no es el `Bioinformático` que tomó el estudio -> retornar HTTP `403 Forbidden` (`code: "ESTUDIO_ASIGNADO_A_OTRO_BIOINFORMATICO"`).
  - `FAILURE(invalid_state)`: `estudio.estado != EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` -> retornar HTTP `409 Conflict`.
  - `FAILURE(validation_error)`: Alguna `variante_id` no existe o su `gen_id` no pertenece a los genes habilitados en `analisis_genes` para este análisis -> retornar HTTP `400 Bad Request` (`code: "VARIANTE_FUERA_DE_GENES_DEL_ESTUDIO"`).
  - `FAILURE(database_error)`: Error al insertar en `analisis_variantes` o `resultados` -> `ABORT_CLEANUP` (`session.rollback()`).

**Observable states during this step**:
  - Customer/Actor (`Bioinformático`) sees: Confirmación `"Análisis bioinformático registrado. Estudio #42 en estado Resultado cargado."`.
  - Operator / `Médico` / `Paciente` sees: `Estudio` en estado `Resultado cargado` con variantes y clasificación registradas.
  - Database:
    - Tabla `analisis_variantes`: filas `(analisis_id=25, variante_id=101)`, `(analisis_id=25, variante_id=104)`.
    - Tabla `resultados`: fila creada (ver Escenario 16).
    - Tabla `estudios`: `estado = 'Resultado cargado'`.
  - Logs: `[bioinformatica_service] variantes_registradas estudio_id=42 analisis_id=25 variantes=[101, 104] estado="Resultado cargado"`

---

### ABORT_CLEANUP: Reversión transaccional y limpieza de archivos
**Triggered by**: Fallo de base de datos o I/O en STEP 1, STEP 2 o STEP 4.
**Actions** (in order):
  1. Ejecutar `session.rollback()` en SQLAlchemy.
  2. Si falló STEP 1 luego de escribir `storage/datos_crudos/estudio_{id}.txt`, eliminar el archivo huérfano del disco.
  3. Preservar el estado previo del `Estudio` (`EN_VIAJE_COREA`, `EN_ANALISIS_BIOINFORMATICA` o `EN_ANALISIS_BIOINFORMATICO`).
**What customer sees**: Sin cambios inconsistentes en el estado del estudio.
**What operator sees**: Mensaje de error detallado para reintentar la carga o el registro de variantes.

---

## State Transitions

```
Estudio (EstadoEstudio):
[En viaje a Corea]
  -- (STEP 1: Administrativo carga Datos crudos) -----------------------> [En analisis por bioinformatica]
[En analisis por bioinformatica]
  -- (STEP 2: Bioinformático toma el Estudio) --------------------------> [En analisis de un bioinformatico]
[En analisis de un bioinformatico]
  -- (STEP 4: Bioinformático registra las Variantes encontradas) -------> [Resultado cargado]
```

---

## Handoff Contracts

### 1. `Administrativo (UI)` -> `Backend (router -> service)` (Cargar Datos crudos de Corea)
**Endpoint**: `POST /api/estudios/{estudio_id}/datos-crudos`
**Payload** (`multipart/form-data` o `application/json`):
```json
{
  "nombre_archivo": "secuencia_corea_estudio_42.txt",
  "contenido_actg": "ATCGGCTAGCTAGCTAGCTAGCTGATCGATCG"
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "estudio_id": 42,
  "datos_crudos_id": 19,
  "analisis_id": 25,
  "archivo_path": "storage/datos_crudos/estudio_42.txt",
  "estado_estudio": "En analisis por bioinformatica"
}
```
**Failure response** (`400` / `403` / `409`):
```json
{
  "ok": false,
  "error": "El archivo de datos crudos solo puede contener bases nucleotídicas A, C, T, G.",
  "code": "ARCHIVO_DATOS_CRUDOS_INVALIDO",
  "retryable": false
}
```
**Timeout**: 10s
**ON FAILURE**: Rollback de inserción en `datos_crudos` y `analisis`; el estudio permanece en `En viaje a Corea`.

---

### 2. `Bioinformático (UI)` -> `Backend (router -> service)` (Tomar un estudio para análisis)
**Endpoint**: `POST /api/bioinformatica/estudios/{estudio_id}/tomar`
**Payload**: `{}`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "estudio_id": 42,
  "analisis_id": 25,
  "bioinformatico_id": 14,
  "estado_estudio": "En analisis de un bioinformatico",
  "es_pompe_urgente": false,
  "genes": [
    { "gen_id": 3, "simbolo": "GAA", "origen": "patologia" },
    { "gen_id": 9, "simbolo": "BRCA1", "origen": "hallazgo_secundario" }
  ]
}
```
**Failure response** (`403` / `409`):
```json
{
  "ok": false,
  "error": "El estudio ya fue tomado por otro bioinformático.",
  "code": "ESTUDIO_YA_TOMADO_POR_OTRO_BIOINFORMATICO",
  "retryable": false
}
```
**Timeout**: 3s
**ON FAILURE**: Rollback; no se modifica `analisis.bioinformatico_id`.

---

### 3. `Backend (service)` -> `API de bioinformática (clients)` (Consultar variantes de un Gen)
**Endpoint**: `GET {BIOINFORMATICA_API_URL}/genes/{simbolo}/variantes`
**Payload**: Path param `simbolo` (ej. `"GAA"`).
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "gen_simbolo": "GAA",
  "variantes": [
    {
      "notacion": "c.1935C>A",
      "clinvar_id": "VCV000004025",
      "clasificacion": "patogenica"
    },
    {
      "notacion": "c.2065G>A",
      "clinvar_id": "VCV000092611",
      "clasificacion": "benigna"
    },
    {
      "notacion": "c.1194+5G>A",
      "clinvar_id": "VCV000551203",
      "clasificacion": "vus"
    }
  ]
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Servicio de bioinformática no disponible",
  "code": "BIOINFORMATICS_API_UNAVAILABLE",
  "retryable": true
}
```
**Timeout**: 8s
**ON FAILURE**: Reintentar 2 veces con backoff de 1s; si persiste, usar caché en tabla `variantes` si existe.

---

### 4. `Bioinformático (UI)` -> `Backend (router -> service)` (Registrar variantes del análisis)
**Endpoint**: `POST /api/bioinformatica/estudios/{estudio_id}/analisis`
**Payload**:
```json
{
  "variantes_ids": [101, 104]
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "estudio_id": 42,
  "analisis_id": 25,
  "tipo_analisis": "inicial",
  "variantes_registradas": [
    {
      "id": 101,
      "gen_simbolo": "GAA",
      "notacion": "c.1935C>A",
      "clasificacion": "patogenica"
    },
    {
      "id": 104,
      "gen_simbolo": "GAA",
      "notacion": "c.1194+5G>A",
      "clasificacion": "vus"
    }
  ],
  "resultado": {
    "id": 18,
    "positivo": true,
    "pdf_path": "storage/resultados/resultado_analisis_25.pdf"
  },
  "estado_estudio": "Resultado cargado"
}
```
**Failure response** (`400` / `403` / `409`):
```json
{
  "ok": false,
  "error": "La variante seleccionada no pertenece a los genes solicitados en este estudio.",
  "code": "VARIANTE_FUERA_DE_GENES_DEL_ESTUDIO",
  "retryable": false
}
```
**Timeout**: 10s
**ON FAILURE**: Rollback transaccional; el estudio permanece en `En análisis de un bioinformático`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Archivo `estudio_{id}.txt` y filas en `datos_crudos`, `analisis`, `analisis_genes` | Step 1 | `ABORT_CLEANUP` | `os.remove()` + `session.rollback()` |
| Asignación de `analisis.bioinformatico_id` y estado `EN_ANALISIS_BIOINFORMATICO` | Step 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Filas en `analisis_variantes`, `resultados` y estado `RESULTADO_CARGADO` | Step 4 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/analisis.py`, `DatosCrudos` tiene `estudio_id` único, mientras que `Analisis` tiene relación `1..N` con `Estudio` (`tipo: TipoAnalisis.INICIAL | REANALISIS`), `AnalisisGen` (`analisis_genes`) y `AnalisisVariante` (`analisis_variantes`). | Low | STEP 1 & STEP 4 | La especificación crea `Analisis(tipo=TipoAnalisis.INICIAL)` con sus `AnalisisGen` al cargar los `DatosCrudos` y registra las `AnalisisVariante` al finalizar el análisis. |
| RC-2 | En `app/src/core/models/enums.py`, `ClasificacionVariante` incluye las 4 categorías del LEL: `PATOGENICA = "patogenica"`, `BENIGNA = "benigna"`, `INOCUA = "inocua"`, `VUS = "vus"`. | Low | STEP 3 & STEP 4 | Alineado 100% con `enums.py#L49-L53`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Carga de `Datos crudos` válida por el `Administrativo` | `POST /api/estudios/42/datos-crudos` con secuencia `ACTG` cuando el estudio está `En viaje a Corea` | HTTP `201 Created`; se inserta en `datos_crudos`, se crea `Analisis(tipo=INICIAL)`, el estudio pasa a `EstadoEstudio.EN_ANALISIS_BIOINFORMATICA` y se crea `Aviso` para el equipo de bioinformática. |
| `TC-02`: Rechazo de `Datos crudos` con caracteres inválidos | `POST /api/estudios/42/datos-crudos` con contenido `"ACTGZ99"` | HTTP `400 Bad Request` (`ARCHIVO_DATOS_CRUDOS_INVALIDO`); el estudio permanece en `En viaje a Corea`. |
| `TC-03`: Priorización de `Pompe urgente` en la lista del `Bioinformático` | `GET /api/bioinformatica/estudios` habiendo un estudio normal más antiguo y un `Pompe urgente` más reciente en `En análisis por bioinformática` | El estudio con `es_pompe_urgente == True` aparece en la posición `0` de la lista devuelta. |
| `TC-04`: Toma exclusiva de estudio por un `Bioinformático` y bloqueo de concurrencia | Bioinformático A invoca `POST /api/bioinformatica/estudios/42/tomar` y luego Bioinformático B invoca el mismo endpoint | Bioinformático A recibe `200 OK` y el estudio pasa a `EstadoEstudio.EN_ANALISIS_BIOINFORMATICO`; Bioinformático B recibe `409 Conflict` (`ESTUDIO_YA_TOMADO_POR_OTRO_BIOINFORMATICO`). |
| `TC-05`: Consulta y sincronización de variantes de un `Gen` vía `API de bioinformática` | `GET /api/bioinformatica/genes/3/variantes` por un `Bioinformático` | HTTP `200 OK`; retorna las variantes con su `ClasificacionVariante` (`patogenica`, `benigna`, `inocua`, `vus`) y las persiste en la tabla `variantes`. |
| `TC-06`: Registro exitoso de variantes encontradas en el análisis | `POST /api/bioinformatica/estudios/42/analisis` con `variantes_ids=[101, 104]` pertenecientes a los genes del estudio | HTTP `200 OK`; se insertan las filas en `analisis_variantes`, se genera el `Resultado` y el estudio pasa a `EstadoEstudio.RESULTADO_CARGADO`. |
| `TC-07`: Rechazo de variante perteneciente a un gen no incluido en el estudio | `POST /api/bioinformatica/estudios/42/analisis` enviando una `variante_id` de un gen no solicitado | HTTP `400 Bad Request` (`VARIANTE_FUERA_DE_GENES_DEL_ESTUDIO`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El equipo de bioinformática comparte una dirección de correo electrónico institucional o recibe aviso grupal cuando un estudio entra en `En análisis por bioinformática`, y cualquiera de los bioinformáticos puede tomar el estudio. | `.ai/2-Glosario_LEL.md` (`Bioinformático`) y `.ai/1-Entrevista.md` (líneas 214-216 y 281-283) | Low |

## Open Questions

- Ninguna pregunta abierta bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/analisis.py`, `clinica.py`, `estudios.py` y `enums.py`. | Estado marcado como `Approved`. |
