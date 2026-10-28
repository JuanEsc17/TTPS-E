# WORKFLOW: Escenario 2 – Dar de alta un estudio
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-2`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Médico` (médico tratante, médico derivante), `Gerente médico`, `Paciente`, `Administrativo` |
| **Objetos** | `Estudio` (sinónimo: `sample`), `Paciente`, `Patología`, `Gen`, `Hallazgo secundario`, `API de bioinformática`, `Obra social`, `API de obras sociales`, `Pompe urgente`, `Aviso` |
| **Verbos** | `Dar de alta estudio` |
| **Estados** | `Creado`, `Pendiente de autorización` |

---

## Overview

- **Objetivo**: Registrar un `Estudio` de exoma clínico asociado a un `Paciente` previamente dado de alta, determinando los `Genes` a evaluar (los asociados a la `Patología` sospechada informados por la `API de bioinformática`, los agregados manualmente por el `Médico` y, si corresponde, los de `Hallazgo secundario`).
- **Contexto**: El `Paciente` ya está registrado en el sistema y el `Médico` tratante solicita un `Estudio` de exoma clínico desde la consulta. Si la `Patología` sospechada es enfermedad de Pompe y el `Paciente` tiene menos de 4 meses de edad al momento del alta, el sistema identifica automáticamente el `Estudio` como `Pompe urgente` (`es_pompe_urgente = True`).
- **Recursos**: Datos del `Paciente` (`paciente_id`, `fecha_nacimiento`), `patologia_sospechada_id` (`Patología`), lista de `Genes` obtenidos de la `API de bioinformática`, `Genes` manuales adicionales, flag `quiere_hallazgos_secundarios`, `obra_social_id` opcional.
- **Episodios**:
  1. El `Médico` selecciona al `Paciente` registrado.
  2. El `Médico` selecciona la `Patología` sospechada para obtener la lista base de `Genes`.
  3. El sistema consulta la `API de bioinformática` para obtener los `Genes` relacionados con la `Patología` sospechada (y los `Genes` de `Hallazgos secundarios` si el `Médico` marca que desea `Hallazgos secundarios`).
  4. El `Médico` agrega `Genes` adicionales manualmente cuando corresponde (`OrigenGen.MANUAL`) e indica si el `Estudio` se tramitará de forma particular o mediante una `Obra social`.
  5. El sistema registra el `Estudio` en estado inicial `Creado` (`EstadoEstudio.CREADO`), persiste cada `EstudioGen` con su `OrigenGen`, calcula si es `Pompe urgente`, y notifica mediante un `Aviso` a los `Administrativos` para que emitan el `Presupuesto` (Escenario 3).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Médico` / `Gerente médico` | Sujeto LEL que solicita el `Estudio` para el `Paciente`, elige la `Patología` sospechada, los `Genes` y si desea `Hallazgos secundarios`. |
| `Paciente` | Sujeto LEL titular del `Estudio` de exoma clínico. |
| `Administrativo` | Sujeto LEL que recibe un `Aviso` interno para emitir el `Presupuesto` del nuevo `Estudio`. |
| `router` (`estudios_router`) | Capa HTTP Flask (`GET /api/v1/bioinformatica/genes` y `POST /api/v1/estudios`). Valida sesión y rol (`Rol.MEDICO` o `Rol.GERENTE_MEDICO`). |
| `service` (`estudio_service`) | Capa de negocio que consulta la `API de bioinformática`, clasifica el `OrigenGen` de cada `Gen`, evalúa la regla de `Pompe urgente` y crea el `Estudio`. |
| `repo` (`estudio_repo`, `clinica_repo`, `paciente_repo`) | Capa de acceso a datos SQLAlchemy sobre `estudios`, `estudios_genes`, `genes`, `patologias_genes`, `obras_sociales`, `avisos`. |
| `clients` (`bioinformatica_client`, `obras_sociales_client`) | Clientes HTTP hacia la `API de bioinformática` (para obtener `Genes` de la `Patología` y de `Hallazgos secundarios`) y la `API de obras sociales` (si el estudio indica `Obra social`). |
| `PostgreSQL` | Base de datos relacional donde se persisten `estudios` y `estudios_genes`. |

---

## Prerequisites

- El usuario autenticado posee `Usuario.rol in (Rol.MEDICO, Rol.GERENTE_MEDICO)` y tiene perfil en `medicos`.
- El `Paciente` (`pacientes.id == paciente_id`) existe en la base de datos.
- La `Patología` (`patologias.id == patologia_sospechada_id`) existe en la tabla `patologias`.
- Si se especifica `obra_social_id`, la `Obra social` existe en `obras_sociales` (sincronizada desde la `API de obras sociales`).

---

## Trigger

El `Médico` selecciona al `Paciente`, configura los `Genes` y `Hallazgos secundarios`, y confirma la creación del `Estudio`:
- **Endpoint HTTP**: `POST /api/v1/estudios` (autenticado con rol `medico` o `gerente_medico`).
- *(Previamente en la pantalla, al elegir la `Patología` o marcar `Hallazgos secundarios`, el frontend invoca `GET /api/v1/patologias/{id}/genes?incluir_secundarios=true|false` que delega en la `API de bioinformática`).*

---

## Workflow Tree

### STEP 1: Validación de permisos del `Médico`, existencia del `Paciente` y `Patología`
**Actor**: `router` (`estudios_router`) -> `service` (`estudio_service`) -> `repo` (`paciente_repo`, `clinica_repo`)
**Action**:
1. Verifica que el usuario autenticado tenga rol `Rol.MEDICO` o `Rol.GERENTE_MEDICO` y obtiene su registro `Medico`.
2. Verifica que `paciente_id` exista en `pacientes` y que `patologia_sospechada_id` exista en `patologias`.
3. Si se informó `obra_social_id`, verifica que exista en `obras_sociales`.
**Timeout**: `2s`
**Input**: Payload JSON de `POST /api/v1/estudios` + usuario autenticado.
**Output on SUCCESS**: Entidades `Paciente`, `Medico`, `Patologia` y `ObraSocial` (opcional) -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no es `Rol.MEDICO` ni `Rol.GERENTE_MEDICO` -> `return 403 Forbidden` (`code: "FORBIDDEN_ROLE"`).
  - `FAILURE(validation_error)`: `paciente_id`, `patologia_sospechada_id` u `obra_social_id` no existen -> `return 404 Not Found` (`code: "RECURSO_NO_ENCONTRADO"`).

**Observable states during this step**:
  - **Customer/Actor (`Médico`) sees**: Spinner `"Verificando datos del paciente y patología..."`.
  - **Operator sees**: Request entrante en `POST /api/v1/estudios`.
  - **Database**: Lecturas (`SELECT`) en `medicos`, `pacientes`, `patologias`, `obras_sociales`.
  - **Logs**: `[estudio_service] STEP 1 iniciado medico_id=<mid> paciente_id=<pid> patologia_id=<pat_id>`

---

### STEP 2: Consulta de `Genes` a la `API de bioinformática` (Patología y `Hallazgos secundarios`)
**Actor**: `service` (`estudio_service`) -> `clients` (`bioinformatica_client`) -> `API de bioinformática`
**Action**:
1. Consulta a la `API de bioinformática` (`GET /api/v1/patologias/{nombre_patologia}/genes`) la lista oficial de `Genes` asociados a la `Patología` sospechada.
2. Si `quiere_hallazgos_secundarios == True`, consulta también a la `API de bioinformática` (`GET /api/v1/genes/hallazgos-secundarios`) los `Genes` correspondientes a `Hallazgos secundarios`.
3. Combina y clasifica los `Genes` solicitados por el `Médico`:
   - Los pertenecientes a la `Patología` -> `OrigenGen.PATOLOGIA`.
   - Los agregados manualmente por el `Médico` (`genes_manuales_simbolos`) -> `OrigenGen.MANUAL`.
   - Los provenientes de `Hallazgos secundarios` -> `OrigenGen.HALLAZGO_SECUNDARIO`.
4. Verifica que el conjunto total de `Genes` a analizar tenga al menos 1 `Gen`.
5. Sincroniza (upsert) los símbolos de `Genes` en la tabla local `genes` (`simbolo`, `nombre`, `es_hallazgo_secundario`) y `patologias_genes`.
**Timeout**: `8s` por llamada (hasta 3 intentos con backoff `1s`, `2s`).
**Input**: `Patologia`, `quiere_hallazgos_secundarios`, `genes_seleccionados_simbolos`, `genes_manuales_simbolos`.
**Output on SUCCESS**: Lista deduplicada de tuplas `(Gen, OrigenGen)` (al menos 1 gen) -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(validation_error)`: La lista final de `Genes` a evaluar está vacía o algún símbolo manual tiene formato inválido -> `return 422 Unprocessable Entity` (`code: "LISTA_GENES_VACIA"`).
  - `FAILURE(transient_external_error)` / `FAILURE(timeout)`: La `API de bioinformática` no responde tras 3 intentos -> Si existen los genes cacheados en `patologias_genes` y `genes` (`es_hallazgo_secundario=True`), usa fallback local advirtiendo en logs; si no hay datos en caché local, `return 502 Bad Gateway` (`code: "BIOINFORMATICA_API_UNAVAILABLE", "retryable": true`).

**Observable states during this step**:
  - **Customer/Actor (`Médico`) sees**: `"Obteniendo y validando lista de genes con Bioinformática..."`.
  - **Operator sees**: Tráfico HTTP hacia `API de bioinformática`.
  - **Database**: Upsert de catálogo en `genes` y `patologias_genes`.
  - **Logs**: `[bioinformatica_client] STEP 2 patologia=<nombre> genes_patologia=<n> manuales=<m> secundarios=<s_count>`

---

### STEP 3: Evaluación de `Pompe urgente` y persistencia del `Estudio` y `EstudioGen`
**Actor**: `service` (`estudio_service`) -> `repo` (`estudio_repo`) -> `PostgreSQL`
**Action**:
1. Calcula si el `Estudio` califica como `Pompe urgente`:
   - `es_pompe_urgente = (patologia.nombre.lower() == "pompe") and (edad_en_meses(paciente.fecha_nacimiento, fecha_actual) < 4)`.
2. Determina el estado inicial en la tabla `estudios`:
   - Por definición del LEL (`Verbo: Dar de alta estudio` y `Estado: Creado`), el `Estudio` se crea con `estado = EstadoEstudio.CREADO` y `ausencias = 0`.
3. Inserta la fila en `estudios` (`paciente_id`, `medico_id`, `patologia_sospechada_id`, `estado = EstadoEstudio.CREADO`, `quiere_hallazgos_secundarios`, `obra_social_id`, `es_pompe_urgente`, `ausencias = 0`).
4. Inserta las filas en `estudios_genes` (`estudio_id`, `gen_id`, `origen`) para cada `(Gen, OrigenGen)`.
**Timeout**: `4s`
**Input**: `Paciente`, `Medico`, `Patologia`, `obra_social_id`, `quiere_hallazgos_secundarios`, `es_pompe_urgente`, lista `(Gen, OrigenGen)`.
**Output on SUCCESS**: `Estudio` persistido con `estudio.id` y `estudio.estado == EstadoEstudio.CREADO` -> `GO TO STEP 4`
**Output on FAILURE**:
  - `FAILURE(db_error)` / `FAILURE(timeout)`: Error al insertar en `estudios` o `estudios_genes` -> `session.rollback()` -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Médico`) sees**: `"Registrando estudio de exoma clínico..."`.
  - **Operator sees**: Nuevo registro en transacción en `estudios` con `estado = 'Creado'`.
  - **Database**: Filas insertadas en `estudios` y `estudios_genes`.
  - **Logs**: `[estudio_repo] STEP 3 estudio_id=<id> estado=Creado es_pompe_urgente=<bool> total_genes=<total>`

---

### STEP 4: Generación de `Aviso` para `Administrativo` y confirmación
**Actor**: `service` (`estudio_service`) -> `repo` (`usuario_repo`) -> `PostgreSQL`
**Action**:
1. Crea un `Aviso` en la tabla `avisos` para los usuarios con `Rol.ADMINISTRATIVO` (`canal = CanalAviso.APP`, `mensaje = f"Nuevo estudio #{estudio.id} dado de alta ({len(genes)} genes). Pendiente emitir presupuesto."`) y un `Aviso` informativo para el `Paciente`.
2. Ejecuta `session.commit()` y retorna `201 Created`.
**Timeout**: `3s`
**Input**: `Estudio`, `cantidad_genes`
**Output on SUCCESS**: JSON con el `Estudio` creado -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(db_error)`: Falla el commit transaccional -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Médico`) sees**: Confirmación `"Estudio #<id> dado de alta en estado Creado"` con el detalle de los `Genes` incluidos y si fue marcado como `Pompe urgente`.
  - **Actor (`Administrativo`) sees**: Nuevo `Aviso` en su bandeja de pendientes para emitir el `Presupuesto` del `Estudio`.
  - **Actor (`Paciente`) sees**: El `Estudio` aparece en su historial en estado `Creado` aguardando presupuesto.
  - **Database**: `estudios.estado = EstadoEstudio.CREADO`, `estudios_genes` poblada, `avisos` insertados.
  - **Logs**: `[estudio_service] STEP 4 completado estudio_id=<id>`

---

### ABORT_CLEANUP: Reversión de alta de estudio
**Triggered by**: Fallos en `STEP 3` o `STEP 4`.
**Actions**:
  1. Ejecutar `session.rollback()` para revertir las inserciones en `avisos`, `estudios_genes` y `estudios`.
  2. Retornar respuesta HTTP de error (`500` / `502` / `503`) con `retryable: true`.
**What customer (`Médico`) sees**: Mensaje de error indicando que el estudio no pudo ser registrado y que puede reintentar la operación.
**What operator sees**: Log de error con `paciente_id` y causa del rollback; 0 estudios incompletos en BD.

---

## State Transitions

```
[Sin Estudio]
   |-- (Médico ejecuta Dar de alta estudio y STEP 1-4 tienen éxito)
   |       --> Estudio.estado = EstadoEstudio.CREADO ("Creado")
   |           Estudio.es_pompe_urgente = True (si Patología == Pompe y edad < 4 meses) | False
   |           EstudioGen.origen in {PATOLOGIA, MANUAL, HALLAZGO_SECUNDARIO}
   |
   +-- (Cualquier paso falla -> ABORT_CLEANUP)
           --> [Sin Estudio]
```

---

## Handoff Contracts

### 1. Frontend Médico -> Backend (`router` -> `service`)
**Endpoint**: `POST /api/v1/estudios`
**Payload**:
```json
{
  "paciente_id": 42,
  "patologia_sospechada_id": 2,
  "quiere_hallazgos_secundarios": true,
  "obra_social_id": 5,
  "genes_patologia_simbolos": ["GAA"],
  "genes_manuales_simbolos": ["GLA", "IDUA"]
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "estudio_id": 101,
    "paciente_id": 42,
    "medico_id": 7,
    "patologia_sospechada_id": 2,
    "estado": "Creado",
    "quiere_hallazgos_secundarios": true,
    "obra_social_id": 5,
    "es_pompe_urgente": false,
    "cantidad_genes_total": 6,
    "genes": [
      {"simbolo": "GAA", "origen": "patologia"},
      {"simbolo": "GLA", "origen": "manual"},
      {"simbolo": "IDUA", "origen": "manual"},
      {"simbolo": "BRCA1", "origen": "hallazgo_secundario"},
      {"simbolo": "BRCA2", "origen": "hallazgo_secundario"},
      {"simbolo": "TP53", "origen": "hallazgo_secundario"}
    ]
  }
}
```
**Failure response** (`400` / `403` / `404` / `422` / `502`):
```json
{
  "ok": false,
  "error": "No se pudo obtener la lista de genes desde la API de bioinformática",
  "code": "BIOINFORMATICA_API_UNAVAILABLE",
  "retryable": true
}
```
**Timeout**: `12s`
**ON FAILURE**: Rollback mediante `ABORT_CLEANUP`.

---

### 2. Backend (`bioinformatica_client`) -> `API de bioinformática`
**Endpoint**: `GET /api/v1/patologias/{patologia_nombre}/genes` y `GET /api/v1/genes/hallazgos-secundarios`
**Payload**: Parámetro de ruta `patologia_nombre` (ej. `"Pompe"`, `"Fabry"`, `"MPS1"`, `"Gaucher"`, `"ASMD"`).
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "patologia": "Pompe",
  "genes": [
    {
      "simbolo": "GAA",
      "nombre": "Alpha-glucosidase"
    }
  ],
  "hallazgos_secundarios": [
    {
      "simbolo": "BRCA1",
      "nombre": "Breast cancer type 1 susceptibility protein"
    }
  ]
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Bioinformática API timeout",
  "code": "UPSTREAM_TIMEOUT",
  "retryable": true
}
```
**Timeout**: `8s` (3 intentos con backoff `1s`, `2s`).
**ON FAILURE**: Usar caché en `patologias_genes` / `genes` si existe; de lo contrario abortar con `502 Bad Gateway`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Registro en `estudios` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |
| Registros en `estudios_genes` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` (cascada `ondelete="CASCADE"`) |
| Registros en `avisos` | STEP 4 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/estudios.py`, `Estudio` posee exactamente las columnas `paciente_id`, `medico_id`, `patologia_sospechada_id`, `estado` (`default=EstadoEstudio.CREADO`), `quiere_hallazgos_secundarios`, `obra_social_id`, `es_pompe_urgente` y `ausencias`. | Low | STEP 3 | 100% alineado con el modelo SQLAlchemy. |
| RC-2 | En `app/src/core/models/estudios.py`, `EstudioGen` tiene clave primaria compuesta `(estudio_id, gen_id)` y columna `origen` (`Enum(OrigenGen)` con valores `PATOLOGIA`, `MANUAL`, `HALLAZGO_SECUNDARIO`). Si un mismo gen viniera por dos vías, se debe deduplicar priorizando `PATOLOGIA` > `MANUAL` > `HALLAZGO_SECUNDARIO` para no violar la PK compuesta. | Medium | STEP 2 & STEP 3 | Regla de deduplicación de `(estudio_id, gen_id)` incorporada en STEP 2. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path estudio estándar sin hallazgos secundarios** | `POST /api/v1/estudios` por un `Médico` para un `Paciente` adulto con `Patología` Fabry y 0 genes manuales. | Retorna `201 Created`; `Estudio.estado == EstadoEstudio.CREADO`, `es_pompe_urgente == False`, `EstudioGen` creado con `origen = OrigenGen.PATOLOGIA`. |
| **TC-02: Happy path con genes manuales y hallazgos secundarios** | `POST /api/v1/estudios` con `quiere_hallazgos_secundarios = True` y 2 `genes_manuales_simbolos`. | Retorna `201 Created`; se insertan filas en `estudios_genes` con los tres orígenes (`PATOLOGIA`, `MANUAL`, `HALLAZGO_SECUNDARIO`) sin duplicar `gen_id`. |
| **TC-03: Detección automática de Pompe urgente** | `POST /api/v1/estudios` para un `Paciente` nacido hace 2 meses con `Patología` `"Pompe"`. | Retorna `201 Created`; `Estudio.es_pompe_urgente == True` y `Estudio.estado == EstadoEstudio.CREADO`. |
| **TC-04: Paciente con Pompe pero mayor de 4 meses** | `POST /api/v1/estudios` para un `Paciente` de 6 meses con `Patología` `"Pompe"`. | Retorna `201 Created`; `Estudio.es_pompe_urgente == False`. |
| **TC-05: Rol no autorizado** | `POST /api/v1/estudios` invocado por un usuario con `Rol.PACIENTE` o `Rol.ADMINISTRATIVO`. | Retorna `403 Forbidden` (`code: "FORBIDDEN_ROLE"`). |
| **TC-06: Paciente o Patología inexistente** | `POST /api/v1/estudios` con `paciente_id = 99999`. | Retorna `404 Not Found` (`code: "RECURSO_NO_ENCONTRADO"`). |
| **TC-07: Caída de API de bioinformática sin caché local** | `POST /api/v1/estudios` cuando `bioinformatica_client` lanza timeout en los 3 intentos y no hay genes cacheados. | Retorna `502 Bad Gateway` (`code: "BIOINFORMATICA_API_UNAVAILABLE"`); 0 registros en `estudios`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El cálculo de menor de 4 meses para `Pompe urgente` se evalúa comparando la fecha actual con `paciente.fecha_nacimiento` (< 4 meses calendario o < 120 días). | `.ai/2-Glosario_LEL.md` (`Objeto: Pompe urgente`) y `app/src/core/models/estudios.py` línea 31. | Bajo. |
| A2 | Aunque el estudio tenga `obra_social_id` asignada al momento del alta, nace en `EstadoEstudio.CREADO` hasta que se emite el `Presupuesto` (Escenario 3) y pasa a `Pendiente de autorización` / gestión de autorización (Escenario 4). | `.ai/2-Glosario_LEL.md` (`Verbo: Dar de alta estudio` -> `El estudio pasa a Creado`, `Estado: Creado`). | Bajo. |

## Open Questions

- Si un `Médico` agrega manualmente un `Gen` que también forma parte de los `Hallazgos secundarios`, ¿se prioriza `OrigenGen.MANUAL` o `OrigenGen.HALLAZGO_SECUNDARIO` en `estudios_genes`? *(En esta spec se prioriza `PATOLOGIA` > `MANUAL` > `HALLAZGO_SECUNDARIO`).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/estudios.py` y `clinica.py`. | Marcada como `Approved`. |
