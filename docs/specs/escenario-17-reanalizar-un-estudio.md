# WORKFLOW: Escenario 17 – Reanalizar un estudio
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-17-Reanalizar-un-estudio`

## Símbolos LEL utilizados

| Categoría | Símbolo LEL | Modelo / Tabla en `app/src/core/models/` |
|---|---|---|
| **Sujeto** | `Médico` | `Medico` en `medicos` / `Usuario` (`Rol.MEDICO`, `Rol.GERENTE_MEDICO`) (`Analisis.solicitado_por_id`) |
| **Sujeto** | `Bioinformático` | `Usuario` (`Rol.BIOINFORMATICO`) en `usuarios` (`Analisis.bioinformatico_id`) |
| **Sujeto** | `Paciente` | `Paciente` en `pacientes` / `Usuario` (`Rol.PACIENTE`) |
| **Objeto** | `Estudio` | `Estudio` en `estudios` y `EstudioGen` en `estudios_genes` |
| **Objeto** | `Datos crudos` | `DatosCrudos` en `datos_crudos` (exoma previamente obtenido de Corea) |
| **Objeto** | `Gen` | `Gen` en `genes` y `AnalisisGen` en `analisis_genes` |
| **Objeto** | `Variante` | `Variante` en `variantes` y `AnalisisVariante` en `analisis_variantes` |
| **Objeto** | `Resultado` | `Resultado` en `resultados` (un `Resultado` por cada fila de `Analisis`) |
| **Objeto** | `API de bioinformática` | Cliente HTTP en `app/src/clients/` |
| **Objeto** | `Aviso` | `Aviso` en `avisos` |
| **Verbo** | `Reanalizar estudio` | Servicio `solicitar_reanalisis_estudio` (`TipoAnalisis.REANALISIS`) |
| **Verbo** | `Cargar resultado` | Registro de variantes y generación del nuevo `Resultado` del reanálisis |
| **Estado** | `Resultado cargado` | `EstadoEstudio.RESULTADO_CARGADO` (`"Resultado cargado"`) |
| **Estado** | `En análisis por bioinformática` | `EstadoEstudio.EN_ANALISIS_BIOINFORMATICA` (`"En analisis por bioinformatica"`) |
| **Estado** | `En análisis de un bioinformático` | `EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` (`"En analisis de un bioinformatico"`) |

---

## Overview

- **Objetivo**: Analizar nuevos `Gen`es utilizando el mismo exoma (`Datos crudos`) previamente obtenido de un `Estudio` ya completado, sin volver a tomar `Muestra` de sangre ni volver a enviarla a Corea, conservando el historial completo de análisis y resultados sobre el mismo `Estudio`.
- **Contexto**: Un `Paciente` ya tiene un `Estudio` con `Datos crudos` secuenciados y en estado `Resultado cargado` (por ejemplo, el análisis inicial dio negativo para la sospecha original), y existe una nueva sospecha clínica o un `Gen` que no fue considerado en el análisis inicial. El `Médico` tratante solicita un reanálisis sobre ese mismo `Estudio` indicando los nuevos `Gen`es a evaluar; el sistema crea una nueva fila en `analisis` con `tipo = TipoAnalisis.REANALISIS`, pasa el `Estudio` directamente a `En análisis por bioinformática`, el `Bioinformático` analiza los `Datos crudos` existentes para esos nuevos `Gen`es y el sistema registra el nuevo `Resultado` en el historial del estudio.
- **Recursos**: Exoma existente (`datos_crudos`), nuevos `Gen`es (`genes`, `estudios_genes`, `analisis_genes`), historial de análisis del estudio (`analisis`, `analisis_variantes`, `resultados`).
- **Episodios**:
  1. El `Médico` tratante solicita un reanálisis del `Estudio` existente.
  2. El `Médico` indica los nuevos `Gen`es a analizar.
  3. El `Bioinformático` toma el estudio y analiza los `Datos crudos` existentes sobre los nuevos `Gen`es.
  4. El sistema registra el nuevo `Analisis` (`TipoAnalisis.REANALISIS`) y su `Resultado` en el historial del `Estudio` / `Paciente`, notificando al `Médico` y al `Paciente`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Médico` | Solicita el reanálisis sobre un `Estudio` existente de su `Paciente` e indica los nuevos `Gen`es a evaluar. |
| `Bioinformático` | Recibe el aviso de que el `Estudio` ingresó a `En análisis por bioinformática` para reanálisis, lo toma (`En análisis de un bioinformático`), analiza los `Datos crudos` ya almacenados y registra las `Variante`s encontradas en los nuevos `Gen`es. |
| `Paciente` | Recibe la notificación del nuevo `Resultado` y puede consultar en su historial tanto el análisis inicial como todos los reanálisis realizados sobre su estudio. |
| `API de bioinformática` | Provee el catálogo de `Gen`es y las `Variante`s conocidas para los nuevos `Gen`es solicitados. |
| Capa `router` (`Flask Blueprint`) | Expone `POST /api/estudios/{estudio_id}/reanalisis` para el `Médico` y reutiliza los endpoints de bioinformática (`/tomar`, `/analisis`) sobre el `Analisis` activo de tipo `REANALISIS`. |
| Capa `service` (`EstudioService`, `BioinformaticaService`, `ResultadoService`) | Valida que el estudio tenga `DatosCrudos` y esté en `RESULTADO_CARGADO`, crea la nueva fila `Analisis(tipo=TipoAnalisis.REANALISIS)`, transiciona el estado del estudio sin pasar por extracción/logística y preserva el historial. |
| Capa `repo` (`EstudioRepo`, `AnalisisRepo`, `GenRepo`, `ResultadoRepo`, `AvisoRepo`) | Persiste el nuevo `Analisis`, `AnalisisGen`, `EstudioGen`, `AnalisisVariante` y `Resultado` en `PostgreSQL`. |

---

## Prerequisites

- Existe un usuario autenticado con `Rol.MEDICO` o `Rol.GERENTE_MEDICO` con perfil `Medico` en `medicos`.
- Existe un `Estudio` en `estudios` cuyo `estado` actual es `EstadoEstudio.RESULTADO_CARGADO`.
- El `Estudio` posee sus `DatosCrudos` ya cargados en la tabla `datos_crudos` (`estudio.datos_crudos IS NOT NULL`).
- El `Estudio` cuenta con al menos un `Analisis` previo completado (`TipoAnalisis.INICIAL` con su `Resultado` en `resultados`).

---

## Trigger

1. **Solicitud de reanálisis (Episodios 1–2)**: El `Médico` tratante invoca `POST /api/estudios/{estudio_id}/reanalisis` indicando la lista de nuevos `Gen`es (`genes_simbolos` o `genes_ids`) y opcionalmente la nueva `patologia_sospechada_id`.
2. **Ejecución del reanálisis bioinformático (Episodios 3–4)**: El `Bioinformático` invoca `POST /api/bioinformatica/estudios/{estudio_id}/tomar` y luego `POST /api/bioinformatica/estudios/{estudio_id}/analisis`.

---

## Workflow Tree

### STEP 1: Validación de la solicitud de reanálisis y de los nuevos Genes
**Actor**: `Médico` -> `router` -> `service` (`EstudioService.solicitar_reanalisis`) -> `clients` (`BioinformaticaClient`) -> `repo` (`EstudioRepo`, `GenRepo`)
**Action**:
1. Verifica que el usuario tenga `Rol.MEDICO` o `Rol.GERENTE_MEDICO` y que sea el médico tratante del `Paciente` / `Estudio`.
2. Bloquea la fila del `Estudio` (`SELECT ... FOR UPDATE`) y verifica que `estudio.estado == EstadoEstudio.RESULTADO_CARGADO` y que `estudio.datos_crudos IS NOT NULL`.
3. Valida la lista de nuevos `Gen`es solicitados:
   - Debe contener al menos 1 `Gen`.
   - Si se indicó una nueva `patologia_sospechada_id` o símbolos de genes, consulta/valida los genes contra la tabla `genes` y la `API de bioinformática`.
   - Verifica que al menos uno de los genes solicitados no haya sido ya analizado en los `Analisis` previos del mismo `Estudio` (evitando un reanálisis idéntico redundante).
**Timeout**: 6s
**Input**:
```json
{
  "estudio_id": 42,
  "nuevos_genes_simbolos": ["IDUA", "GBA"],
  "nueva_patologia_sospechada_id": 3
}
```
**Output on SUCCESS**: `{ estudio, medico, nuevos_genes: [Gen("IDUA"), Gen("GBA")] }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no tiene `Rol.MEDICO` / `Rol.GERENTE_MEDICO` o no es el médico tratante del paciente -> retornar HTTP `403 Forbidden`.
  - `FAILURE(not_found)`: No existe `Estudio` con `id = estudio_id` -> retornar HTTP `404 Not Found`.
  - `FAILURE(invalid_state)`: `estudio.estado != EstadoEstudio.RESULTADO_CARGADO` o `estudio.datos_crudos is None` -> retornar HTTP `409 Conflict` (`code: "ESTUDIO_NO_APTO_PARA_REANALISIS"`).
  - `FAILURE(validation_error)`: Lista `nuevos_genes_simbolos` vacía, o todos los genes indicados ya fueron evaluados en análisis anteriores de este mismo `Estudio` -> retornar HTTP `400 Bad Request` (`code: "GENES_YA_ANALIZADOS_O_VACIOS"`).

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: `"Validando solicitud de reanálisis..."`.
  - Operator sees: `Estudio` aún en `Resultado cargado`.
  - Database: Lectura con bloqueo `FOR UPDATE` sobre `estudios.id = 42`.
  - Logs: `[estudio_service] validando_reanalisis estudio_id=42 medico_id=4 nuevos_genes=["IDUA", "GBA"]`

---

### STEP 2: Creación del nuevo registro `Analisis(REANALISIS)` y salto directo a `En análisis por bioinformática`
**Actor**: `service` -> `repo` (`AnalisisRepo`, `EstudioRepo`, `AvisoRepo`) -> `PostgreSQL` -> `clients` (`MailClient`)
**Action**: En una transacción atómica sobre el **mismo** `Estudio` (sin crear otro `Estudio`, ni pedir `Turno`, ni tomar `Muestra`, ni armar `SampleSet`):
1. Inserta una **nueva fila** en la tabla `analisis` conservando intactas las filas de `Analisis` anteriores (historial):
   - `estudio_id = estudio.id`
   - `tipo = TipoAnalisis.REANALISIS`
   - `solicitado_por_id = medico.id`
   - `bioinformatico_id = None`
   - `created_at = now()`
2. Inserta en `analisis_genes` los nuevos `Gen`es asociados a este nuevo `analisis.id`, y agrega en `estudios_genes` aquellos que no estuvieran ya vinculados al `Estudio` (con `OrigenGen.PATOLOGIA` o `OrigenGen.MANUAL` según corresponda).
3. Si el médico indicó una `nueva_patologia_sospechada_id`, actualiza `estudio.patologia_sospechada_id`.
4. Actualiza `estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICA`.
5. Crea un `Aviso` y envía correo al equipo de `Bioinformático`s informando que el `Estudio` ingresó a `En análisis por bioinformática` para un `Reanálisis`.
**Timeout**: 5s
**Input**: `{ estudio_id: 42, medico_id: 4, nuevos_genes_ids: [11, 12] }`
**Output on SUCCESS**: `{ estudio_id: 42, analisis_id: 39, tipo: "reanalisis", estado_estudio: "En analisis por bioinformatica" }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(database_error)`: Error de base de datos al insertar en `analisis` / `analisis_genes` -> `ABORT_CLEANUP` (`session.rollback()`).

**Observable states during this step**:
  - Customer/Actor (`Médico` y `Paciente`) sees: El `Estudio #42` pasa a estado `En análisis por bioinformática`, manteniendo visible en el historial el `Resultado` del análisis inicial (`analisis_id = 25`).
  - Operator (`Bioinformático`) sees: El `Estudio #42` aparece nuevamente en la bandeja de `En análisis por bioinformática` identificado como `TipoAnalisis.REANALISIS` con los `Datos crudos` ya disponibles y los nuevos genes (`IDUA`, `GBA`).
  - Database:
    - Tabla `analisis`: Se conserva la fila `id = 25 (tipo='inicial')` con su `Resultado` `id = 18`, y se agrega la nueva fila `id = 39 (tipo='reanalisis', solicitado_por_id=4, bioinformatico_id=NULL)`.
    - Tabla `analisis_genes`: Nuevas filas para `analisis_id = 39` con `gen_id IN (11, 12)`.
    - Tabla `estudios`: `estado = 'En analisis por bioinformatica'`.
  - Logs: `[estudio_service] reanalisis_creado estudio_id=42 analisis_id=39 solicitado_por_medico_id=4`

---

### STEP 3: Toma del Reanálisis y evaluación de los Datos crudos existentes por el Bioinformático
**Actor**: `Bioinformático` -> `router` -> `service` (`BioinformaticaService.tomar_estudio` y `consultar_variantes`) -> `repo` (`AnalisisRepo`, `EstudioRepo`)
**Action**:
1. Un `Bioinformático` toma el estudio (`POST /api/bioinformatica/estudios/{estudio_id}/tomar`).
2. El sistema identifica el último `Analisis` pendiente (`analisis.id = 39`, `tipo == TipoAnalisis.REANALISIS`, `resultado IS NULL`), le asigna `analisis.bioinformatico_id = usuario.id` y cambia `estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICO`.
3. El `Bioinformático` accede al archivo `estudio.datos_crudos.archivo_path` ya existente y consulta las variantes conocidas de los nuevos `Gen`es (`IDUA`, `GBA`) mediante la `API de bioinformática`.
**Timeout**: 5s
**Input**: `{ estudio_id: 42, bioinformatico_usuario_id: 16 }`
**Output on SUCCESS**: `{ estudio_id: 42, analisis_id: 39, estado_estudio: "En analisis de un bioinformatico" }` -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(forbidden | conflict | invalid_state)`: Mismas validaciones que en STEP 2 del Escenario 15 (`403` si no es bioinformático, `409` si otro bioinformático ya lo tomó).

**Observable states during this step**:
  - Customer/Actor (`Médico` / `Paciente`) sees: `Estudio` en `En análisis de un bioinformático`.
  - Operator (`Bioinformático`) sees: Vista de trabajo del `Reanálisis #39` con acceso directo a `estudio.datos_crudos` y selector de variantes para los nuevos genes `IDUA` y `GBA`.
  - Database: `analisis.bioinformatico_id = 16` en `analisis.id = 39`; `estudios.estado = 'En analisis de un bioinformatico'`.
  - Logs: `[bioinformatica_service] reanalisis_tomado estudio_id=42 analisis_id=39 bioinformatico_id=16`

---

### STEP 4: Carga de variantes del Reanálisis y registro del nuevo Resultado en el historial
**Actor**: `Bioinformático` -> `router` (`POST /api/bioinformatica/estudios/{estudio_id}/analisis`) -> `service` (`BioinformaticaService.registrar_variantes_analisis` + `ResultadoService.generar_resultado`) -> `repo`
**Action**:
1. El `Bioinformático` registra las `Variante`s encontradas en los nuevos `Gen`es para el `Analisis` de tipo `TipoAnalisis.REANALISIS` (`analisis_id = 39`).
2. El sistema inserta las filas en `analisis_variantes` para `analisis_id = 39`.
3. Calcula `calcular_positivo` sobre las variantes del reanálisis, genera el nuevo PDF (`storage/resultados/resultado_analisis_39.pdf`) e inserta una nueva fila en `resultados` (`analisis_id = 39`, `positivo`, `pdf_path`).
4. Actualiza `estudio.estado = EstadoEstudio.RESULTADO_CARGADO`.
5. Envía `Aviso` y correo electrónico al `Médico` solicitante y al `Paciente` informando que el resultado del reanálisis está disponible.
6. En el historial del `Estudio` (`estudio.analisis`, ordenado por `Analisis.id`) quedan registrados y accesibles tanto el `Analisis` inicial (`id = 25`) con su `Resultado` (`id = 18`) como el `Analisis` de reanálisis (`id = 39`) con su nuevo `Resultado` (`id = 24`).
**Timeout**: 10s
**Input**:
```json
{
  "estudio_id": 42,
  "variantes_ids": [215]
}
```
**Output on SUCCESS**: `{ estudio_id: 42, analisis_id: 39, tipo_analisis: "reanalisis", resultado_id: 24, estado_estudio: "Resultado cargado", total_analisis_en_historial: 2 }` -> FIN DEL WORKFLOW.
**Output on FAILURE**:
  - `FAILURE(validation_error | forbidden | database_error)`: Si ocurre cualquier error, ejecuta `ABORT_CLEANUP` revirtiendo únicamente los cambios del paso actual y manteniendo intacto todo el historial previo del estudio.

**Observable states during this step**:
  - Customer/Actor (`Médico` y `Paciente`) sees: `Estudio` nuevamente en `Resultado cargado`, con historial de 2 análisis (`#1 Inicial - Negativo`, `#2 Reanálisis - Positivo`) y ambos PDFs descargables.
  - Operator (`Bioinformático`) sees: Reanálisis finalizado.
  - Database:
    - Tabla `analisis`: 2 filas para `estudio_id = 42` (`id=25, tipo='inicial'` y `id=39, tipo='reanalisis'`).
    - Tabla `resultados`: 2 filas (`analisis_id=25` y `analisis_id=39`).
    - Tabla `estudios`: `estado = 'Resultado cargado'`.
  - Logs: `[bioinformatica_service] reanalisis_completado estudio_id=42 analisis_id=39 resultado_id=24`

---

### ABORT_CLEANUP: Reversión transaccional preservando historial previo
**Triggered by**: Fallo en STEP 2, STEP 3 o STEP 4.
**Actions** (in order):
  1. Ejecutar `session.rollback()` en SQLAlchemy.
  2. Si en STEP 4 se creó un PDF parcial para el nuevo `Analisis`, eliminarlo del disco sin tocar nunca los PDFs de análisis anteriores (`analisis_id = 25`).
**What customer sees**: El historial de análisis previos del `Estudio` permanece 100% íntegro.
**What operator sees**: Mensaje de error permitiendo reintentar la operación.

---

## State Transitions

```
Estudio (EstadoEstudio):
[Resultado cargado] (con DatosCrudos existentes y Analisis #1 INICIAL completado)
  -- (STEP 1-2: Médico solicita Reanálisis con nuevos Genes) -------> [En analisis por bioinformatica] (se agrega Analisis #2 REANALISIS)
[En analisis por bioinformatica]
  -- (STEP 3: Bioinformático toma el Reanálisis) -------------------> [En analisis de un bioinformatico]
[En analisis de un bioinformatico]
  -- (STEP 4: Bioinformático registra variantes del Reanálisis) ----> [Resultado cargado] (con Historial: Analisis #1 + Analisis #2)
```

---

## Handoff Contracts

### 1. `Médico (UI)` -> `Backend (router -> service)` (Solicitar Reanálisis de un Estudio)
**Endpoint**: `POST /api/estudios/{estudio_id}/reanalisis`
**Payload**:
```json
{
  "nuevos_genes_simbolos": ["IDUA", "GBA"],
  "nueva_patologia_sospechada_id": 3
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "estudio_id": 42,
  "analisis_id": 39,
  "tipo_analisis": "reanalisis",
  "solicitado_por_medico_id": 4,
  "nuevos_genes": [
    { "gen_id": 11, "simbolo": "IDUA" },
    { "gen_id": 12, "simbolo": "GBA" }
  ],
  "estado_estudio": "En analisis por bioinformatica",
  "requiere_nueva_muestra": false
}
```
**Failure response** (`400` / `403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "Todos los genes solicitados ya fueron analizados previamente en este estudio.",
  "code": "GENES_YA_ANALIZADOS_O_VACIOS",
  "retryable": false
}
```
**Timeout**: 6s
**ON FAILURE**: Rollback transaccional; el `Estudio` permanece en `Resultado cargado` sin crear nueva fila en `analisis`.

---

### 2. `Médico / Paciente (UI)` -> `Backend (router -> service)` (Consultar historial de análisis de un Estudio)
**Endpoint**: `GET /api/estudios/{estudio_id}/analisis`
**Payload**: Ninguno.
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "estudio_id": 42,
  "estado_estudio": "Resultado cargado",
  "historial_analisis": [
    {
      "analisis_id": 25,
      "tipo": "inicial",
      "created_at": "2026-10-15T10:00:00",
      "genes": ["GLA"],
      "resultado": {
        "resultado_id": 18,
        "positivo": false,
        "pdf_url": "/api/estudios/42/analisis/25/resultado/pdf"
      }
    },
    {
      "analisis_id": 39,
      "tipo": "reanalisis",
      "solicitado_por_medico_id": 4,
      "created_at": "2026-10-28T17:10:00",
      "genes": ["IDUA", "GBA"],
      "resultado": {
        "resultado_id": 24,
        "positivo": true,
        "pdf_url": "/api/estudios/42/analisis/39/resultado/pdf"
      }
    }
  ]
}
```
**Failure response** (`403` / `404`):
```json
{
  "ok": false,
  "error": "No tiene permisos para consultar el historial de este estudio.",
  "code": "FORBIDDEN",
  "retryable": false
}
```
**Timeout**: 3s
**ON FAILURE**: Retornar error HTTP sin mutar estado.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Nueva fila `Analisis(tipo=REANALISIS)` en `analisis` y filas en `analisis_genes` / `estudios_genes` | Step 2 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Asignación de `bioinformatico_id` y transición a `EN_ANALISIS_BIOINFORMATICO` | Step 3 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Nuevo PDF de resultado y filas en `analisis_variantes` y `resultados` | Step 4 | `ABORT_CLEANUP` | `os.remove()` del nuevo PDF + `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/analisis.py` (líneas 31-46), el modelo `Analisis` está diseñado específicamente para este escenario: tiene `tipo: Mapped[TipoAnalisis]` (`INICIAL` o `REANALISIS`), `solicitado_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("medicos.id"))` y el docstring `"Un analisis del exoma. El reanalisis agrega una fila nueva sobre el mismo estudio (historial)"`. Además, `Estudio.analisis` está ordenado por `Analisis.id` (`estudios.py#L45`). | Low | Todos los pasos | Alineación 100% exacta con el diseño de `analisis.py` y `estudios.py`. |
| RC-2 | Ni en `.ai/2-Glosario_LEL.md` (`Reanalizar estudio`) ni en `.ai/3-Escenarios.md` (Escenario 17) se incluye un nuevo flujo de presupuesto/turno/extracción para el reanálisis: el estudio salta directamente al análisis bioinformático reutilizando `estudio.datos_crudos`. | Low | STEP 2 | El estudio pasa directamente de `Resultado cargado` a `En análisis por bioinformática` creando la nueva fila en `analisis`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Solicitud exitosa de reanálisis por el `Médico` tratante | `POST /api/estudios/42/reanalisis` con `nuevos_genes_simbolos=["IDUA", "GBA"]` sobre un estudio en `Resultado cargado` | HTTP `201 Created`; se agrega una segunda fila en `analisis` con `tipo == TipoAnalisis.REANALISIS` y `solicitado_por_id == medico.id`, se vinculan los nuevos genes en `analisis_genes` y `estudio.estado` pasa a `EstadoEstudio.EN_ANALISIS_BIOINFORMATICA` sin crear nuevo `Estudio` ni `Muestra`. |
| `TC-02`: Preservación del análisis inicial y su resultado en el historial | Se solicita y completa un reanálisis sobre el `Estudio #42` | `len(estudio.analisis) == 2`: `estudio.analisis[0].tipo == TipoAnalisis.INICIAL` mantiene su `Resultado` intacto y `estudio.analisis[1].tipo == TipoAnalisis.REANALISIS` tiene su propio `Resultado`. |
| `TC-03`: Rechazo de reanálisis si se piden únicamente genes ya analizados en el mismo estudio | `POST /api/estudios/42/reanalisis` pidiendo `["GLA"]` cuando `"GLA"` ya fue analizado en el análisis inicial | HTTP `400 Bad Request` (`GENES_YA_ANALIZADOS_O_VACIOS`). |
| `TC-04`: Rechazo de reanálisis cuando el estudio aún no tiene resultado o datos crudos | `POST /api/estudios/42/reanalisis` cuando `estudio.estado == EstadoEstudio.EN_VIAJE_COREA` | HTTP `409 Conflict` (`ESTUDIO_NO_APTO_PARA_REANALISIS`). |
| `TC-05`: Rechazo de reanálisis solicitado por un rol distinto a `Médico` | `POST /api/estudios/42/reanalisis` invocado por un `Paciente` o `Administrativo` | HTTP `403 Forbidden`. |
| `TC-06`: Ciclo completo de reanálisis por el `Bioinformático` | El `Bioinformático` toma el estudio en reanálisis (`/tomar`) y carga variantes encontradas en `"IDUA"` (`/analisis`) | El estudio pasa por `EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` y finaliza en `EstadoEstudio.RESULTADO_CARGADO`, generando el nuevo PDF y notificando a `Médico` y `Paciente`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El reanálisis reutiliza el registro `DatosCrudos` único del `Estudio` (`datos_crudos.estudio_id` es `unique=True` en `analisis.py#L23`) porque el exoma completo del paciente ya fue leído en el envío inicial a Corea. | `.ai/1-Entrevista.md` (líneas 90-92: `"no tenemos que volver a sacar sangre ni tenemos que volver a hacer la lectura del ADN"`) y `analisis.py#L23` | Low |

## Open Questions

- Ninguna pregunta abierta bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/analisis.py`, `estudios.py`, `clinica.py` y `enums.py`. | Estado marcado como `Approved`. |
