# WORKFLOW: Escenario 21 – Registrar un médico
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-21`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Médico` (sinónimos: médico tratante, médico derivante) |
| **Objetos** | `Especialidad` |
| **Verbos** | *(Autoregistro / Alta de `Médico`; habilita posteriormente `Iniciar sesión`, `Dar de alta paciente`, `Dar de alta estudio`)* |
| **Estados** | *(No aplica estado de `Estudio`; crea `Usuario` con `Rol.MEDICO`, `debe_cambiar_password = False`, `Medico` y vínculos en `MedicoEspecialidad`)* |

---

## Overview

- **Objetivo**: Permitir que un **médico** se registre por sí mismo como usuario profesional del sistema.
- **Contexto**: El profesional necesita utilizar el sistema para derivar **pacientes** y solicitar **estudios** de exoma clínico. Conforme al LEL, el sistema asume que la matrícula ingresada por el **médico** es válida sin consultar una API externa de colegio médico.
- **Recursos**: Matrícula (`matricula`), **especialidades** (`especialidades_ids`), `nombre`, `apellido`, `telefono`, correo electrónico (`email`), contraseña (`password`).
- **Episodios**:
  1. El **médico** ingresa sus datos personales (`nombre`, `apellido`, `telefono`, `email`, `password`).
  2. El **médico** registra su `matricula`.
  3. El **médico** selecciona sus **especialidades** de la lista estandarizada precargada en el sistema (`especialidades`).
  4. El sistema registra al **médico** creando de forma atómica su cuenta en `usuarios` (`Rol.MEDICO`), su perfil en `medicos` y sus asociaciones en `medicos_especialidades`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Médico` (Sujeto LEL) | Profesional externo que se autoda de alta en el sistema completando el formulario público de registro de médicos. |
| `medicos_router` (`app/src/routers/`) | Capa `router`: expone el catálogo de **especialidades** y el endpoint público de autoregistro de **médico**, validando tipos y campos obligatorios. |
| `medico_service` (`app/src/services/`) | Capa `service`: valida formato de datos, existencia de todas las **especialidades** elegidas, unicidad de `email` y `matricula`, hashea la contraseña y coordina la creación del perfil profesional. |
| `medico_repo` / `usuario_repo` (`app/src/repos/`) | Capa `repo`: consulta `especialidades`, `usuarios` y `medicos`, e inserta en una sola transacción `Usuario`, `Medico` y `MedicoEspecialidad`. |
| `PostgreSQL` | Persiste las filas en `usuarios`, `medicos` y `medicos_especialidades` aplicando restricciones `UNIQUE(email)` y `UNIQUE(matricula)`. |

---

## Prerequisites

- La tabla `especialidades` en `PostgreSQL` cuenta con el catálogo estandarizado de **especialidades** médicas precargado (al menos 1 especialidad activa para seleccionar).
- El profesional aún no posee una cuenta en `usuarios` con ese `email` ni un perfil en `medicos` con esa `matricula`.

---

## Trigger

El **médico** accede a la pantalla pública de registro profesional, consulta la lista de **especialidades** (`GET /api/v1/especialidades`) y envía el formulario de alta.
- **Endpoint HTTP**: `POST /api/v1/medicos/registro`

---

## Workflow Tree

### STEP 1: Validación de campos obligatorios del médico y formato de credenciales
**Actor**: `medicos_router` -> `medico_service`
**Action**:
1. Verifica que todos los campos requeridos estén presentes y no vacíos: `nombre`, `apellido`, `telefono`, `email`, `password`, `matricula` y `especialidades_ids`.
2. Valida formato de `email`, longitud y fortaleza de `password` (>= 8 caracteres), longitud de `matricula` (`1..50` caracteres) y que `especialidades_ids` sea una lista no vacía de enteros únicos (`len >= 1`).
3. Nota de dominio LEL: El sistema **asume que la matrícula del médico es válida** (no realiza llamada externa al Ministerio/Colegio Médico).
**Timeout**: `2s`
**Input**: `{ nombre: str, apellido: str, telefono: str, email: str, password: str, matricula: str, especialidades_ids: list[int] }`
**Output on SUCCESS**: Payload normalizado (`email` en minúsculas, `matricula` sin espacios extremos, `especialidades_ids` deduplicados) -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(validation_error)`: Algún campo obligatorio está vacío, `email` inválido, `password` débil o `especialidades_ids` está vacía (`[]`) -> retorna `400 Bad Request` (`code: "DATOS_MEDICO_INVALIDOS"`), sin efectos en base de datos.
  - `FAILURE(timeout)`: Supera `2s` -> retorna `504 Gateway Timeout` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: Indicador "Validando datos de registro profesional...".
  - Operator sees: Petición `POST /api/v1/medicos/registro` recibida.
  - Database: Sin escrituras.
  - Logs: `[medico_service] step_1_validar_registro_medico email=<email> matricula=<matricula> especialidades_count=<n>`

---

### STEP 2: Verificación de unicidad de `email` y `matricula` y existencia de `Especialidad`
**Actor**: `medico_service` -> `medico_repo` / `usuario_repo` -> `PostgreSQL`
**Action**:
1. Consulta `usuarios` por `email` para verificar que no esté registrado.
2. Consulta `medicos` por `matricula` para verificar que no esté registrada.
3. Consulta `especialidades` filtrando por `id IN especialidades_ids` y comprueba que la cantidad de filas encontradas coincida exactamente con `len(especialidades_ids)`.
**Timeout**: `3s`
**Input**: `{ email: str, matricula: str, especialidades_ids: list[int] }`
**Output on SUCCESS**: `email` libre, `matricula` libre y todas las `Especialidad` existen -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(conflict_email)`: Ya existe un `Usuario` con ese `email` -> retorna `409 Conflict` (`code: "EMAIL_YA_REGISTRADO"`).
  - `FAILURE(conflict_matricula)`: Ya existe un `Medico` con esa `matricula` -> retorna `409 Conflict` (`code: "MATRICULA_YA_REGISTRADA"`).
  - `FAILURE(validation_error)`: Uno o más IDs en `especialidades_ids` no existen en la tabla `especialidades` -> retorna `422 Unprocessable Entity` (`code: "ESPECIALIDAD_INEXISTENTE"`).
  - `FAILURE(timeout)`: Consulta SQL > `3s` -> reintenta 1 vez (`500ms`); si falla, retorna `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: Spinner de carga en el formulario de registro.
  - Operator sees: Consultas de verificación en `usuarios`, `medicos` y `especialidades`.
  - Database: Solo lecturas (`SELECT`).
  - Logs: `[medico_repo] step_2_verificar_unicidad_y_especialidades email=<email> matricula=<matricula>`

---

### STEP 3: Persistencia transaccional de `Usuario`, `Medico` y `MedicoEspecialidad`
**Actor**: `medico_service` -> `medico_repo` -> `PostgreSQL`
**Action**:
1. Calcula `password_hash` a partir de `password`.
2. En una única transacción de base de datos:
   - Inserta en `usuarios` una fila con `email`, `password_hash`, `rol = Rol.MEDICO`, `nombre`, `apellido`, `telefono`, `debe_cambiar_password = False`.
   - Inserta en `medicos` una fila con `usuario_id = usuario.id` y `matricula`.
   - Inserta en `medicos_especialidades` una fila `(medico_id = medico.id, especialidad_id = esp_id)` por cada especialidad seleccionada.
   - Si se envió `dispositivo_identificador`, registra opcionalmente la fila en `dispositivos_conocidos` para que el primer ingreso desde esa misma máquina sea reconocido como máquina conocida.
3. Ejecuta `COMMIT` de la transacción.
**Timeout**: `4s`
**Input**: Datos validados de `Usuario`, `Medico` y `especialidades_ids`.
**Output on SUCCESS**: `{ medico_id: int, usuario_id: int, matricula: str, especialidades: list[dict] }` -> Retorna `201 Created`.
**Output on FAILURE**:
  - `FAILURE(conflict)`: Condición de carrera concurrente que dispara `IntegrityError` en `usuarios.email` o `medicos.matricula` -> `ABORT_CLEANUP` (`ROLLBACK`) -> retorna `409 Conflict` (`code: "REGISTRO_MEDICO_DUPLICADO"`).
  - `FAILURE(database_error)` / `FAILURE(timeout)`: Error de conexión o timeout > `4s` -> `ABORT_CLEANUP` (`ROLLBACK`) -> retorna `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: Confirmación "Registro exitoso. Ya puede iniciar sesión con su correo y contraseña."
  - Operator sees: Nuevo médico activo en el sistema.
  - Database:
    - `usuarios`: 1 nueva fila con `rol = 'MEDICO'`, `debe_cambiar_password = false`.
    - `medicos`: 1 nueva fila con `usuario_id` y `matricula`.
    - `medicos_especialidades`: N nuevas filas vinculando `medico_id` con `especialidades.id`.
  - Logs: `[medico_repo] step_3_medico_registrado_ok medico_id=<id> usuario_id=<id> matricula=<matricula>`

---

### ABORT_CLEANUP: Reversión de registro parcial de médico
**Triggered by**: Cualquier `IntegrityError`, fallo de base de datos o timeout durante `STEP 3`.
**Actions** (in order):
  1. Ejecutar `ROLLBACK` de la transacción SQL para que no quede ningún `Usuario` sin fila en `medicos` ni ningún `Medico` sin filas en `medicos_especialidades`.
  2. Registrar el motivo del fallo en logs.
**What customer (`Médico`) sees**: Mensaje de error claro indicando si hubo duplicidad concurrente (`409`) o error temporal del servidor (`503`).
**What operator sees**: Base de datos consistente sin usuarios huérfanos.

---

## State Transitions

```
[No registrado] -> (STEP 1-3 exitosos) -> [Médico registrado (usuarios.rol = Rol.MEDICO, medicos.matricula activa, medicos_especialidades > 0)]
[No registrado] -> (Fallo en STEP 1 o STEP 2) -> [No registrado (sin efectos en BD)]
[En transacción STEP 3] -> (Fallo o conflicto concurrente -> ABORT_CLEANUP) -> [No registrado (rollback completo)]
```

---

## Handoff Contracts

### 1. Frontend (`Médico`) -> Backend (`medicos_router`) – Consulta de especialidades
**Endpoint**: `GET /api/v1/especialidades`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": [
    { "id": 1, "nombre": "Genética Médica" },
    { "id": 2, "nombre": "Neurología" },
    { "id": 3, "nombre": "Pediatría" },
    { "id": 4, "nombre": "Clínica Médica" },
    { "id": 5, "nombre": "Cardiología" }
  ]
}
```
**Timeout**: `3s`

### 2. Frontend (`Médico`) -> Backend (`medicos_router`) – Alta de médico
**Endpoint**: `POST /api/v1/medicos/registro`
**Payload**:
```json
{
  "nombre": "Martín",
  "apellido": "Gómez",
  "telefono": "+5492214448899",
  "email": "martin.gomez@hospital.org.ar",
  "password": "DrGomez2026!Secure",
  "matricula": "MP-114523",
  "especialidades_ids": [1, 3],
  "dispositivo_identificador": "fp_sha256_medico_workstation_01"
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "medico_id": 15,
    "usuario_id": 64,
    "nombre": "Martín",
    "apellido": "Gómez",
    "telefono": "+5492214448899",
    "email": "martin.gomez@hospital.org.ar",
    "rol": "medico",
    "matricula": "MP-114523",
    "especialidades": [
      { "id": 1, "nombre": "Genética Médica" },
      { "id": 3, "nombre": "Pediatría" }
    ]
  }
}
```
**Failure response** (`400` / `409` / `422` / `503`):
```json
{
  "ok": false,
  "error": "La matrícula ingresada ya pertenece a un médico registrado.",
  "code": "MATRICULA_YA_REGISTRADA",
  "retryable": false
}
```
**Timeout**: `6s`
**ON FAILURE**: Si es `400/409/422`, resaltar el campo conflictivo en el formulario; si es `503`, permitir reintento sin perder los datos cargados.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Fila en `usuarios` (`Rol.MEDICO`) | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` transaccional |
| Fila en `medicos` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` transaccional |
| Filas en `medicos_especialidades` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` transaccional |
| Fila opcional en `dispositivos_conocidos` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` transaccional |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/perfiles.py` (líneas 20-46), los modelos `Especialidad`, `MedicoEspecialidad` y `Medico` existen con `matricula` única (`String(50), unique=True`) y relación many-to-many mediante `medicos_especialidades`. | Low | Overview / STEP 3 | Alineado 100% con el modelo de base de datos. |
| RC-2 | En `.ai/2-Glosario_LEL.md` (`Sujeto: Médico` y `Sujeto: Gerente médico`), el **médico** se autoda de alta (`Rol.MEDICO`), mientras que el **gerente médico** es dado de alta por el **admin general** con los mismos datos que un **médico**. | Low | STEP 1 / STEP 3 | El endpoint público `/api/v1/medicos/registro` asigna exclusivamente `Rol.MEDICO`, impidiendo escalación de privilegios a `Rol.GERENTE_MEDICO`. |
| RC-3 | No existen aún un seed de `especialidades` ni los archivos `medicos_router.py`, `medico_service.py` y `medico_repo.py`. | Medium | Prerequisites / Actors | Documentado como prerequisito de seed/migración e implementación de capas. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Registro válido de médico con múltiples especialidades | `POST /api/v1/medicos/registro` con datos válidos y `especialidades_ids: [1, 3]` | Retorna `201 Created`; crea `Usuario` (`rol=Rol.MEDICO`, `debe_cambiar_password=False`), `Medico` y 2 filas en `medicos_especialidades`. |
| `TC-02`: Registro sin especialidades seleccionadas | `POST /api/v1/medicos/registro` con `especialidades_ids: []` | Retorna `400 Bad Request` (`code: "DATOS_MEDICO_INVALIDOS"`); no crea `Usuario` ni `Medico`. |
| `TC-03`: Especialidad inexistente en catálogo | `POST /api/v1/medicos/registro` con `especialidades_ids: [9999]` | Retorna `422 Unprocessable Entity` (`code: "ESPECIALIDAD_INEXISTENTE"`); no crea registros. |
| `TC-04`: Matrícula duplicada | `POST /api/v1/medicos/registro` con una `matricula` ya existente en `medicos` | Retorna `409 Conflict` (`code: "MATRICULA_YA_REGISTRADA"`). |
| `TC-05`: Correo electrónico duplicado | `POST /api/v1/medicos/registro` con un `email` ya existente en `usuarios` | Retorna `409 Conflict` (`code: "EMAIL_YA_REGISTRADO"`). |
| `TC-06`: Intento de inyectar rol `gerente_medico` en el payload | `POST /api/v1/medicos/registro` enviando `"rol": "gerente_medico"` | El campo extra es ignorado/rechazado y el usuario se crea estrictamente con `Rol.MEDICO`. |
| `TC-07`: Fallo transaccional al insertar en `medicos_especialidades` | Error forzado en mitad de `STEP 3` | `ABORT_CLEANUP` hace `ROLLBACK`; no queda fila huérfana en `usuarios` ni en `medicos`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El **médico** define su propia contraseña en el formulario de autoregistro, por lo que `Usuario.debe_cambiar_password` se inicializa en `False` (a diferencia del **paciente**, cuyo alta la realiza el **médico**). | `app/src/core/models/usuarios.py` (líneas 29-30) y `.ai/2-Glosario_LEL.md` | Bajo. |
| A2 | La tabla `especialidades` se alimenta mediante datos semilla (seed) con una lista estandarizada amplia antes de habilitar el registro de médicos. | `.ai/1-Entrevista.md` (líneas 197-199) y `.ai/2-Glosario_LEL.md` (`Objeto: Especialidad`) | Medio: si la tabla está vacía, ningún médico podrá completar el paso 3 del escenario. |

## Open Questions

- Ninguna. El LEL y la entrevista definen explícitamente que la matrícula se asume válida y que todos los campos (matrícula, especialidades, nombre, apellido, teléfono y mail) son obligatorios.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/perfiles.py` (`Medico`, `Especialidad`, `MedicoEspecialidad`) y `usuarios.py` (`Usuario`). | Aprobada para implementación. |
