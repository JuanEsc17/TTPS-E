# WORKFLOW: Escenario 23 – Gestionar una patología
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-23`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Gerente médico` |
| **Objetos** | `Patología`, `Síntoma`, `Síntoma cardinal`, `Síntoma secundario`, `SNOMED`, `Gen`, `API de bioinformática` |
| **Verbos** | *(Dar de alta y modificar `Patología`, definir `Síntoma cardinal` y `Síntomas secundarios`)* |
| **Estados** | *(No aplica transición de estado de `Estudio`; crea o actualiza `Patologia`, `Sintoma`, `PatologiaSintoma` y sincroniza `PatologiaGen`)* |

---

## Overview

- **Objetivo**: Registrar o modificar una **patología** y sus **síntomas** asociados (**síntoma cardinal** y **síntomas secundarios**).
- **Contexto**: El **gerente médico** administra la información de las **patologías** disponibles en el laboratorio (enfermedad de Fabry, enfermedad de Pompe, mucopolisacaridosis 1, Gaucher, ASMD) para que el sistema pueda validar la sintomatología cuando un **médico** ejecuta `Dar de alta paciente`.
- **Recursos**: `Patología` (`nombre`, `descripcion`), `Síntoma cardinal` (único por **patología**, codificado en **SNOMED**), `Síntomas secundarios` (lista de síntomas codificados en **SNOMED**).
- **Episodios**:
  1. El **gerente médico** registra una nueva **patología** o selecciona una **patología** existente para modificarla.
  2. El **gerente médico** registra su **síntoma cardinal** (buscado/validado en **SNOMED**).
  3. El **gerente médico** registra sus **síntomas secundarios** (buscados/validados en **SNOMED**).
  4. El sistema guarda la información de la **patología** en `patologias`, `sintomas` y `patologias_sintomas` (garantizando el índice único parcial `uq_un_cardinal_por_patologia`) y sincroniza opcionalmente los **genes** asociados desde la **API de bioinformática** en `patologias_genes`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Gerente médico` (Sujeto LEL) | Usuario autenticado con `Rol.GERENTE_MEDICO` que da de alta o modifica una **patología** y define su **síntoma cardinal** y sus **síntomas secundarios**. |
| `patologias_router` (`app/src/routers/`) | Capa `router`: autoriza exclusivamente a `Rol.GERENTE_MEDICO` y recibe las peticiones `POST /api/v1/patologias` (alta) y `PUT /api/v1/patologias/{patologia_id}` (modificación). |
| `patologia_service` (`app/src/services/`) | Capa `service`: valida que exista exactamente un **síntoma cardinal**, que los **síntomas secundarios** no dupliquen al **síntoma cardinal**, asegura que cada **síntoma** tenga su código **SNOMED** (`snomed_id`, `descripcion`), y coordina la persistencia y sincronización de **genes**. |
| `clinica_repo` (`app/src/repos/`) | Capa `repo`: realiza upsert de `Sintoma` por `snomed_id`, crea o actualiza `Patologia`, reemplaza las asociaciones en `PatologiaSintoma` y actualiza `PatologiaGen`. |
| `snomed_client` / `bioinformatica_client` (`app/src/clients/`) | Capa `clients`: `snomed_client` permite buscar términos en **SNOMED** y `bioinformatica_client` consulta los **genes** asociados a la **patología** en la **API de bioinformática**. |
| `PostgreSQL` | Persiste `patologias`, `sintomas`, `patologias_sintomas` (con el índice único `uq_un_cardinal_por_patologia`), `genes` y `patologias_genes`. |

---

## Prerequisites

- El usuario ha iniciado sesión con `rol = Rol.GERENTE_MEDICO` y cuenta con perfil activo en `usuarios` y `medicos`.
- Para la búsqueda de **síntomas**, el catálogo **SNOMED** (en la tabla `sintomas` o vía **SNOMED** API) se encuentra disponible.
- Si la operación es una modificación (`PUT /api/v1/patologias/{patologia_id}`), la **patología** debe existir previamente en la tabla `patologias`.

---

## Trigger

El **gerente médico** envía el formulario de creación o edición de una **patología** con su **síntoma cardinal** y sus **síntomas secundarios**.
- **Endpoints HTTP**:
  - Alta: `POST /api/v1/patologias`
  - Modificación: `PUT /api/v1/patologias/{patologia_id}`

---

## Workflow Tree

### STEP 1: Autorización de `Gerente médico` y validación estructural de la patología y sus síntomas
**Actor**: `patologias_router` -> `patologia_service`
**Action**:
1. Verifica que el usuario autenticado posea estrictamente `Rol.GERENTE_MEDICO`.
2. Valida que `nombre` esté presente (`1..120` caracteres), que se haya especificado exactamente un `sintoma_cardinal` (`{ snomed_id, descripcion }`) y una lista `sintomas_secundarios` (al menos 2 **síntomas secundarios** para que la regla de validación de alta de **paciente** con 2 secundarios sea satisfacible, todos con `snomed_id` y `descripcion` válidos).
3. Verifica que el `snomed_id` del **síntoma cardinal** no esté repetido dentro de `sintomas_secundarios` y que no haya códigos `snomed_id` duplicados dentro de `sintomas_secundarios`.
**Timeout**: `2s`
**Input**: `{ patologia_id: Optional[int], nombre: str, descripcion: Optional[str], sintoma_cardinal: { snomed_id: str, descripcion: str }, sintomas_secundarios: list[{ snomed_id: str, descripcion: str }] }`
**Output on SUCCESS**: Payload validado y deduplicado -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario autenticado tiene `Rol.MEDICO`, `Rol.ADMINISTRATIVO` u otro rol distinto de `Rol.GERENTE_MEDICO` -> retorna `403 Forbidden` (`code: "SOLO_GERENTE_MEDICO"`).
  - `FAILURE(validation_error)`: Falta `nombre`, falta `sintoma_cardinal`, hay menos de 2 `sintomas_secundarios`, o el `snomed_id` del **síntoma cardinal** también figura como **síntoma secundario** -> retorna `400 Bad Request` (`code: "ESTRUCTURA_PATOLOGIA_INVALIDA"`).
  - `FAILURE(timeout)`: Supera `2s` -> retorna `504 Gateway Timeout` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Gerente médico`) sees: Indicador "Validando configuración de la patología...".
  - Operator sees: Petición `POST` o `PUT` en `/api/v1/patologias` en validación.
  - Database: Sin escrituras.
  - Logs: `[patologia_service] step_1_validar_patologia gerente_usuario_id=<id> nombre=<nombre> operacion=<alta|modificacion>`

---

### STEP 2: Verificación de unicidad de nombre de patología y resolución/upsert de síntomas SNOMED
**Actor**: `patologia_service` -> `clinica_repo` (+ `snomed_client` si se requiere validar término externo) -> `PostgreSQL`
**Action**:
1. Si es alta (`POST`), verifica que no exista otra fila en `patologias` con el mismo `nombre`. Si es modificación (`PUT`), obtiene la fila `patologias` por `patologia_id` con `SELECT ... FOR UPDATE` y verifica que ningún otro registro distinto tenga el nuevo `nombre`.
2. Para el **síntoma cardinal** y cada **síntoma secundario**, busca el `snomed_id` en la tabla `sintomas`; si aún no está cacheado localmente en `sintomas`, lo inserta con su `(snomed_id, descripcion)` validado.
**Timeout**: `4s`
**Input**: `{ patologia_id: Optional[int], nombre: str, sintoma_cardinal: dict, sintomas_secundarios: list[dict] }`
**Output on SUCCESS**: `{ patologia_existente: Optional[Patologia], sintoma_cardinal_id: int, sintomas_secundarios_ids: list[int] }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(not_found)`: En `PUT /api/v1/patologias/{patologia_id}`, no existe `patologias.id == patologia_id` -> retorna `404 Not Found` (`code: "PATOLOGIA_NO_ENCONTRADA"`).
  - `FAILURE(conflict)`: Ya existe otra **patología** con el mismo `nombre` (`UNIQUE(nombre)` en `patologias`) -> retorna `409 Conflict` (`code: "PATOLOGIA_NOMBRE_DUPLICADO"`).
  - `FAILURE(timeout)`: Supera `4s` -> reintenta 1 vez (`500ms`); si falla, ejecuta `ABORT_CLEANUP` y retorna `503 Service Unavailable`.

**Observable states during this step**:
  - Customer/Actor (`Gerente médico`) sees: "Normalizando síntomas en SNOMED...".
  - Operator sees: Transacción iniciada en `PostgreSQL`; lectura/upsert en `sintomas`.
  - Database: Filas de `sintomas` aseguradas por `snomed_id`.
  - Logs: `[clinica_repo] step_2_resolver_sintomas_snomed nombre=<nombre> total_sintomas=<1+N>`

---

### STEP 3: Persistencia de `Patologia` y reemplazo atómico de `PatologiaSintoma`
**Actor**: `patologia_service` -> `clinica_repo` -> `PostgreSQL`
**Action**:
1. Si es alta, inserta la fila en `patologias` (`nombre`, `descripcion`). Si es modificación, actualiza `patologias.nombre`, `patologias.descripcion` y `patologias.updated_at = func.now()`.
2. En caso de modificación, elimina las filas previas de `patologias_sintomas` para `patologia_id` (`DELETE FROM patologias_sintomas WHERE patologia_id = :id`) y ejecuta `flush()` antes de insertar las nuevas para respetar en todo momento el índice único parcial `uq_un_cardinal_por_patologia` (`WHERE es_cardinal`).
3. Inserta en `patologias_sintomas`:
   - 1 fila con `(patologia_id, sintoma_id = sintoma_cardinal_id, es_cardinal = True)`.
   - N filas con `(patologia_id, sintoma_id = sec_id, es_cardinal = False)` para cada **síntoma secundario**.
4. Ejecuta `COMMIT` de la transacción en `PostgreSQL`.
**Timeout**: `4s`
**Input**: `{ patologia: Patologia, sintoma_cardinal_id: int, sintomas_secundarios_ids: list[int] }`
**Output on SUCCESS**: `Patologia` y `PatologiaSintoma` persistidos -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(conflict)`: Violación concurrente de `UNIQUE(nombre)` en `patologias` o del índice `uq_un_cardinal_por_patologia` en `patologias_sintomas` -> `ABORT_CLEANUP` (`ROLLBACK`) -> retorna `409 Conflict` (`code: "CONFLICTO_CONCURRENTE_PATOLOGIA"`).
  - `FAILURE(database_error)` / `FAILURE(timeout)`: Error de escritura en `PostgreSQL` -> `ABORT_CLEANUP` (`ROLLBACK`) -> retorna `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Gerente médico`) sees: "Guardando patología y síntomas asociados...".
  - Operator sees: Escritura en `patologias` y `patologias_sintomas`.
  - Database:
    - `patologias`: fila creada o actualizada con `updated_at = now()`.
    - `patologias_sintomas`: exactamente 1 fila con `es_cardinal = true` y N filas con `es_cardinal = false` para `patologia_id`.
  - Logs: `[clinica_repo] step_3_patologia_persistida patologia_id=<id> sintoma_cardinal_id=<id> secundarios_count=<n>`

---

### STEP 4: Sincronización de genes de la patología con la `API de bioinformática` (no bloqueante ante caída externa)
**Actor**: `patologia_service` -> `bioinformatica_client` -> `clinica_repo` -> `PostgreSQL`
**Action**:
1. Consulta a la **API de bioinformática** (`GET /api/v1/bioinformatica/patologias/{nombre}/genes`) para obtener los **genes** asociados a la **patología**.
2. Si la **API de bioinformática** responde exitosamente, hace upsert de cada `Gen` (`simbolo`, `nombre`, `es_hallazgo_secundario = False`) en `genes` y sincroniza la tabla puente `patologias_genes`.
3. Si la **API de bioinformática** presenta un fallo transitorio tras reintentos, la **patología** y sus **síntomas** **se mantienen guardados** (ya que el objetivo del Escenario 23 es guardar la patología y sus síntomas) y se devuelve `genes_sincronizados: false` con advertencia para sincronización diferida al elegir genes.
**Timeout**: `5s` (con 2 reintentos y backoff de `500ms`, `1s`)
**Input**: `{ patologia_id: int, nombre: str }`
**Output on SUCCESS**: `{ patologia_id: int, nombre: str, sintoma_cardinal: dict, sintomas_secundarios: list[dict], genes_sincronizados: bool }` -> Retorna `201 Created` (en alta) o `200 OK` (en modificación).
**Output on FAILURE**:
  - `FAILURE(transient_external_error)`: Timeout o error `5xx` de la **API de bioinformática** tras 2 reintentos -> registra warning en logs, mantiene el `COMMIT` del `STEP 3` y retorna `201`/`200` con `genes_sincronizados: false`.

**Observable states during this step**:
  - Customer/Actor (`Gerente médico`) sees: Confirmación "Patología guardada correctamente con su síntoma cardinal y síntomas secundarios."
  - Operator sees: `patologias`, `patologias_sintomas` y (si la API respondió) `patologias_genes` actualizados.
  - Database: `patologias` y `patologias_sintomas` confirmados; `genes` y `patologias_genes` actualizados si `genes_sincronizados == True`.
  - Logs: `[patologia_service] step_4_sincronizar_genes_patologia patologia_id=<id> genes_sincronizados=<bool>`

---

### ABORT_CLEANUP: Reversión de alta o modificación de patología
**Triggered by**: Fallo en `STEP 2` o `STEP 3` (error de base de datos, violación de restricción única o timeout SQL).
**Actions** (in order):
  1. Ejecutar `ROLLBACK` de la transacción SQL para restaurar el estado exacto previo de `patologias` y `patologias_sintomas`.
  2. Registrar el error en los logs del sistema.
**What customer (`Gerente médico`) sees**: Mensaje de error explicando la causa (`409` nombre duplicado o `503` error de base de datos) sin pérdida de los síntomas que ya estaban guardados antes de la edición.
**What operator sees**: Transacción revertida limpiamente; el índice `uq_un_cardinal_por_patologia` permanece íntegro.

---

## State Transitions

```
[Patología inexistente]
   -> (POST /api/v1/patologias: STEP 1-4 exitosos)
   -> [Patología activa con 1 Síntoma cardinal (es_cardinal=True) y N Síntomas secundarios (es_cardinal=False)]

[Patología activa (versión V1 de síntomas)]
   -> (PUT /api/v1/patologias/{id}: STEP 1-4 exitosos)
   -> [Patología activa (versión V2 de síntomas reemplazada atómicamente)]

[Patología activa (versión V1 de síntomas)]
   -> (PUT /api/v1/patologias/{id}: fallo en STEP 2 o STEP 3 -> ABORT_CLEANUP)
   -> [Patología activa (conserva intacta la versión V1 de síntomas)]
```

---

## Handoff Contracts

### 1. Frontend (`Gerente médico`) -> Backend (`patologias_router`) – Alta / Modificación
**Endpoint**: `POST /api/v1/patologias` (o `PUT /api/v1/patologias/{patologia_id}`)
**Payload**:
```json
{
  "nombre": "Enfermedad de Fabry",
  "descripcion": "Trastorno lisosomal ligado al cromosoma X por deficiencia de alfa-galactosidasa A.",
  "sintoma_cardinal": {
    "snomed_id": "279079003",
    "descripcion": "Acroparestesia"
  },
  "sintomas_secundarios": [
    {
      "snomed_id": "79890006",
      "descripcion": "Angioqueratoma"
    },
    {
      "snomed_id": "52553005",
      "descripcion": "Hipohidrosis"
    },
    {
      "snomed_id": "55822004",
      "descripcion": "Hipertrofia ventricular izquierda"
    }
  ]
}
```
**Success response** (`201 Created` en alta / `200 OK` en modificación):
```json
{
  "ok": true,
  "data": {
    "patologia_id": 1,
    "nombre": "Enfermedad de Fabry",
    "descripcion": "Trastorno lisosomal ligado al cromosoma X por deficiencia de alfa-galactosidasa A.",
    "sintoma_cardinal": {
      "sintoma_id": 10,
      "snomed_id": "279079003",
      "descripcion": "Acroparestesia",
      "es_cardinal": true
    },
    "sintomas_secundarios": [
      {
        "sintoma_id": 14,
        "snomed_id": "79890006",
        "descripcion": "Angioqueratoma",
        "es_cardinal": false
      },
      {
        "sintoma_id": 15,
        "snomed_id": "52553005",
        "descripcion": "Hipohidrosis",
        "es_cardinal": false
      },
      {
        "sintoma_id": 16,
        "snomed_id": "55822004",
        "descripcion": "Hipertrofia ventricular izquierda",
        "es_cardinal": false
      }
    ],
    "genes_sincronizados": true
  }
}
```
**Failure response** (`400` / `403` / `404` / `409` / `503`):
```json
{
  "ok": false,
  "error": "El síntoma cardinal no puede estar repetido en la lista de síntomas secundarios.",
  "code": "ESTRUCTURA_PATOLOGIA_INVALIDA",
  "retryable": false
}
```
**Timeout**: `10s`

### 2. `patologia_service` -> `bioinformatica_client` (`API de bioinformática`)
**Endpoint**: `GET /api/v1/bioinformatica/patologias/{nombre}/genes`
**Success response**:
```json
{
  "ok": true,
  "patologia": "Enfermedad de Fabry",
  "genes": [
    {
      "simbolo": "GLA",
      "nombre": "Galactosidase alpha",
      "es_hallazgo_secundario": false
    }
  ]
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Bioinformatics upstream timeout",
  "code": "BIOINFORMATICA_TIMEOUT",
  "retryable": true
}
```
**Timeout**: `5s`
**ON FAILURE**: Reintentar 2 veces con backoff (`500ms`, `1s`); si persiste, devolver la patología creada con `genes_sincronizados: false`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Fila nueva o modificada en `patologias` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` transaccional |
| Filas en `patologias_sintomas` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` transaccional |
| Filas nuevas en `sintomas` | Step 2 | `ABORT_CLEANUP` | `ROLLBACK` transaccional si `STEP 3` falla |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/clinica.py` (líneas 49-53), `PatologiaSintoma` define el índice parcial único `Index("uq_un_cardinal_por_patologia", "patologia_id", unique=True, sqlite_where=text("es_cardinal"), postgresql_where=text("es_cardinal"))`. | High | STEP 3 | En `STEP 3` se exige `DELETE` + `flush()` antes de insertar el nuevo síntoma cardinal al modificar una patología, evitando violación transitoria del índice único parcial. |
| RC-2 | En `app/src/core/models/clinica.py`, la clave primaria de `PatologiaSintoma` es `(patologia_id, sintoma_id)`. Por ello, un mismo `sintoma_id` no puede ser a la vez cardinal y secundario de la misma patología. | Medium | STEP 1 | Validado explícitamente en `STEP 1` (`FAILURE(validation_error)` si el `snomed_id` cardinal se repite en secundarios). |
| RC-3 | No existen aún `patologias_router.py`, `patologia_service.py` ni `clinica_repo.py`. | Medium | Actors | Documentados para implementación en el flujo SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Registrar una nueva patología | `POST /api/v1/patologias` por `Rol.GERENTE_MEDICO` con 1 **síntoma cardinal** y 3 **síntomas secundarios** | Retorna `201 Created`; crea fila en `patologias`, 1 fila en `patologias_sintomas` con `es_cardinal=True` y 3 con `es_cardinal=False`. |
| `TC-02`: Happy path – Modificar síntoma cardinal y secundarios de una patología existente | `PUT /api/v1/patologias/1` por `Rol.GERENTE_MEDICO` cambiando el **síntoma cardinal** y la lista de **síntomas secundarios** | Retorna `200 OK`; reemplaza atómicamente las filas en `patologias_sintomas` respetando `uq_un_cardinal_por_patologia`. |
| `TC-03`: Acceso denegado a médico común o administrativo | `POST /api/v1/patologias` autenticado con `Rol.MEDICO` o `Rol.ADMINISTRATIVO` | Retorna `403 Forbidden` (`code: "SOLO_GERENTE_MEDICO"`). |
| `TC-04`: Síntoma cardinal repetido como secundario | `POST /api/v1/patologias` donde el mismo `snomed_id` aparece en `sintoma_cardinal` y en `sintomas_secundarios` | Retorna `400 Bad Request` (`code: "ESTRUCTURA_PATOLOGIA_INVALIDA"`). |
| `TC-05`: Patología sin síntoma cardinal o con menos de 2 secundarios | `POST /api/v1/patologias` con `sintoma_cardinal = null` o solo 1 síntoma secundario | Retorna `400 Bad Request` (`code: "ESTRUCTURA_PATOLOGIA_INVALIDA"`). |
| `TC-06`: Nombre de patología duplicado | `POST /api/v1/patologias` con un `nombre` ya existente en `patologias` | Retorna `409 Conflict` (`code: "PATOLOGIA_NOMBRE_DUPLICADO"`). |
| `TC-07`: Modificación de patología inexistente | `PUT /api/v1/patologias/9999` | Retorna `404 Not Found` (`code: "PATOLOGIA_NO_ENCONTRADA"`). |
| `TC-08`: Resiliencia ante caída de `API de bioinformática` | `POST /api/v1/patologias` cuando `bioinformatica_client` lanza timeout en los 3 intentos | La **patología** y sus **síntomas** quedan persistidos en BD y retorna `201 Created` con `genes_sincronizados: false`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Toda **patología** debe tener exactamente un **síntoma cardinal** (impuesto por el índice único `uq_un_cardinal_por_patologia` en `clinica.py`) y al menos dos **síntomas secundarios** (para permitir la regla de validación del alta de paciente con dos síntomas secundarios). | `app/src/core/models/clinica.py` (líneas 49-53) y `.ai/2-Glosario_LEL.md` | Bajo. |
| A2 | Modificar los **síntomas** de una **patología** aplica a las validaciones de altas futuras de **pacientes** y no invalida retrospectivamente a los **pacientes** ya dados de alta. | `.ai/1-Entrevista.md` (líneas 398-414) | Bajo. |

## Open Questions

- Ninguna. El modelo `Patologia`, `Sintoma` y `PatologiaSintoma` en `app/src/core/models/clinica.py` refleja fielmente las reglas del LEL.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/clinica.py` (`Patologia`, `Sintoma`, `PatologiaSintoma`, `uq_un_cardinal_por_patologia`). | Aprobada para implementación. |
