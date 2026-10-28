# WORKFLOW: Escenario 36 – Cargar los síntomas del paciente con SNOMED
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-36`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Médico** | `Usuario` (`rol = Rol.MEDICO` o `Rol.GERENTE_MEDICO`) + perfil `Medico` (`medicos.id`, médico tratante) |
| **Sujetos** | **Paciente** | Modelo `Paciente` (`pacientes`: `id`, `diagnostico_presuntivo_id`, relación `sintomas`) |
| **Objetos** | **SNOMED** | Cliente HTTP externo (`app/src/clients/snomed_client.py`) y catálogo local sincronizado en tabla `sintomas` (`snomed_id`, `descripcion`) |
| **Objetos** | **Síntoma** | Modelo `Sintoma` (`sintomas`: `id`, `snomed_id`, `descripcion`) y tabla asociativa `PacienteSintoma` (`pacientes_sintomas`) |
| **Objetos** | **Patología** | Modelo `Patologia` (`patologias`: `id`, `nombre`, `descripcion`) |
| **Objetos** | **Síntoma cardinal** | Fila en `PatologiaSintoma` (`patologias_sintomas`) con `es_cardinal == True` (índice único `uq_un_cardinal_por_patologia`) |
| **Objetos** | **Síntoma secundario** | Fila en `PatologiaSintoma` (`patologias_sintomas`) con `es_cardinal == False` |
| **Verbos** | **Cargar síntomas** | Buscar términos en **SNOMED** al escribir, seleccionarlos y validarlos contra la **patología** |
| **Verbos** | **Dar de alta paciente** | Registrar al **paciente** solo si la lista de **síntomas** supera la validación contra la **patología** |
| **Estados** | *(No altera `EstadoEstudio`)* | Condición bloqueante para el alta del **paciente** previa al alta de su **estudio** |

---

## Overview

- **Objetivo:** Registrar los **síntomas** del **paciente** utilizando terminología médica estandarizada **SNOMED** y validarlos contra la **patología** sospechada (diagnóstico presuntivo) antes de permitir el alta del **paciente**.
- **Contexto:** El **médico** tratante está dando de alta a un **paciente**, ya indicó el diagnóstico presuntivo (`diagnostico_presuntivo_id`) y debe cargar la lista de **síntomas** del **paciente**.
- **Recursos:** **SNOMED** (`snomed_client` / tabla `sintomas`), lista de **síntomas** (`pacientes_sintomas`), diagnóstico presuntivo (`Paciente.diagnostico_presuntivo_id`), **patología** (`patologias`), **síntoma cardinal** (`PatologiaSintoma.es_cardinal == True`), **síntomas secundarios** (`PatologiaSintoma.es_cardinal == False`).
- **Episodios:**
  1. El **médico** escribe las primeras letras de un **síntoma** (mínimo 3 caracteres).
  2. El sistema consulta **SNOMED** y muestra una lista de **síntomas** coincidentes.
  3. El **médico** elige el **síntoma** de la lista.
  4. El sistema agrega el **síntoma** a la lista del **paciente**.
  5. El sistema valida los **síntomas** contra la **patología**: debe haber al menos el **síntoma cardinal** (`es_cardinal == True`) o al menos dos **síntomas secundarios** (`es_cardinal == False`) definidos para esa **patología**.
  6. El sistema no permite **dar de alta paciente** si la validación falla.

**Resumen del flujo:**
1. **Búsqueda autocompletada en SNOMED (`STEP 1` y `STEP 2`):** A medida que el **médico** escribe al menos 3 letras (`GET /api/snomed/sintomas?q=<prefijo>`), el backend consulta al módulo **SNOMED** vía `snomed_client` (con fallback a búsqueda indexada por prefijo/subcadena sobre `sintomas.descripcion` en caso de indisponibilidad transitoria del servicio externo) y devuelve la lista de términos con su `snomed_id` y `descripcion`.
2. **Selección y validación contra la patología (`STEP 3` y `STEP 4`):** El **médico** agrega los **síntomas** seleccionados a la lista del **paciente** y el sistema verifica contra la tabla `patologias_sintomas` de la `Patologia` (`diagnostico_presuntivo_id`) si el conjunto seleccionado incluye el **síntoma cardinal** (`es_cardinal == True`) o `>= 2` **síntomas secundarios** (`es_cardinal == False`).
3. **Persistencia o bloqueo del alta (`STEP 5`):** Al confirmar **Dar de alta paciente** (`POST /api/pacientes`), si la regla de **síntoma cardinal** o **dos síntomas secundarios** no se cumple, el servicio rechaza la operación con `422 Unprocessable Entity` (`SINTOMAS_NO_VALIDAN_PATOLOGIA`) e impide crear el registro en `usuarios` y `pacientes`. Si se cumple, sincroniza los términos en `sintomas` (upsert por `snomed_id`) y guarda el **paciente** junto con sus filas en `pacientes_sintomas` dentro de una única transacción.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Médico** (Sujeto LEL) | Escribe las primeras letras de cada **síntoma**, selecciona los términos **SNOMED**, indica el diagnóstico presuntivo y solicita el alta del **paciente**. |
| **Router HTTP** (`app/src/routers/snomed.py`, `app/src/routers/pacientes.py`) | Expone `GET /api/snomed/sintomas` para el autocompletado y `POST /api/pacientes` (más `POST /api/patologias/{patologia_id}/validar-sintomas`) para validar y persistir. |
| **Servicio Clínico / Pacientes** (`app/src/services/clinica_service.py`, `paciente_service.py`) | Orquesta la consulta a **SNOMED**, ejecuta la regla de validación (`cardinal >= 1 OR secundarios >= 2`) contra `PatologiaSintoma` y controla la transacción de alta del **paciente**. |
| **Cliente SNOMED** (`app/src/clients/snomed_client.py`) | Consulta vía `httpx` la API del módulo externo de **SNOMED** por prefijo de texto. |
| **Repositorio Clínico y de Pacientes** (`app/src/repos/clinica_repo.py`, `paciente_repo.py`) | Consulta `sintomas`, `patologias` y `patologias_sintomas`; realiza upsert de `Sintoma` por `snomed_id` e inserta en `pacientes` y `pacientes_sintomas`. |
| **PostgreSQL** (`db`) | Garantiza la unicidad de `sintomas.snomed_id`, `uq_un_cardinal_por_patologia` en `patologias_sintomas` y la atomicidad del alta de `Paciente`. |

---

## Prerequisites

- **Sesión y Rol:** El usuario autenticado debe tener sesión activa con `Usuario.rol in (Rol.MEDICO, Rol.GERENTE_MEDICO)` y perfil en `medicos`.
- **Datos existentes en `app/src/core/models/`:**
  - Existe en la tabla `patologias` la **patología** elegida como diagnóstico presuntivo (`diagnostico_presuntivo_id`).
  - Existen en `patologias_sintomas` las asociaciones de esa **patología** con su **síntoma cardinal** (`es_cardinal = True`) y sus **síntomas secundarios** (`es_cardinal = False`), dadas de alta previamente por el **gerente médico**.
- **Estado previo del `Estudio`:** No aplica (`N/A`; este escenario ocurre durante el alta del **paciente**, antes de **dar de alta estudio**).

---

## Trigger

1. **Autocompletado SNOMED (Episodios 1-2):** El **médico** escribe `>= 3` letras en el buscador de **síntomas** -> `GET /api/snomed/sintomas?q=<prefijo>`.
2. **Validación y alta del paciente (Episodios 3-6):** El **médico** selecciona los **síntomas** de la lista y envía el alta del **paciente** -> `POST /api/pacientes` (o pre-valida en vivo mediante `POST /api/patologias/{patologia_id}/validar-sintomas`).

---

## Workflow Tree

### STEP 1: Búsqueda de síntomas por prefijo en SNOMED (Episodios 1 y 2)
**Actor**: **Médico** -> Router (`snomed.py`) -> Servicio (`clinica_service.py`) -> Cliente SNOMED (`snomed_client.py`) / Repositorio (`clinica_repo.py`)
**Action**:
  1. Valida que el parámetro `q` (texto escrito por el **médico**) tenga al menos 3 caracteres no vacíos (`len(q.strip()) >= 3`).
  2. Consulta a `snomed_client.buscar_sintomas(q)` (`GET /external/snomed/concepts?q=<q>&limit=20`).
  3. Si la API externa de **SNOMED** responde con éxito, combina/sincroniza los resultados con la tabla local `sintomas` (`snomed_id`, `descripcion`). Si la API externa sufre un timeout o caída transitoria, realiza fallback consultando la tabla local `sintomas` (`WHERE descripcion ILIKE '<q>%' OR descripcion ILIKE '%<q>%'`) para no interrumpir la consulta médica.
**Timeout**: `3s` (llamada externa con timeout de `2s` + fallback local en `< 0.5s`).
**Input**: `{ q: "cef", limit: 20 }`
**Output on SUCCESS**: `{ resultados: list[{ snomed_id: str, descripcion: str }] }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(unauthorized / forbidden)`: Usuario sin sesión o sin rol médico -> retornar `401` / `403`.
  - `FAILURE(validation_error)`: `len(q.strip()) < 3` -> retornar `422 Unprocessable Entity` (`PREFIJO_DEMASIADO_CORTO`, indicando que debe ingresar al menos 3 letras).
  - `FAILURE(external_and_db_failure)`: Falla tanto el servicio externo de **SNOMED** como la consulta a PostgreSQL -> retornar `502 Bad Gateway` (`SNOMED_NO_DISPONIBLE`, `retryable=True`).

**Observable states during this step**:
  - Customer/Actor (**Médico**) sees: Desplegable autocompletado con los **síntomas** coincidentes de **SNOMED** (ej. `"25064002 - Cefalea"`, `"162306004 - Cefalea tensional"`).
  - Operator sees: Petición `GET /api/snomed/sintomas?q=cef`.
  - Database: Lectura sobre `sintomas`.
  - Logs: `[clinica_service] step=1_busqueda_snomed q='cef' resultados=8 fuente=<api|local_fallback>`

---

### STEP 2: Selección de síntomas y revinculación con el catálogo local `sintomas` (Episodios 3 y 4)
**Actor**: **Médico** -> Router (`pacientes.py`) -> Servicio (`paciente_service.py`) -> Repositorio (`clinica_repo.py`)
**Action**:
  1. El **médico** selecciona uno o más términos de la lista devuelta por **SNOMED** y los agrega a la lista de **síntomas** del **paciente**, enviando sus `snomed_ids` (y `descripcion`) junto con el `diagnostico_presuntivo_id`.
  2. El repositorio verifica que la `Patologia` (`diagnostico_presuntivo_id`) exista en `patologias` y recupera su configuración de `PatologiaSintoma` (`patologias_sintomas` junto con los `Sintoma.snomed_id` asociados a esa patología).
  3. Para cada término seleccionado por el **médico**, asegura que exista en la tabla local `sintomas` (si es un término válido de **SNOMED** aún no cacheado localmente, hace `flush` de la fila en `sintomas`).
**Timeout**: `2s`
**Input**:
```json
{
  "diagnostico_presuntivo_id": 1,
  "sintomas_seleccionados": [
    { "snomed_id": "225566008", "descripcion": "Acroparestesia" },
    { "snomed_id": "4556007", "descripcion": "Hipohidrosis" }
  ]
}
```
**Output on SUCCESS**: `{ patologia: Patologia, sintomas_entidades: list[Sintoma], mapa_patologia_sintomas: dict[int, bool] }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(validation_error)`: Lista `sintomas_seleccionados` vacía -> retornar `422 Unprocessable Entity` (`SINTOMAS_REQUERIDOS`).
  - `FAILURE(not_found)`: `diagnostico_presuntivo_id` no existe en `patologias` -> retornar `404 Not Found` (`PATOLOGIA_NO_ENCONTRADA`).

**Observable states during this step**:
  - Customer/Actor (**Médico**) sees: Los **síntomas** elegidos aparecen como etiquetas (chips) en la ficha del **paciente**.
  - Operator sees: Validación de síntomas iniciada contra `patologia_id = 1`.
  - Database: Lectura de `patologias`, `patologias_sintomas` y `sintomas`.
  - Logs: `[paciente_service] step=2_resolucion_sintomas patologia_id=1 cantidad_seleccionados=2`

---

### STEP 3: Validación de síntomas contra la patología sospechada (Episodios 5 y 6)
**Actor**: Servicio (`clinica_service.py` / `paciente_service.py`)
**Action**:
  1. Cruza el conjunto de `sintoma.id` (o `snomed_id`) seleccionados para el **paciente** con las filas de `patologias_sintomas` de la `Patologia` (`patologia_id == diagnostico_presuntivo_id`):
     - `cardinales_coincidentes = [ps for ps in patologia.sintomas if ps.es_cardinal and ps.sintoma_id in ids_seleccionados]`
     - `secundarios_coincidentes = [ps for ps in patologia.sintomas if not ps.es_cardinal and ps.sintoma_id in ids_seleccionados]`
  2. Evalúa la regla de negocio del LEL:
     - `es_valido = (len(cardinales_coincidentes) >= 1) or (len(secundarios_coincidentes) >= 2)`
  3. Si `es_valido == False`: bloquea inmediatamente el alta del **paciente**.
**Timeout**: `1s`
**Input**: `{ patologia_id: 1, ids_seleccionados: set[int] }`
**Output on SUCCESS** (`es_valido == True`): `{ cardinales_encontrados: int, secundarios_encontrados: int, validacion_aprobada: True }` -> GO TO STEP 4
**Output on FAILURE** (`es_valido == False`):
  - `FAILURE(validation_error / regla_clinica)`: El conjunto de **síntomas** del **paciente** no contiene el **síntoma cardinal** ni al menos dos **síntomas secundarios** de la **patología** sospechada -> ejecutar `ABORT_CLEANUP` (`rollback` de cualquier `flush` previo) -> retornar `422 Unprocessable Entity` con código `SINTOMAS_NO_VALIDAN_PATOLOGIA`, detallando cuántos cardinales (`0`) y secundarios (`0` o `1`) coincidieron con la **patología**. El sistema NO permite dar de alta al **paciente**.

**Observable states during this step**:
  - Customer/Actor (**Médico**) sees:
    - Si `es_valido == True`: Indicador verde "Los síntomas validan el diagnóstico presuntivo (1 síntoma cardinal / >= 2 síntomas secundarios)".
    - Si `es_valido == False`: Alerta de bloqueo: "No se puede dar de alta al paciente: los síntomas seleccionados no coinciden con la patología sospechada. Debe incluir el síntoma cardinal o al menos dos síntomas secundarios de dicha patología.".
  - Operator sees: Resultado de validación clínica en logs.
  - Database: Si `es_valido == False`, 0 filas creadas en `pacientes` y `pacientes_sintomas`.
  - Logs: `[clinica_service] step=3_validacion_patologia patologia_id=1 cardinales=<c> secundarios=<s> valido=<bool>`

---

### STEP 4: Persistencia de los síntomas del paciente en `pacientes_sintomas`
**Actor**: Servicio (`paciente_service.py`) -> Repositorio (`paciente_repo.py`) -> PostgreSQL
**Action**: Habiendo superado la validación clínica en `STEP 3` y las demás validaciones obligatorias del alta de **paciente** (DNI, nombre, apellido, teléfono, mail, fecha de nacimiento, historia clínica, tipo de sospecha):
  1. Inserta el `Usuario` (`rol = Rol.PACIENTE`, `debe_cambiar_password = True`) y el `Paciente` en `pacientes`.
  2. Inserta en la tabla `pacientes_sintomas` una fila `(paciente_id = paciente.id, sintoma_id = s.id)` por cada **síntoma** seleccionado (deduplicando `sintoma_id`).
  3. Ejecuta `COMMIT`.
**Timeout**: `3s`
**Input**: `{ paciente_data: dict, sintomas_ids: list[int] }`
**Output on SUCCESS**: `{ paciente_id: int, sintomas_registrados: list[Sintoma] }` -> Retornar `201 Created` al **médico** (FIN DEL WORKFLOW).
**Output on FAILURE**:
  - `FAILURE(conflict)`: `dni` o `email` del **paciente** ya existen en la base de datos -> `ABORT_CLEANUP` (`rollback`) -> retornar `409 Conflict`.
  - `FAILURE(database_error)`: Error de base de datos al insertar en `pacientes_sintomas` -> `ABORT_CLEANUP` (`rollback`) -> retornar `500 Internal Server Error`.

**Observable states during this step**:
  - Customer/Actor (**Médico**) sees: Confirmación de alta del **paciente** con su lista de **síntomas** codificados en **SNOMED**.
  - Operator sees: Nuevo registro en `pacientes` y sus vínculos en `pacientes_sintomas`.
  - Database:
    - Tabla `sintomas`: términos **SNOMED** asegurados (`snomed_id`, `descripcion`).
    - Tabla `pacientes`: nueva fila con `diagnostico_presuntivo_id`.
    - Tabla `pacientes_sintomas`: `N` filas asociando `paciente_id` con cada `sintoma_id`.
  - Logs: `[paciente_repo] step=4_paciente_y_sintomas_guardados paciente_id=<id> patologia_id=1 sintomas_count=<N>`

---

### ABORT_CLEANUP: Rollback transaccional ante fallo de validación clínica o persistencia
**Triggered by**: Fallo de validación en `STEP 3` (`SINTOMAS_NO_VALIDAN_PATOLOGIA`) o error de base de datos en `STEP 4`.
**Actions** (in order):
  1. Ejecutar `db.session.rollback()` para garantizar que no se cree ninguna fila parcial en `usuarios`, `pacientes` ni `pacientes_sintomas`.
  2. Devolver al **médico** el detalle exacto de por qué los **síntomas** no validaron la **patología** seleccionada.
**What customer/actor (**Médico**) sees**: El formulario permanece abierto con los datos cargados y el mensaje explicativo para que corrija los **síntomas** o el diagnóstico presuntivo.
**What operator sees**: Log `INFO`/`WARN` de rechazo por regla de negocio clínica sin residuos en base de datos.

---

## State Transitions

```
Validación Clínica de Síntomas del Paciente:
  [Lista de síntomas en edición]
    -- (Incluye >= 1 Síntoma cardinal de la Patología) --> [Válido -> Permite crear Paciente y PacienteSintoma]
    -- (No incluye Síntoma cardinal, pero incluye >= 2 Síntomas secundarios de la Patología) --> [Válido -> Permite crear Paciente y PacienteSintoma]
    -- (0 Síntomas cardinales y < 2 Síntomas secundarios de la Patología) --> [Inválido -> Bloquea Dar de alta paciente (422 SINTOMAS_NO_VALIDAN_PATOLOGIA)]

Estudio (EstadoEstudio):
  Sin transición en este escenario (habilita que luego se pueda ejecutar Dar de alta estudio -> EstadoEstudio.CREADO).
```

---

## Handoff Contracts

### 1. Frontend (Médico) -> Backend: Buscar síntomas en SNOMED
**Endpoint**: `GET /api/snomed/sintomas?q=acr`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "query": "acr",
    "resultados": [
      {
        "snomed_id": "225566008",
        "descripcion": "Acroparestesia"
      },
      {
        "snomed_id": "24019002",
        "descripcion": "Acrocianosis"
      }
    ]
  }
}
```
**Failure response** (`422` / `502`):
```json
{
  "ok": false,
  "error": "Debe ingresar al menos 3 letras para buscar síntomas en SNOMED.",
  "code": "PREFIJO_DEMASIADO_CORTO",
  "retryable": false
}
```
**Timeout**: `3s`
**ON FAILURE**: Mostrar aviso bajo el campo de búsqueda; si es error `502`, reintentar automáticamente al siguiente ingreso de teclado (debounce `300ms`).

---

### 2. Frontend (Médico) -> Backend: Validar síntomas y dar de alta paciente
**Endpoint**: `POST /api/pacientes`
**Payload** *(sección relevante a síntomas y patología)*:
```json
{
  "dni": "48112233",
  "nombre": "Mateo",
  "apellido": "Ruiz",
  "telefono": "+5492215551122",
  "email": "padre.mateo@mail.com",
  "fecha_nacimiento": "2018-05-14",
  "diagnostico_presuntivo_id": 1,
  "historia_clinica": "Paciente de 8 años que consulta por acroparestesias...",
  "tipo_sospecha": "clinica",
  "sintomas": [
    { "snomed_id": "225566008", "descripcion": "Acroparestesia" }
  ]
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "paciente_id": 45,
    "dni": "48112233",
    "diagnostico_presuntivo": {
      "id": 1,
      "nombre": "Fabry"
    },
    "validacion_sintomas": {
      "aprobada": true,
      "cardinales_coincidentes": 1,
      "secundarios_coincidentes": 0
    },
    "sintomas": [
      {
        "id": 10,
        "snomed_id": "225566008",
        "descripcion": "Acroparestesia"
      }
    ]
  }
}
```
**Failure response – Validación contra patología fallida** (`422 Unprocessable Entity`):
```json
{
  "ok": false,
  "error": "Los síntomas seleccionados no validan la patología 'Fabry'. Se requiere el síntoma cardinal o al menos 2 síntomas secundarios asociados a la patología.",
  "code": "SINTOMAS_NO_VALIDAN_PATOLOGIA",
  "details": {
    "patologia_id": 1,
    "patologia_nombre": "Fabry",
    "cardinales_coincidentes": 0,
    "secundarios_coincidentes": 1
  },
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Bloquear el alta del **paciente** y destacar la sección de **síntomas** y diagnóstico presuntivo en la interfaz.

---

### 3. Backend (`snomed_client`) -> API Externa de SNOMED
**Endpoint**: `GET /external/snomed/concepts?q={prefijo}&limit=20`
**Success response** (`200 OK`):
```json
{
  "items": [
    { "conceptId": "225566008", "term": "Acroparestesia" },
    { "conceptId": "24019002", "term": "Acrocianosis" }
  ]
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "SNOMED search timeout",
  "code": "SNOMED_TIMEOUT",
  "retryable": true
}
```
**Timeout**: `2s`
**ON FAILURE**: Ejecutar fallback automático buscando en la tabla local `sintomas` (`sintomas.descripcion ILIKE '%<prefijo>%'`).

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Filas en `sintomas`, `usuarios`, `pacientes` y `pacientes_sintomas` (en sesión SQLAlchemy) | Step 2 / Step 4 | `ABORT_CLEANUP` | `db.session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/clinica.py`, existen los modelos exactos `Patologia` (`patologias`), `Sintoma` (`sintomas`: `id`, `snomed_id`, `descripcion`), `PatologiaSintoma` (`patologias_sintomas`: `patologia_id`, `sintoma_id`, `es_cardinal` con índice único parcial `uq_un_cardinal_por_patologia`) y `PacienteSintoma` (`pacientes_sintomas`: `paciente_id`, `sintoma_id`). | Low | Overview, STEP 2, STEP 3, STEP 4 | Alineación 100% con el esquema de base de datos existente. |
| RC-2 | En `.ai/1-Entrevista.md` (línea 374) se especifica que la búsqueda en **SNOMED** se dispara al escribir 3 letras ("empiezo a escribir tres letras, eso consulta la API"). | Low | STEP 1 | Se incorporó la validación `len(q.strip()) >= 3` en `GET /api/snomed/sintomas`. |
| RC-3 | En `.ai/1-Entrevista.md` (líneas 409-410) y `.ai/2-Glosario_LEL.md` se establece que la validación exige 1 **síntoma cardinal** o al menos 2 **síntomas secundarios** de la **patología**, sin permitir el alta del **paciente** si no se cumple. | High | STEP 3 | Formalizada como condición bloqueante transaccional en `STEP 3`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Búsqueda de síntomas en SNOMED con 3 o más letras | `GET /api/snomed/sintomas?q=cef` por un médico autenticado | Retorna `200 OK` con la lista de síntomas coincidentes (`snomed_id`, `descripcion`). |
| `TC-02`: Rechazo de búsqueda en SNOMED con menos de 3 letras | `GET /api/snomed/sintomas?q=ce` | Retorna `422 Unprocessable Entity` (`PREFIJO_DEMASIADO_CORTO`), sin consultar la API externa. |
| `TC-03`: Happy path – Alta de paciente válida con 1 síntoma cardinal | `POST /api/pacientes` con `diagnostico_presuntivo_id=1` y el síntoma cuyo `PatologiaSintoma.es_cardinal == True` | Retorna `201 Created`; crea el paciente y la fila en `pacientes_sintomas`. |
| `TC-04`: Happy path – Alta de paciente válida con 2 síntomas secundarios (sin cardinal) | `POST /api/pacientes` con `diagnostico_presuntivo_id=1` y 2 síntomas con `PatologiaSintoma.es_cardinal == False` para esa patología | Retorna `201 Created`; crea el paciente y las 2 filas en `pacientes_sintomas`. |
| `TC-05`: Bloqueo de alta cuando solo hay 1 síntoma secundario y ningún cardinal | `POST /api/pacientes` con `diagnostico_presuntivo_id=1` y solo 1 síntoma secundario de esa patología | Retorna `422 Unprocessable Entity` (`SINTOMAS_NO_VALIDAN_PATOLOGIA`); 0 filas creadas en `pacientes` y `usuarios`. |
| `TC-06`: Bloqueo de alta cuando los síntomas pertenecen a otra patología distinta de la sospechada | `POST /api/pacientes` con `diagnostico_presuntivo_id=1` (Fabry) pero enviando síntomas que solo están asociados a `patologia_id=2` (Pompe) | Retorna `422 Unprocessable Entity` (`SINTOMAS_NO_VALIDAN_PATOLOGIA`); 0 filas creadas en `pacientes`. |
| `TC-07`: Fallback a tabla local `sintomas` cuando la API externa de SNOMED sufre timeout | `GET /api/snomed/sintomas?q=acr` cuando `snomed_client` lanza `httpx.TimeoutException` | El servicio consulta `sintomas` en PostgreSQL y retorna `200 OK` con los términos locales coincidentes. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El **paciente** puede tener cargados síntomas adicionales en **SNOMED** además de los que validan la **patología**, siempre y cuando dentro de su lista seleccionada exista al menos 1 **síntoma cardinal** o 2 **síntomas secundarios** de la **patología** sospechada. | Verificado en `.ai/3-Escenarios.md#Escenario-36` ("debe haber un síntoma cardinal o al menos dos síntomas secundarios"). | Bajo. |
| A2 | Los síntomas asociados a cada una de las 5 **patologías** ya están registrados en `sintomas` y `patologias_sintomas` por el **gerente médico**. | Verificado en `.ai/2-Glosario_LEL.md` (`Sujeto: Gerente médico`). | Si una patología no tuviera síntomas configurados en `patologias_sintomas`, ninguna combinación validaría hasta que el gerente médico los defina. |

## Open Questions

- Cuando el tipo de sospecha del **paciente** es `"familiar"` (`Paciente.tipo_sospecha == "familiar"`, descrito en `.ai/1-Entrevista.md` líneas 111-113 para familiares asintomáticos con antecedente confirmado), ¿se mantiene la exigencia de síntomas o se exceptúa solo para sospecha familiar? *(En el Escenario 36 del LEL la regla de validación de síntomas se define como general para la carga de síntomas con SNOMED; conviene confirmar con el stakeholder si la sospecha familiar permite lista vacía).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada verificando `Patologia`, `Sintoma`, `PatologiaSintoma` y `PacienteSintoma` en `app/src/core/models/clinica.py`. | Aprobada. |
