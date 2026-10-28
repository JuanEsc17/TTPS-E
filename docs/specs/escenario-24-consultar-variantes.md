# WORKFLOW: Escenario 24 – Consultar variantes
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-24`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Bioinformático` |
| **Objetos** | `Estudio`, `Gen`, `Variante`, `VUS`, `API de bioinformática`, `Datos crudos` |
| **Verbos** | `Cargar resultado` *(flujo posterior que utiliza las variantes consultadas)* |
| **Estados** | `En análisis de un bioinformático` |

---

## Overview

- **Objetivo**: Consultar la lista y la clasificación de **variantes** genéticas conocidas asociadas a los **genes** analizados en un **estudio**.
- **Contexto**: El **bioinformático** tomó un **estudio** que se encuentra en estado **En análisis de un bioinformático** (`EstadoEstudio.EN_ANALISIS_BIOINFORMATICO`), está analizando los **datos crudos** y selecciona uno de los **genes** solicitados para el **estudio** a fin de conocer sus **variantes** conocidas y su clasificación (`patogenica`, `benigna`, `inocua` o `vus`).
- **Recursos**: `Genes` (`genes`, `estudios_genes`), `Variantes` (`variantes`), clasificación de variantes (`ClasificacionVariante`: `PATOGENICA`, `BENIGNA`, `INOCUA`, `VUS`), `API de bioinformática`.
- **Episodios**:
  1. El **bioinformático** selecciona un **gen** perteneciente al **estudio** en análisis.
  2. El sistema consulta las **variantes** conocidas del **gen** en la **API de bioinformática** y sincroniza/actualiza el catálogo local en la tabla `variantes`.
  3. El sistema muestra la lista de **variantes** del **gen** junto con la clasificación de cada **variante** (`patogénica`, `benigna`, `inocua` o **VUS**).
  4. El **bioinformático** utiliza esta información para seleccionar las **variantes** encontradas y registrar el análisis (`Cargar resultado`).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Bioinformático` (Sujeto LEL) | Integrante autenticado (`Rol.BIOINFORMATICO`) que analiza un **estudio** en estado **En análisis de un bioinformático** y selecciona un **gen** para consultar sus **variantes**. |
| `API de bioinformática` (Objeto LEL) | Módulo externo que informa las **variantes** conocidas de cada **gen** (`notacion`, `clinvar_id`) y su clasificación (`patogenica`, `benigna`, `inocua`, `vus`). |
| `bioinformatica_router` / `analisis_router` (`app/src/routers/`) | Capa `router`: verifica sesión con `Rol.BIOINFORMATICO` y recibe la solicitud de consulta de **variantes** de un **gen** para el **estudio**. |
| `analisis_service` (`app/src/services/`) | Capa `service`: verifica que el **estudio** esté en **En análisis de un bioinformático**, que el **gen** pertenezca al **estudio** (o análisis activo), consulta la **API de bioinformática**, hace upsert en `variantes` y retorna la lista clasificada. |
| `clinica_repo` / `analisis_repo` (`app/src/repos/`) | Capa `repo`: lee `estudios`, `estudios_genes`, `analisis`, `genes` y realiza el upsert en `variantes` respetando `UniqueConstraint("gen_id", "notacion")`. |
| `bioinformatica_client` (`app/src/clients/`) | Capa `clients`: cliente HTTP (`httpx`) hacia la **API de bioinformática** con política de timeout y reintentos con backoff. |
| `PostgreSQL` | Almacena y actualiza las filas en `variantes` (`id`, `gen_id`, `notacion`, `clinvar_id`, `clasificacion`) asociadas a `genes.id`. |

---

## Prerequisites

- El usuario ha iniciado sesión con `rol = Rol.BIOINFORMATICO`.
- El **estudio** existe en `estudios` con `estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` y cuenta con un registro `Analisis` tomado por el **bioinformático** (`analisis.bioinformatico_id = usuario.id`).
- El **gen** seleccionado existe en `genes` y está vinculado al **estudio** en `estudios_genes` (o en `analisis_genes` en caso de reanálisis).

---

## Trigger

El **bioinformático** selecciona un **gen** en la pantalla de análisis bioinformático del **estudio**.
- **Endpoint HTTP**: `GET /api/v1/estudios/{estudio_id}/genes/{gen_id}/variantes`

---

## Workflow Tree

### STEP 1: Autorización de `Bioinformático` y validación del estado del `Estudio` y pertenencia del `Gen`
**Actor**: `analisis_router` -> `analisis_service` -> `analisis_repo` -> `PostgreSQL`
**Action**:
1. Verifica que el usuario autenticado tenga `Rol.BIOINFORMATICO`.
2. Consulta el `Estudio` (`estudios.id = estudio_id`) y su `Analisis` activo.
3. Comprueba que `estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO`.
4. Comprueba que el `Gen` (`genes.id = gen_id`) exista y esté incluido entre los **genes** solicitados para el **estudio** (`estudios_genes` o `analisis_genes`).
**Timeout**: `2s`
**Input**: `{ estudio_id: int, gen_id: int, usuario_id: int }`
**Output on SUCCESS**: `{ estudio: Estudio, gen: Gen }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no tiene `Rol.BIOINFORMATICO` -> retorna `403 Forbidden` (`code: "SOLO_BIOINFORMATICO"`).
  - `FAILURE(not_found)`: No existe el `Estudio` o no existe el `Gen` -> retorna `404 Not Found` (`code: "ESTUDIO_O_GEN_NO_ENCONTRADO"`).
  - `FAILURE(invalid_state)`: El `Estudio` no se encuentra en estado **En análisis de un bioinformático** (`EstadoEstudio.EN_ANALISIS_BIOINFORMATICO`) -> retorna `409 Conflict` (`code: "ESTADO_ESTUDIO_INVALIDO_PARA_ANALISIS"`).
  - `FAILURE(validation_error)`: El `Gen` no forma parte de los **genes** a evaluar en ese **estudio** -> retorna `422 Unprocessable Entity` (`code: "GEN_NO_SOLICITADO_EN_ESTUDIO"`).
  - `FAILURE(timeout)`: Supera `2s` -> retorna `504 Gateway Timeout` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Bioinformático`) sees: Selector de variantes mostrando "Cargando variantes conocidas del gen `<simbolo>`...".
  - Operator sees: Consulta `GET /api/v1/estudios/{estudio_id}/genes/{gen_id}/variantes` iniciada.
  - Database: Lectura en `estudios`, `analisis`, `estudios_genes`, `genes`.
  - Logs: `[analisis_service] step_1_validar_consulta_variantes estudio_id=<id> gen_id=<id> simbolo=<simbolo>`

---

### STEP 2: Consulta de variantes conocidas y su clasificación en la `API de bioinformática`
**Actor**: `analisis_service` -> `bioinformatica_client` -> `API de bioinformática`
**Action**:
1. Realiza una petición HTTP `GET` a la **API de bioinformática** enviando el símbolo del **gen** (`gen.simbolo`, ej. `"GLA"` o `"GAA"`).
2. Recibe la lista actualizada de **variantes** conocidas en la especie humana para ese **gen**, incluyendo su notación (`notacion`, ej. `"c.1935C>A"`), identificador `clinvar_id` y su clasificación (`patogenica`, `benigna`, `inocua` o `vus`).
3. Valida que cada clasificación recibida mapee a un valor válido de `ClasificacionVariante` (`PATOGENICA`, `BENIGNA`, `INOCUA`, `VUS`).
**Timeout**: `5s` por intento (hasta 2 reintentos con backoff de `500ms` y `1s`)
**Input**: `{ gen_id: int, simbolo: str }`
**Output on SUCCESS**: Lista de variantes externas `{ notacion: str, clinvar_id: Optional[str], clasificacion: ClasificacionVariante }[]` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(transient_external_error)`: Timeout o error `5xx` en la **API de bioinformática** -> reintenta hasta 2 veces (`500ms`, `1s`).
    - Si tras los reintentos la **API de bioinformática** sigue caída pero existen **variantes** previamente cacheadas en la tabla local `variantes` para `gen_id`, retorna las variantes locales con flag `fuente: "cache_local_contingencia"` (`200 OK`) para no bloquear el trabajo del **bioinformático**.
    - Si no existen variantes en caché local para ese `gen_id`, retorna `503 Service Unavailable` (`code: "API_BIOINFORMATICA_NO_DISPONIBLE"`, `retryable: true`).
  - `FAILURE(permanent_external_error)`: La **API de bioinformática** responde `404` (gen desconocido) o payload malformado -> retorna `502 Bad Gateway` (`code: "RESPUESTA_INVALIDA_API_BIOINFORMATICA"`).

**Observable states during this step**:
  - Customer/Actor (`Bioinformático`) sees: Spinner "Consultando base bioinformática de variantes...".
  - Operator sees: Llamada saliente `GET` desde `bioinformatica_client` hacia `API de bioinformática`.
  - Database: Sin cambios aún.
  - Logs: `[bioinformatica_client] step_2_consultar_variantes_gen simbolo=<simbolo> status=<status> variantes_recibidas=<n>`

---

### STEP 3: Sincronización (Upsert) en tabla `variantes` y entrega de resultados clasificados al `Bioinformático`
**Actor**: `analisis_service` -> `clinica_repo` -> `PostgreSQL`
**Action**:
1. Sincroniza en la tabla `variantes` las **variantes** devueltas por la **API de bioinformática** usando la clave única `(gen_id, notacion)`:
   - Si `(gen_id, notacion)` no existe en `variantes`, inserta la nueva fila con `clinvar_id` y `clasificacion`.
   - Si ya existe y cambió su `clasificacion` (por ej., una **VUS** reclasificada como `patogenica` o `benigna` por nueva evidencia científica) o su `clinvar_id`, actualiza la fila.
2. Ejecuta `COMMIT` y retorna la lista ordenada de **variantes** con su `id` interno, `notacion`, `clinvar_id` y `clasificacion` para que el **bioinformático** las seleccione al registrar el análisis (`AnalisisVariante`).
**Timeout**: `3s`
**Input**: `{ gen_id: int, variantes_externas: list[dict] }`
**Output on SUCCESS**: `{ gen_id: int, simbolo: str, variantes: list[{ variante_id: int, notacion: str, clinvar_id: Optional[str], clasificacion: str }] }` -> Retorna `200 OK`.
**Output on FAILURE**:
  - `FAILURE(conflict)` / `FAILURE(database_error)`: Dos **bioinformáticos** consultan el mismo **gen** simultáneamente provocando colisión en `UniqueConstraint("gen_id", "notacion")` -> maneja con `ON CONFLICT (gen_id, notacion) DO UPDATE` (o rollback y lectura de las filas ya insertadas) -> retorna `200 OK`. Si la base de datos falla, ejecuta `ABORT_CLEANUP` (`ROLLBACK`) y retorna `503 Service Unavailable`.

**Observable states during this step**:
  - Customer/Actor (`Bioinformático`) sees: Desplegable/tabla de **variantes** del **gen** con etiquetas de clasificación (`Patogénica`, `Benigna`, `Inocua`, `VUS`) lista para seleccionar y registrar en el análisis.
  - Operator sees: Catálogo local `variantes` sincronizado para `gen_id`.
  - Database: Tabla `variantes` actualizada con las filas `(gen_id, notacion, clinvar_id, clasificacion)`; `estudios.estado` permanece en `EN_ANALISIS_BIOINFORMATICO`.
  - Logs: `[clinica_repo] step_3_sincronizar_variantes_ok gen_id=<id> total_variantes=<n>`

---

### ABORT_CLEANUP: Reversión de sincronización parcial de variantes en base de datos
**Triggered by**: Fallo de escritura o timeout en `PostgreSQL` durante `STEP 3`.
**Actions** (in order):
  1. Ejecutar `ROLLBACK` de la transacción en `PostgreSQL` para no dejar actualizaciones parciales en `variantes`.
  2. Registrar error en logs con `estudio_id` y `gen_id`.
**What customer (`Bioinformático`) sees**: Mensaje de error con botón "Reintentar consulta de variantes" sin perder el estado de su análisis en pantalla.
**What operator sees**: Transacción revertida sin bloqueo de tablas.

---

## State Transitions

```
[Estudio(estado = EN_ANALISIS_BIOINFORMATICO)]
   -> (STEP 1-3 exitosos)
   -> [Estudio(estado = EN_ANALISIS_BIOINFORMATICO) + Tabla `variantes` sincronizada para `gen_id` con ClasificacionVariante (PATOGENICA | BENIGNA | INOCUA | VUS)]

[Variante(clasificacion = VUS)]
   -> (API de bioinformática informa nueva clasificación en STEP 2-3)
   -> [Variante(clasificacion = PATOGENICA | BENIGNA | INOCUA)]
```

---

## Handoff Contracts

### 1. Frontend (`Bioinformático`) -> Backend (`analisis_router`)
**Endpoint**: `GET /api/v1/estudios/{estudio_id}/genes/{gen_id}/variantes`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "estudio_id": 25,
    "estado_estudio": "En analisis de un bioinformatico",
    "gen": {
      "gen_id": 3,
      "simbolo": "GAA",
      "nombre": "Alpha glucosidase"
    },
    "fuente": "api_bioinformatica",
    "variantes": [
      {
        "variante_id": 101,
        "notacion": "c.-32-13T>G",
        "clinvar_id": "VCV000004027",
        "clasificacion": "patogenica"
      },
      {
        "variante_id": 102,
        "notacion": "c.1935C>A",
        "clinvar_id": "VCV000004031",
        "clasificacion": "patogenica"
      },
      {
        "variante_id": 103,
        "notacion": "c.2065G>A",
        "clinvar_id": "VCV000092615",
        "clasificacion": "benigna"
      },
      {
        "variante_id": 104,
        "notacion": "c.1551+5G>A",
        "clinvar_id": "VCV000451822",
        "clasificacion": "vus"
      },
      {
        "variante_id": 105,
        "notacion": "c.546G>T",
        "clinvar_id": "VCV000188901",
        "clasificacion": "inocua"
      }
    ]
  }
}
```
**Failure response** (`403` / `404` / `409` / `422` / `503`):
```json
{
  "ok": false,
  "error": "El gen seleccionado no pertenece a la lista de genes a analizar en este estudio.",
  "code": "GEN_NO_SOLICITADO_EN_ESTUDIO",
  "retryable": false
}
```
**Timeout**: `12s`

### 2. `analisis_service` (`bioinformatica_client`) -> `API de bioinformática`
**Endpoint**: `GET /api/v1/bioinformatica/genes/{simbolo}/variantes`
**Success response**:
```json
{
  "ok": true,
  "gen_simbolo": "GAA",
  "variantes": [
    {
      "notacion": "c.-32-13T>G",
      "clinvar_id": "VCV000004027",
      "clasificacion": "patogenica"
    },
    {
      "notacion": "c.1935C>A",
      "clinvar_id": "VCV000004031",
      "clasificacion": "patogenica"
    },
    {
      "notacion": "c.1551+5G>A",
      "clinvar_id": "VCV000451822",
      "clasificacion": "vus"
    }
  ]
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Upstream ClinVar connector timeout",
  "code": "BIOINFORMATICA_UPSTREAM_TIMEOUT",
  "retryable": true
}
```
**Timeout**: `5s`
**ON FAILURE**: Reintentar hasta 2 veces con backoff (`500ms`, `1s`); si persiste y existen variantes en `variantes` para `gen_id`, servir caché local con `fuente: "cache_local_contingencia"`; de lo contrario retornar `503`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Filas insertadas/actualizadas en `variantes` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` de la transacción SQL |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/clinica.py` (líneas 102-112), el modelo `Variante` tiene exactamente las columnas `id`, `gen_id`, `notacion`, `clinvar_id`, `clasificacion` (`Enum(ClasificacionVariante)`) y `UniqueConstraint("gen_id", "notacion")`. | Low | STEP 3 / Handoff Contracts | Alineado 100% con el modelo SQLAlchemy y con `ClasificacionVariante` (`PATOGENICA`, `BENIGNA`, `INOCUA`, `VUS`) en `enums.py`. |
| RC-2 | En `app/src/core/models/analisis.py` (líneas 58-65), `AnalisisVariante` vincula `analisis_id` con `variante_id` (`ForeignKey("variantes.id")`), por lo que es indispensable que la consulta de variantes (Escenario 24) sincronice las variantes de la API externa en la tabla local `variantes` y devuelva sus `variante_id`. | High | STEP 3 | Especificado como upsert en `variantes` durante `STEP 3` para que el paso posterior (`Cargar resultado`) reciba `variante_id` válidos. |
| RC-3 | No existen aún `analisis_router.py`, `analisis_service.py`, `bioinformatica_client.py` ni `analisis_repo.py`. | Medium | Actors | Documentados para implementación en el flujo SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Consulta y sincronización de variantes de un gen del estudio | `GET /api/v1/estudios/25/genes/3/variantes` por `Rol.BIOINFORMATICO` con estudio en `EN_ANALISIS_BIOINFORMATICO` | Retorna `200 OK` con las variantes y sus clasificaciones (`patogenica`, `benigna`, `inocua`, `vus`) y las persiste en `variantes`. |
| `TC-02`: Reclasificación de variante existente (ej. de `vus` a `patogenica`) | La `API de bioinformática` devuelve una variante ya existente en `variantes` con una nueva `clasificacion` | El upsert en `STEP 3` actualiza `variantes.clasificacion` sin duplicar `(gen_id, notacion)`. |
| `TC-03`: Gen no perteneciente al estudio | `GET /api/v1/estudios/25/genes/99/variantes` donde `gen_id=99` no está en `estudios_genes` ni `analisis_genes` | Retorna `422 Unprocessable Entity` (`code: "GEN_NO_SOLICITADO_EN_ESTUDIO"`). |
| `TC-04`: Estudio en estado inválido (ej. `En analisis por bioinformatica` aún no tomado o `Resultado cargado`) | `GET /api/v1/estudios/25/genes/3/variantes` cuando `estudio.estado != EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` | Retorna `409 Conflict` (`code: "ESTADO_ESTUDIO_INVALIDO_PARA_ANALISIS"`). |
| `TC-05`: Usuario con rol distinto de bioinformático | Petición realizada por `Rol.MEDICO` o `Rol.ADMINISTRATIVO` | Retorna `403 Forbidden` (`code: "SOLO_BIOINFORMATICO"`). |
| `TC-06`: Fallback a caché local ante caída de la `API de bioinformática` | `bioinformatica_client` falla con timeout en los 3 intentos, pero `variantes` ya tiene filas para `gen_id=3` | Retorna `200 OK` con `fuente: "cache_local_contingencia"` y las variantes almacenadas en `variantes`. |
| `TC-07`: Fallo total sin caché local disponible | `bioinformatica_client` falla en los 3 intentos y `variantes` tiene 0 filas para `gen_id=3` | Retorna `503 Service Unavailable` (`code: "API_BIOINFORMATICA_NO_DISPONIBLE"`, `retryable: true`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | La **API de bioinformática** es la fuente de verdad de las **variantes** conocidas y su clasificación, pero el sistema persiste cada `Variante` consultada en la tabla local `variantes` porque `AnalisisVariante` tiene clave foránea `variante_id -> variantes.id`. | `app/src/core/models/clinica.py` (`Variante`) y `app/src/core/models/analisis.py` (`AnalisisVariante`) | Bajo: es un requerimiento estructural directo del modelo de datos. |

## Open Questions

- Ninguna. Los cuatro valores de `ClasificacionVariante` (`patogenica`, `benigna`, `inocua`, `vus`) coinciden exactamente entre el LEL y `app/src/core/models/enums.py`.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/clinica.py` (`Gen`, `Variante`), `analisis.py` (`Analisis`, `AnalisisGen`, `AnalisisVariante`) y `enums.py` (`ClasificacionVariante`, `EstadoEstudio`). | Aprobada para implementación. |
