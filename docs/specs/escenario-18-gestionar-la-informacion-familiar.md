# WORKFLOW: Escenario 18 – Gestionar la información familiar
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-18-Gestionar-la-informacion-familiar`

## Símbolos LEL utilizados

| Categoría | Símbolo LEL | Modelo / Tabla en `app/src/core/models/` |
|---|---|---|
| **Sujeto** | `Médico` | `Medico` en `medicos` / `Usuario` (`Rol.MEDICO`, `Rol.GERENTE_MEDICO`) |
| **Sujeto** | `Paciente` | `Paciente` en `pacientes` |
| **Objeto** | `Familiar` | `Familiar` en `familiares` (`parentesco`, `nombre`, `diagnostico_previo`) |
| **Objeto** | `Síntoma` | `Sintoma` en `sintomas` y `FamiliarSintoma` en `familiares_sintomas` |
| **Objeto** | `SNOMED` | `Sintoma.snomed_id` (`sintomas`) |
| **Objeto** | `Patología` | `Patologia` en `patologias` (referenciada en `diagnostico_previo` cuando existe) |
| **Objeto** | `Familiograma` | Archivo PDF referenciado en `Paciente.familiograma_pdf_path` |
| **Objeto** | `API de familiograma` | Cliente HTTP en `app/src/clients/` |
| **Verbo** | `Dar de alta paciente` | Flujo de alta/actualización clínica del `Paciente` |
| **Verbo** | `Cargar síntomas` | Selección de síntomas codificados en `SNOMED` para los familiares |
| **Estado** | *(N/A – Entidad Paciente)* | Aplica sobre `Paciente` (`pacientes`) durante la consulta médica |

---

## Overview

- **Objetivo**: Registrar la información de los `Familiar`es vinculada a un `Paciente` (nombre, relación de parentesco, `Síntoma`s codificados en `SNOMED` y diagnóstico previo si lo hubiera), enviarla a la `API de familiograma` y asociar el PDF del `Familiograma` (genograma) devuelto al `Paciente`.
- **Contexto**: Durante la consulta médica (al dar de alta al `Paciente` o al actualizar sus antecedentes familiares), el `Paciente` dispone de información familiar relevante para evaluar el patrón de herencia genética y detectar parientes a *screenear*. El `Médico` tratante carga cada `Familiar` con su parentesco, nombre, `Síntoma`s y diagnóstico previo; el sistema envía la estructura familiar a la `API de familiograma` y guarda el PDF resultante en `paciente.familiograma_pdf_path`. *(Si el paciente no posee o no desea brindar información familiar, aplica el Escenario 19, donde la lista queda vacía y `familiograma_pdf_path` es `None`).*
- **Recursos**: Datos de `Familiar`es (`familiares`), relación (`parentesco`), `Síntoma`s (`sintomas`, `familiares_sintomas`), diagnóstico previo (`diagnostico_previo`), `Familiograma` en PDF (`pacientes.familiograma_pdf_path`), `API de familiograma`.
- **Episodios**:
  1. El `Médico` tratante registra los `Familiar`es del `Paciente` (nombre y diagnóstico previo opcional).
  2. El `Médico` registra la relación de parentesco (`parentesco`) con cada `Familiar`.
  3. El `Médico` registra los `Síntoma`s (`SNOMED`) de cada `Familiar`.
  4. El sistema envía los familiares a la `API de familiograma` y asocia el PDF del `Familiograma` recibido al `Paciente` (`paciente.familiograma_pdf_path`).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Médico` | Registra la lista de `Familiar`es del `Paciente` con su parentesco, nombre, síntomas `SNOMED` y diagnóstico previo, y solicita la generación del `Familiograma`. |
| `Paciente` | Brinda verbalmente al `Médico` la información sobre sus parientes durante la consulta. |
| `API de familiograma` | Módulo externo que recibe la lista de `Familiar`es (parentescos, síntomas y diagnósticos previos) y devuelve el dibujo del `Familiograma` (genograma) en formato PDF. |
| Capa `router` (`Flask Blueprint`) | Expone `PUT /api/pacientes/{paciente_id}/familiares` (o la sección familiar dentro de `POST /api/pacientes`) y `GET /api/pacientes/{paciente_id}/familiograma/pdf`. |
| Capa `service` (`ClinicaService` / `PacienteService`) | Valida los datos de cada `Familiar` y sus `Síntoma`s `SNOMED`, persiste `Familiar` y `FamiliarSintoma`, invoca a la `API de familiograma` y asocia `familiograma_pdf_path` al `Paciente`. |
| Capa `repo` (`PacienteRepo`, `FamiliarRepo`, `SintomaRepo`) | Ejecuta las operaciones sobre `pacientes`, `familiares`, `familiares_sintomas` y `sintomas` en `PostgreSQL`. |
| Capa `clients` (`FamiliogramaClient`) | Realiza la petición HTTP (`httpx`) hacia la `API de familiograma` y recibe el PDF generado. |

---

## Prerequisites

- Existe un usuario autenticado con `Rol.MEDICO` o `Rol.GERENTE_MEDICO` con perfil `Medico` en la tabla `medicos`.
- Existe un `Paciente` en la tabla `pacientes` (o se está creando en la misma transacción de alta de paciente del Escenario 1).
- Los `Síntoma`s referenciados para los familiares existen en la tabla `sintomas` con su `snomed_id` válido.

---

## Trigger

El `Médico` tratante envía la nómina de familiares del paciente mediante `PUT /api/pacientes/{paciente_id}/familiares` (o al confirmar la carga de familiares durante el alta del `Paciente` en `POST /api/pacientes` con una lista `familiares` no vacía).

---

## Workflow Tree

### STEP 1: Validación de permisos, existencia del Paciente y estructura de los Familiares
**Actor**: `Médico` -> `router` -> `service` (`PacienteService.gestionar_informacion_familiar`) -> `repo` (`PacienteRepo`, `SintomaRepo`)
**Action**:
1. Verifica que el usuario autenticado tenga `Rol.MEDICO` o `Rol.GERENTE_MEDICO`.
2. Verifica que el `Paciente` exista en `pacientes` (`paciente_id`).
3. Verifica que la lista `familiares` contenga al menos 1 elemento (si la lista es vacía `[]`, redirige al comportamiento del **Escenario 19**: mantiene vacía la sección `familiares` y `familiograma_pdf_path = None`).
4. Para cada ítem de `familiares`:
   - Valida que `nombre` (`String(150)`) y `parentesco` (`String(60)`, ej. `"padre"`, `"madre"`, `"hermano"`, `"primo"`, `"abuelo_paterno"`) no estén vacíos y respeten las longitudes máximas del modelo `Familiar` (`app/src/core/models/clinica.py#L63-L70`).
   - Valida que `diagnostico_previo` (opcional, `String(255)`) no supere los 255 caracteres.
   - Valida que todos los `sintomas_snomed_ids` (o `sintomas_ids`) indicados para ese familiar correspondan a registros válidos en la tabla `sintomas`.
**Timeout**: 3s
**Input**:
```json
{
  "paciente_id": 15,
  "familiares": [
    {
      "nombre": "Carlos Gómez",
      "parentesco": "padre",
      "diagnostico_previo": "Fabry",
      "sintomas_snomed_ids": ["422587007", "25064002"]
    },
    {
      "nombre": "Lucía Gómez",
      "parentesco": "hermana",
      "diagnostico_previo": null,
      "sintomas_snomed_ids": ["422587007"]
    }
  ]
}
```
**Output on SUCCESS**: Datos de familiares y síntomas validados -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario autenticado no tiene `Rol.MEDICO` ni `Rol.GERENTE_MEDICO` -> retornar HTTP `403 Forbidden`.
  - `FAILURE(not_found)`: No existe `Paciente` con `id = paciente_id` -> retornar HTTP `404 Not Found`.
  - `FAILURE(validation_error)`: Falta `nombre` o `parentesco` en algún familiar, excede longitud de columna o algún `snomed_id` no existe en `sintomas` -> retornar HTTP `400 Bad Request` (`code: "DATOS_FAMILIARES_INVALIDOS"`).

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: Indicador `"Registrando familiares y generando familiograma..."`.
  - Operator sees: Sin cambios aún en base de datos.
  - Database: Lectura de `pacientes` y `sintomas`.
  - Logs: `[paciente_service] validando_familiares paciente_id=15 medico_id=4 cantidad_familiares=2`

---

### STEP 2: Persistencia de los Familiares, Parentescos y Síntomas en Base de Datos
**Actor**: `service` -> `repo` (`FamiliarRepo`) -> `PostgreSQL`
**Action**:
1. Si el `Paciente` tenía registros previos en `familiares` que están siendo actualizados por el `Médico`, los reemplaza limpiamente (`cascade="all, delete-orphan"` en `Paciente.familiares`, `perfiles.py#L80`).
2. Por cada familiar recibido, inserta una fila en la tabla `familiares` (`paciente_id`, `parentesco`, `nombre`, `diagnostico_previo`).
3. Por cada síntoma de cada familiar, inserta la fila asociativa en la tabla `familiares_sintomas` (`familiar_id`, `sintoma_id`).
**Timeout**: 4s
**Input**: `{ paciente_id: 15, familiares_validados }`
**Output on SUCCESS**: `{ familiares_ids: [81, 82] }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(database_error)`: Error de integridad o conexión al escribir en `familiares` / `familiares_sintomas` -> `ABORT_CLEANUP` (`session.rollback()`) y retornar HTTP `500 Internal Server Error`.

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: `"Generando PDF del familiograma..."`.
  - Operator sees: Familiares asociados al `Paciente #15`.
  - Database:
    - Tabla `familiares`: 2 filas insertadas con `paciente_id = 15`.
    - Tabla `familiares_sintomas`: 3 filas insertadas vinculando cada `familiar_id` con sus `sintoma_id`.
  - Logs: `[paciente_service] familiares_persistidos paciente_id=15 familiares_ids=[81, 82]`

---

### STEP 3: Envío de los Familiares a la API de familiograma y recepción del PDF
**Actor**: `service` -> `clients` (`FamiliogramaClient.generar_familiograma_pdf`)
**Action**:
1. Construye el payload con los datos del `Paciente` (caso índice / probando: nombre, fecha de nacimiento, diagnóstico presuntivo y síntomas) y la lista de `Familiar`es (con su `parentesco`, `nombre`, `diagnostico_previo` y lista de `sintomas` con código `SNOMED` y descripción).
2. Envía la petición HTTP `POST` a la `API de familiograma`.
3. Recibe el documento PDF con el dibujo del `Familiograma` (genograma) que representa gráficamente el árbol familiar y el patrón de herencia.
**Timeout**: 12s
**Input**: `{ paciente, familiares: [ { parentesco, nombre, diagnostico_previo, sintomas } ] }`
**Output on SUCCESS**: `{ pdf_bytes: b"%PDF-1.4..." }` -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(external_api_timeout_or_5xx)`: La `API de familiograma` supera 12s o devuelve HTTP 5xx -> reintentar hasta 2 veces con backoff de 1s y 2s.
  - `FAILURE(external_api_unavailable_after_retries)`: Si tras los reintentos la `API de familiograma` sigue caída, **se conservan** los registros de `Familiar` y `FamiliarSintoma` en la base de datos (para que el `Médico` no pierda los datos cargados durante la consulta con el paciente), se deja `paciente.familiograma_pdf_path = None` y se devuelve HTTP `200 OK` con `familiograma_generado: false, warning: "FAMILIOGRAMA_API_PENDIENTE"` habilitando regeneración posterior (`POST /api/pacientes/{paciente_id}/familiograma/regenerar`).

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: Espera de respuesta del generador de familiograma.
  - Operator sees: Petición saliente hacia `API de familiograma`.
  - Database: Registros en `familiares` y `familiares_sintomas` listos; `familiograma_pdf_path` pendiente de actualización en STEP 4.
  - Logs: `[familiograma_client] solicitando_familiograma paciente_id=15 cantidad_familiares=2`

---

### STEP 4: Almacenamiento del PDF del Familiograma y asociación al Paciente
**Actor**: `service` -> File Storage -> `repo` (`PacienteRepo`) -> `PostgreSQL`
**Action**:
1. Guarda el PDF devuelto por la `API de familiograma` en almacenamiento persistente (`storage/familiogramas/familiograma_paciente_{paciente_id}.pdf`).
2. Actualiza la columna `paciente.familiograma_pdf_path = "storage/familiogramas/familiograma_paciente_{paciente_id}.pdf"` en la tabla `pacientes`.
3. Confirma (`commit`) la transacción en `PostgreSQL`.
**Timeout**: 4s
**Input**: `{ paciente_id: 15, pdf_bytes }`
**Output on SUCCESS**: `{ paciente_id: 15, familiograma_pdf_path: "storage/familiogramas/familiograma_paciente_15.pdf" }` -> FIN DEL WORKFLOW.
**Output on FAILURE**:
  - `FAILURE(io_or_database_error)`: Error al guardar el archivo PDF en disco o al actualizar `pacientes.familiograma_pdf_path` -> ejecutar `ABORT_CLEANUP` y retornar HTTP `500 Internal Server Error`.

**Observable states during this step**:
  - Customer/Actor (`Médico` y `Paciente`) sees: Familiares registrados y vista previa / enlace de descarga del PDF del `Familiograma` asociado a la ficha del `Paciente`.
  - Operator sees: `paciente.familiograma_pdf_path` poblado y archivo PDF disponible.
  - Database:
    - Tabla `pacientes`: `familiograma_pdf_path = 'storage/familiogramas/familiograma_paciente_15.pdf'` para `id = 15`.
    - Tablas `familiares` y `familiares_sintomas`: persistidas y confirmadas.
  - Logs: `[paciente_service] familiograma_asociado paciente_id=15 pdf_path="storage/familiogramas/familiograma_paciente_15.pdf"`

---

### ABORT_CLEANUP: Reversión transaccional y limpieza de archivos
**Triggered by**: Fallo de base de datos o de escritura en disco en STEP 2 o STEP 4.
**Actions** (in order):
  1. Ejecutar `session.rollback()` en SQLAlchemy para revertir cambios incompletos en `familiares`, `familiares_sintomas` y `pacientes`.
  2. Si se llegó a escribir un archivo truncado en `storage/familiogramas/familiograma_paciente_{id}.pdf` sin commitear en base de datos, eliminarlo con `os.remove()`.
**What customer sees**: Mensaje de error en el formulario del `Médico` conservando los datos en pantalla para reintentar.
**What operator sees**: Registro de error en los logs de aplicación.

---

## State Transitions

```
Paciente (pacientes.familiograma_pdf_path y relación familiares):
[familiares = [], familiograma_pdf_path = NULL]
  -- (STEP 1-2: Médico carga familiares, parentescos y síntomas SNOMED) --> [familiares = [F1..Fn], familiograma_pdf_path = NULL]
  -- (STEP 3-4: API de familiograma devuelve PDF y se asocia al paciente) -> [familiares = [F1..Fn], familiograma_pdf_path = "storage/familiogramas/..."]
```

---

## Handoff Contracts

### 1. `Médico (UI)` -> `Backend (router -> service)` (Registrar familiares y generar Familiograma)
**Endpoint**: `PUT /api/pacientes/{paciente_id}/familiares`
**Payload**:
```json
{
  "familiares": [
    {
      "nombre": "Carlos Gómez",
      "parentesco": "padre",
      "diagnostico_previo": "Fabry",
      "sintomas_snomed_ids": ["422587007", "25064002"]
    },
    {
      "nombre": "Lucía Gómez",
      "parentesco": "hermana",
      "diagnostico_previo": null,
      "sintomas_snomed_ids": ["422587007"]
    }
  ]
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "paciente_id": 15,
  "familiares": [
    {
      "id": 81,
      "nombre": "Carlos Gómez",
      "parentesco": "padre",
      "diagnostico_previo": "Fabry",
      "sintomas": [
        { "id": 4, "snomed_id": "422587007", "descripcion": "Acroparestesia" },
        { "id": 9, "snomed_id": "25064002", "descripcion": "Cefalea" }
      ]
    },
    {
      "id": 82,
      "nombre": "Lucía Gómez",
      "parentesco": "hermana",
      "diagnostico_previo": null,
      "sintomas": [
        { "id": 4, "snomed_id": "422587007", "descripcion": "Acroparestesia" }
      ]
    }
  ],
  "familiograma_generado": true,
  "familiograma_pdf_path": "storage/familiogramas/familiograma_paciente_15.pdf",
  "familiograma_pdf_url": "/api/pacientes/15/familiograma/pdf"
}
```
**Failure response** (`400` / `403` / `404`):
```json
{
  "ok": false,
  "error": "El código SNOMED '999999999' no existe en el catálogo de síntomas.",
  "code": "SINTOMA_SNOMED_INEXISTENTE",
  "retryable": false
}
```
**Timeout**: 15s
**ON FAILURE**: Rollback transaccional si falla validación o base de datos; degradación elegante conservando familiares en BD si solo falla la `API de familiograma` externa.

---

### 2. `Backend (service)` -> `API de familiograma (clients)`
**Endpoint**: `POST {FAMILIOGRAMA_API_URL}/familiogramas`
**Payload**:
```json
{
  "paciente": {
    "paciente_id": 15,
    "nombre_completo": "Juan Gómez",
    "fecha_nacimiento": "1998-05-14",
    "diagnostico_presuntivo": "Fabry",
    "sintomas": [
      { "snomed_id": "422587007", "descripcion": "Acroparestesia" }
    ]
  },
  "familiares": [
    {
      "nombre": "Carlos Gómez",
      "parentesco": "padre",
      "diagnostico_previo": "Fabry",
      "sintomas": [
        { "snomed_id": "422587007", "descripcion": "Acroparestesia" },
        { "snomed_id": "25064002", "descripcion": "Cefalea" }
      ]
    },
    {
      "nombre": "Lucía Gómez",
      "parentesco": "hermana",
      "diagnostico_previo": null,
      "sintomas": [
        { "snomed_id": "422587007", "descripcion": "Acroparestesia" }
      ]
    }
  ]
}
```
**Success response** (`200 OK`, `application/pdf` o JSON con `pdf_base64`):
```json
{
  "ok": true,
  "pdf_base64": "JVBERi0xLjQK..."
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Error al renderizar el árbol genealógico.",
  "code": "FAMILIOGRAMA_RENDER_ERROR",
  "retryable": true
}
```
**Timeout**: 12s
**ON FAILURE**: Reintentar 2 veces con backoff (1s, 2s); si falla, conservar los registros de `Familiar` en la base de datos y marcar `familiograma_pdf_path = None` con opción de regeneración.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Filas en `familiares` y `familiares_sintomas` | Step 2 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |
| Archivo `storage/familiogramas/familiograma_paciente_{id}.pdf` y columna `pacientes.familiograma_pdf_path` | Step 4 | `ABORT_CLEANUP` | `os.remove()` + `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/clinica.py` (líneas 63-81), `Familiar` posee exactamente `id`, `paciente_id`, `parentesco: String(60)`, `nombre: String(150)`, `diagnostico_previo: Optional[String(255)]` y la relación `sintomas: Mapped[list[Sintoma]] = relationship(secondary="familiares_sintomas")` mediante la tabla `FamiliarSintoma`. | Low | STEP 1 & STEP 2 | Alineado 100% con `clinica.py`. |
| RC-2 | En `app/src/core/models/perfiles.py` (líneas 71 y 80), `Paciente` posee `familiograma_pdf_path: Mapped[Optional[str]] = mapped_column(String(500))` y `familiares: Mapped[list["Familiar"]] = relationship(back_populates="paciente", cascade="all, delete-orphan")`. | Low | STEP 2 & STEP 4 | Alineado 100% con `perfiles.py`. |
| RC-3 | Si la `API de familiograma` externa sufre una caída temporal durante la consulta médica, abortar toda la transacción obligaría al `Médico` a volver a interrogar y tipear todos los familiares y síntomas del paciente. | Medium | STEP 3 | Se especificó que tras agotar los reintentos contra la `API de familiograma`, los registros en `familiares` y `familiares_sintomas` se preservan en `PostgreSQL` y se permite regenerar el PDF posteriormente. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Registro exitoso de familiares con parentesco, síntomas `SNOMED`, diagnóstico previo y asociación de `Familiograma` PDF | `PUT /api/pacientes/15/familiares` con 2 familiares válidos por un `Médico` | HTTP `200 OK`; se insertan 2 filas en `familiares`, sus vínculos en `familiares_sintomas`, se invoca a la `API de familiograma`, se guarda el PDF en disco y `paciente.familiograma_pdf_path` queda poblado. |
| `TC-02`: Registro de familiar sin diagnóstico previo (`diagnostico_previo = null`) ni síntomas (`sintomas_snomed_ids = []`) | `PUT /api/pacientes/15/familiares` con un familiar sano (`diagnostico_previo=None`, `sintomas_snomed_ids=[]`) | HTTP `200 OK`; se crea la fila en `familiares` con `diagnostico_previo IS NULL`, 0 filas en `familiares_sintomas` para ese familiar, y se genera el `Familiograma`. |
| `TC-03`: Rechazo por síntoma `SNOMED` inexistente | `PUT /api/pacientes/15/familiares` incluyendo un `snomed_id` que no existe en `sintomas` | HTTP `400 Bad Request` (`SINTOMA_SNOMED_INEXISTENTE`); no se crean registros huérfanos en `familiares`. |
| `TC-04`: Rechazo por falta de `parentesco` o `nombre` | `PUT /api/pacientes/15/familiares` con `parentesco=""` | HTTP `400 Bad Request` (`DATOS_FAMILIARES_INVALIDOS`). |
| `TC-05`: Rechazo por rol no autorizado | `PUT /api/pacientes/15/familiares` invocado por un `Administrativo` o `Transportista` | HTTP `403 Forbidden`. |
| `TC-06`: Resiliencia ante caída de la `API de familiograma` | La `API de familiograma` devuelve `503 Service Unavailable` en todos los reintentos | Los registros en `familiares` y `familiares_sintomas` quedan guardados en la base de datos, `paciente.familiograma_pdf_path` queda en `None` y la respuesta informa `familiograma_generado: false, warning: "FAMILIOGRAMA_API_PENDIENTE"`. |
| `TC-07`: Actualización de familiares reemplaza sin dejar huérfanos | Se invoca `PUT /api/pacientes/15/familiares` por segunda vez modificando la lista de familiares | Gracias a `cascade="all, delete-orphan"`, los familiares anteriores son reemplazados por la nueva lista y se actualiza el PDF del `Familiograma`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Los síntomas de los familiares no están sujetos a la restricción de "1 síntoma cardinal o 2 secundarios de la patología" (regla que aplica exclusivamente para validar los síntomas del propio `Paciente` contra su diagnóstico presuntivo en el Escenario 1 y 36), ya que un familiar en el árbol genealógico puede ser asintomático o presentar solo un signo aislado. | `.ai/1-Entrevista.md` (líneas 99-102 y 409-414) y `.ai/2-Glosario_LEL.md` (`Familiar`, `Síntoma cardinal`, `Síntoma secundario`) | Low |

## Open Questions

- Ninguna pregunta abierta bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/clinica.py`, `perfiles.py` y `enums.py`. | Estado marcado como `Approved`. |
