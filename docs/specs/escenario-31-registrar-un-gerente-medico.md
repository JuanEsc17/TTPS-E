# WORKFLOW: Escenario 31 – Registrar un gerente médico
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-31`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Admin general** | `Usuario` (`rol = Rol.ADMIN_GENERAL`) |
| **Sujetos** | **Gerente médico** | `Usuario` (`rol = Rol.GERENTE_MEDICO`) + perfil `Medico` (`medicos`: `id`, `usuario_id`, `matricula`) |
| **Sujetos** | **Médico** | Noción base de **Gerente médico** ("Médico con facultades adicionales; el admin general lo da de alta con los mismos datos que un médico") |
| **Objetos** | **Especialidad** | Modelo `Especialidad` (tabla `especialidades`) y tabla asociativa `MedicoEspecialidad` (`medicos_especialidades`) |
| **Verbos** | **Iniciar sesión** | El **gerente médico** registrado podrá iniciar sesión con las credenciales dadas de alta |
| **Estados** | *(No altera `EstadoEstudio`)* | Alta administrativa de usuario y perfil profesional |

---

## Overview

- **Objetivo:** Dar de alta a un **gerente médico** como usuario del sistema con los mismos datos profesionales que un **médico** y con facultades adicionales (`Rol.GERENTE_MEDICO`) para administrar **patologías** y **cupones**.
- **Contexto:** El laboratorio necesita incorporar un **gerente médico** que gestione el catálogo de **patologías** (con su **síntoma cardinal** y **síntomas secundarios**) y la creación/asignación de **cupones**.
- **Recursos:** Matrícula (`Medico.matricula`), **especialidades** (`especialidades`), nombre (`Usuario.nombre`), apellido (`Usuario.apellido`), teléfono (`Usuario.telefono`), correo electrónico (`Usuario.email`), contraseña (`Usuario.password_hash`).
- **Episodios:**
  1. El **admin general** ingresa los datos personales del **gerente médico** (nombre, apellido, teléfono, correo electrónico y contraseña).
  2. El **admin general** registra su matrícula profesional.
  3. El **admin general** selecciona sus **especialidades** de la lista estandarizada.
  4. El sistema registra al **gerente médico** creando su usuario con `Rol.GERENTE_MEDICO`, su perfil en `medicos` y sus vínculos en `medicos_especialidades`.

**Resumen del flujo:** El **admin general** autenticado envía una petición `POST /api/admin/gerentes-medicos` con los datos personales, la matrícula y la lista de identificadores de **especialidades**. El servicio valida que el solicitante tenga `Rol.ADMIN_GENERAL`, que el correo electrónico no esté registrado en `usuarios`, que la matrícula no esté registrada en `medicos` (asumiendo que la matrícula ingresada es válida según el LEL) y que todas las **especialidades** seleccionadas existan en la tabla `especialidades`. A continuación, hashea la contraseña y ejecuta una transacción atómica en PostgreSQL insertando en `usuarios` (`rol = Rol.GERENTE_MEDICO`, `debe_cambiar_password = False`), en `medicos` (`usuario_id`, `matricula`) y en `medicos_especialidades`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Admin general** (Sujeto LEL) | Carga los datos personales, matrícula y **especialidades** para dar de alta al **gerente médico**. |
| **Router HTTP** (`app/src/routers/admin_usuarios.py`) | Verifica sesión activa y rol exclusivo `Rol.ADMIN_GENERAL`, valida el esquema de entrada y formatea la respuesta HTTP. |
| **Servicio de Usuarios / Perfiles** (`app/src/services/usuario_service.py`) | Verifica unicidad de email y matrícula, existencia de **especialidades**, calcula el `password_hash` seguro y coordina el alta transaccional. |
| **Repositorio de Usuarios y Perfiles** (`app/src/repos/usuario_repo.py`) | Consulta `usuarios`, `medicos` y `especialidades`, e inserta atómicamente en `usuarios`, `medicos` y `medicos_especialidades`. |
| **PostgreSQL** (`db`) | Aplica las restricciones `UNIQUE(usuarios.email)`, `UNIQUE(medicos.usuario_id)`, `UNIQUE(medicos.matricula)` y claves foráneas de `medicos_especialidades`. |

---

## Prerequisites

- **Sesión y Rol:** El usuario que ejecuta la acción debe tener sesión activa con `Usuario.rol == Rol.ADMIN_GENERAL`.
- **Datos existentes en `app/src/core/models/`:**
  - La tabla `especialidades` debe contar con el catálogo estandarizado de **especialidades** médicas precargado (al menos las seleccionadas en el payload).
  - No debe existir ninguna fila en `usuarios` con el mismo `email` ni ninguna fila en `medicos` con la misma `matricula`.
- **Estado previo del `Estudio`:** No aplica (`N/A`).

---

## Trigger

- **Acción de usuario:** El **admin general** accede al panel de administración de usuarios, completa el formulario "Alta de Gerente Médico" (nombre, apellido, teléfono, mail, contraseña, matrícula y **especialidades**) y confirma el registro.
- **Endpoint HTTP:** `POST /api/admin/gerentes-medicos`

---

## Workflow Tree

### STEP 1: Verificación de rol `ADMIN_GENERAL` y validación de datos de entrada
**Actor**: Router HTTP (`admin_usuarios.py`) -> Servicio de Usuarios (`usuario_service.py`)
**Action**: Comprueba que el usuario autenticado posea `Rol.ADMIN_GENERAL`. Valida que `nombre`, `apellido`, `telefono`, `email`, `password` y `matricula` no estén vacíos, que `email` tenga formato válido, que `password` cumpla la política mínima de seguridad (>= 8 caracteres) y que `especialidades_ids` sea una lista no vacía de enteros únicos. *(Conforme al LEL, el sistema asume que la matrícula es válida sin consultar colegios médicos externos).*
**Timeout**: `1s`
**Input**:
```json
{
  "admin_usuario_id": 1,
  "rol_autenticado": "Rol.ADMIN_GENERAL",
  "nombre": "Laura",
  "apellido": "Gómez",
  "telefono": "+5492214556677",
  "email": "laura.gomez@exoma.com",
  "password": "********",
  "matricula": "MP-114589",
  "especialidades_ids": [1, 4]
}
```
**Output on SUCCESS**: Datos normalizados (`email` en minúsculas, `matricula` sin espacios extremos, `especialidades_ids` deduplicados) -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Sin sesión activa -> retornar `401 Unauthorized`.
  - `FAILURE(forbidden)`: El usuario autenticado no tiene `Rol.ADMIN_GENERAL` (por ejemplo, es `Rol.ADMINISTRATIVO` o `Rol.GERENTE_MEDICO`) -> retornar `403 Forbidden` (`SOLO_ADMIN_GENERAL`), sin efectos secundarios.
  - `FAILURE(validation_error)`: Campos obligatorios faltantes, `email` inválido, `matricula` vacía o `especialidades_ids` vacío -> retornar `422 Unprocessable Entity` (`DATOS_ENTRADA_INVALIDOS`).

**Observable states during this step**:
  - Customer/Actor (**Admin general**) sees: Indicador de envío en el formulario de alta.
  - Operator sees: Petición `POST /api/admin/gerentes-medicos` recibida.
  - Database: Sin escrituras.
  - Logs: `[usuario_service] step=1_validacion_alta_gerente admin_id=1 email=laura.gomez@exoma.com matricula=MP-114589`

---

### STEP 2: Verificación de unicidad (`email`, `matricula`) y existencia de `Especialidad`
**Actor**: Servicio de Usuarios (`usuario_service.py`) -> Repositorio (`usuario_repo.py`) -> PostgreSQL
**Action**:
  1. Consulta en `usuarios` si existe `email == payload.email`.
  2. Consulta en `medicos` si existe `matricula == payload.matricula`.
  3. Consulta en `especialidades` todas las filas cuyo `id IN payload.especialidades_ids` y comprueba que la cantidad encontrada coincida con la solicitada.
**Timeout**: `2s`
**Input**: `{ email: "laura.gomez@exoma.com", matricula: "MP-114589", especialidades_ids: [1, 4] }`
**Output on SUCCESS**: `{ especialidades: list[Especialidad] }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(conflict_email)`: Ya existe un `Usuario` con ese `email` -> retornar `409 Conflict` (`EMAIL_YA_REGISTRADO`, `retryable=False`).
  - `FAILURE(conflict_matricula)`: Ya existe un `Medico` con esa `matricula` -> retornar `409 Conflict` (`MATRICULA_YA_REGISTRADA`, `retryable=False`).
  - `FAILURE(validation_error)`: Alguno de los IDs en `especialidades_ids` no existe en la tabla `especialidades` -> retornar `404 Not Found` / `422 Unprocessable Entity` (`ESPECIALIDAD_INEXISTENTE`, indicando los IDs faltantes).

**Observable states during this step**:
  - Customer/Actor (**Admin general**) sees: Validación en curso.
  - Operator sees: Consultas `SELECT` de verificación sobre `usuarios`, `medicos` y `especialidades`.
  - Database: Solo lecturas; ninguna fila insertada.
  - Logs: `[usuario_repo] step=2_unicidad_ok email=laura.gomez@exoma.com matricula=MP-114589`

---

### STEP 3: Hash de contraseña y persistencia atómica (`usuarios`, `medicos`, `medicos_especialidades`)
**Actor**: Servicio de Usuarios (`usuario_service.py`) -> Repositorio (`usuario_repo.py`) -> PostgreSQL
**Action**:
  1. Genera `password_hash` con algoritmo seguro (`werkzeug.security.generate_password_hash` / `argon2` / `bcrypt`).
  2. Dentro de una única transacción de base de datos:
     - Inserta en `usuarios` con `email`, `password_hash`, `rol = Rol.GERENTE_MEDICO`, `nombre`, `apellido`, `telefono`, `debe_cambiar_password = False`.
     - Hace `flush()` para obtener `usuario.id`.
     - Inserta en `medicos` con `usuario_id = usuario.id` y `matricula`.
     - Hace `flush()` para obtener `medico.id`.
     - Inserta en `medicos_especialidades` una fila `(medico_id = medico.id, especialidad_id = esp.id)` por cada especialidad seleccionada.
     - Ejecuta `COMMIT`.
**Timeout**: `3s`
**Input**: `{ nombre, apellido, telefono, email, password_hash, matricula, especialidades }`
**Output on SUCCESS**: `{ usuario: Usuario, medico: Medico, especialidades: list[Especialidad] }` -> Retornar `201 Created` al **admin general** (FIN DEL WORKFLOW).
**Output on FAILURE**:
  - `FAILURE(conflict)`: Condición de carrera donde otra petición concurrente insertó el mismo `email` o `matricula` entre `STEP 2` y `STEP 3` (`IntegrityError` en `uq` de `usuarios.email` o `medicos.matricula`) -> ejecutar `ABORT_CLEANUP` (`rollback`) -> retornar `409 Conflict` (`RECURSO_DUPLICADO_CONCURRENTE`).
  - `FAILURE(database_error / timeout)`: Falla la inserción en `medicos` o `medicos_especialidades` tras el `flush()` de `usuarios` -> ejecutar `ABORT_CLEANUP` (`rollback`) -> retornar `500 Internal Server Error` (`DB_ERROR`, `retryable=True`).

**Observable states during this step**:
  - Customer/Actor (**Admin general**) sees: Notificación "Gerente médico registrado exitosamente" y detalle del perfil creado con su matrícula y **especialidades**.
  - Operator sees: Nuevo usuario con `rol = gerente_medico` y perfil `Medico` asociado.
  - Database:
    - Tabla `usuarios`: 1 nueva fila con `rol = Rol.GERENTE_MEDICO`, `debe_cambiar_password = False`, `created_at = now()`, `updated_at = now()`.
    - Tabla `medicos`: 1 nueva fila con `usuario_id = usuarios.id` y `matricula`.
    - Tabla `medicos_especialidades`: `N` nuevas filas vinculando `medico_id` con cada `especialidad_id`.
  - Logs: `[usuario_repo] step=3_alta_gerente_ok usuario_id=<uid> medico_id=<mid> matricula=MP-114589`

---

### ABORT_CLEANUP: Rollback transaccional de alta de gerente médico
**Triggered by**: Cualquier `IntegrityError` o `OperationalError` durante `STEP 3`.
**Actions** (in order):
  1. Ejecutar `db.session.rollback()` para deshacer la creación de filas en `medicos_especialidades`, `medicos` y `usuarios`, garantizando que nunca quede un `Usuario` con `Rol.GERENTE_MEDICO` sin su correspondiente fila en `medicos`.
  2. Registrar el error en los logs de aplicación con el detalle de la restricción violada.
**What customer/actor (**Admin general**) sees**: Mensaje de error específico (`409` si el correo o matrícula ya existen, o `500` si hubo un fallo temporal de base de datos).
**What operator sees**: Log `WARN`/`ERROR` indicando rollback limpio sin registros huérfanos en `usuarios`.

---

## State Transitions

```
Usuario + Medico (Gerente médico):
  [Inexistente]
    -- (STEP 1 + STEP 2 + STEP 3 exitosos) --> [Registrado y Activo:
                                                  usuarios.rol = Rol.GERENTE_MEDICO,
                                                  usuarios.debe_cambiar_password = False,
                                                  medicos.usuario_id = usuarios.id,
                                                  medicos_especialidades = [esp_1, ..., esp_N]]
    -- (Fallo en STEP 1, 2 o 3 + ABORT_CLEANUP) --> [Inexistente (0 filas creadas)]

Estudio (EstadoEstudio):
  Sin transición en este escenario.
```

---

## Handoff Contracts

### Frontend (Admin general) -> Backend (`router` -> `service` -> `repo`)
**Endpoint**: `POST /api/admin/gerentes-medicos`
**Payload**:
```json
{
  "nombre": "Laura",
  "apellido": "Gómez",
  "telefono": "+5492214556677",
  "email": "laura.gomez@exoma.com",
  "password": "ClaveSegura2026!",
  "matricula": "MP-114589",
  "especialidades_ids": [1, 4]
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "usuario_id": 27,
    "medico_id": 9,
    "rol": "gerente_medico",
    "nombre": "Laura",
    "apellido": "Gómez",
    "telefono": "+5492214556677",
    "email": "laura.gomez@exoma.com",
    "matricula": "MP-114589",
    "especialidades": [
      { "id": 1, "nombre": "Genética Médica" },
      { "id": 4, "nombre": "Pediatría" }
    ],
    "created_at": "2026-10-28T20:10:00Z"
  }
}
```
**Failure response** (`401` / `403` / `404` / `409` / `422` / `500`):
```json
{
  "ok": false,
  "error": "La matrícula profesional ingresada ya se encuentra registrada en el sistema.",
  "code": "MATRICULA_YA_REGISTRADA",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Mantener los datos en el formulario del **admin general** resaltando el campo en conflicto (`email`, `matricula` o `especialidades_ids`).

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Fila en `usuarios` (`flush`) | Step 3 | `ABORT_CLEANUP` | `db.session.rollback()` |
| Fila en `medicos` (`flush`) | Step 3 | `ABORT_CLEANUP` | `db.session.rollback()` |
| Filas en `medicos_especialidades` (`flush`) | Step 3 | `ABORT_CLEANUP` | `db.session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/perfiles.py`, el docstring de `Medico` establece explícitamente: `"Medico tratante/derivante. El gerente medico es un Medico con rol GERENTE_MEDICO."` y `Cupon.gerente_id` apunta a `medicos.id`. | High | Overview, STEP 3 | El alta de un **gerente médico** DEBE crear tanto la fila en `usuarios` (`rol = Rol.GERENTE_MEDICO`) como la fila en `medicos` y sus filas en `medicos_especialidades` dentro de la misma transacción. |
| RC-2 | `Usuario.debe_cambiar_password` tiene comentario en `usuarios.py`: `# True hasta que el paciente cambia la contrasena inicial (escenario 20)` y `default=False`. | Low | STEP 3 | Para el **gerente médico**, `debe_cambiar_password` se inicializa en `False` (solo el **paciente** tiene cambio obligatorio en el primer ingreso según el LEL). |
| RC-3 | En el LEL (`Sujeto: Médico`), se explicita: `"El sistema asume que la matrícula del médico es válida"`. | Low | STEP 1 | No se invoca ninguna API externa para validar la matrícula; únicamente se valida formato no vacío y unicidad en `medicos.matricula`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Alta completa de gerente médico | `POST /api/admin/gerentes-medicos` enviado por `Rol.ADMIN_GENERAL` con datos válidos, matrícula nueva y 2 especialidades existentes | Retorna `201 Created`; crea 1 fila en `usuarios` (`rol=Rol.GERENTE_MEDICO`, `password_hash != password`), 1 fila en `medicos` y 2 filas en `medicos_especialidades`. |
| `TC-02`: Rechazo por usuario sin rol `ADMIN_GENERAL` | `POST /api/admin/gerentes-medicos` enviado por un usuario con `Rol.GERENTE_MEDICO`, `Rol.MEDICO` o `Rol.ADMINISTRATIVO` | Retorna `403 Forbidden` (`SOLO_ADMIN_GENERAL`); no se inserta ninguna fila en `usuarios` ni `medicos`. |
| `TC-03`: Rechazo por email duplicado | `POST /api/admin/gerentes-medicos` con un `email` ya existente en `usuarios` | Retorna `409 Conflict` (`EMAIL_YA_REGISTRADO`); no se crea perfil en `medicos`. |
| `TC-04`: Rechazo por matrícula duplicada (incluso si pertenece a un médico común) | `POST /api/admin/gerentes-medicos` con una `matricula` ya registrada en `medicos` | Retorna `409 Conflict` (`MATRICULA_YA_REGISTRADA`); no queda ninguna fila huérfana en `usuarios`. |
| `TC-05`: Rechazo por especialidad inexistente | `POST /api/admin/gerentes-medicos` con `especialidades_ids=[1, 9999]` donde `9999` no existe en `especialidades` | Retorna `404 Not Found` / `422 Unprocessable Entity` (`ESPECIALIDAD_INEXISTENTE`); 0 filas creadas en `usuarios` y `medicos`. |
| `TC-06`: Rechazo por lista de especialidades vacía o campos obligatorios faltantes | `POST /api/admin/gerentes-medicos` con `especialidades_ids=[]` o `matricula=""` | Retorna `422 Unprocessable Entity` (`DATOS_ENTRADA_INVALIDOS`). |
| `TC-07`: Atomicidad transaccional ante fallo en `medicos` | Simulación de fallo de base de datos después de `session.flush()` de `Usuario` y antes de `commit()` de `Medico` | `ABORT_CLEANUP` ejecuta `rollback()` y verifica que `usuarios` no contenga el email intentado. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El **admin general** define la contraseña inicial del **gerente médico** en el formulario de alta (o el sistema la recibe en el payload de creación) y `debe_cambiar_password` queda en `False`, pudiendo el **gerente médico** cambiarla cuando quiera mediante el Escenario 34. | Verificado en `.ai/2-Glosario_LEL.md` ("Cambiar contraseña inicial: ... obligatorio en el primer ingreso del paciente") y `usuarios.py` (`debe_cambiar_password: default=False`). | Bajo. |
| A2 | El catálogo de `especialidades` ya se encuentra poblado mediante migración/seed inicial antes de registrar médicos o gerentes médicos. | Verificado en `.ai/2-Glosario_LEL.md` (`Objeto: Especialidad`). | Si la tabla `especialidades` estuviera vacía, el formulario no tendría opciones para seleccionar. |

## Open Questions

- ¿Se desea enviar un correo electrónico informativo de bienvenida al **gerente médico** tras su alta por el **admin general**, o el **admin general** le entrega sus credenciales por canal interno del laboratorio?

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada verificando `Usuario`, `Medico`, `Especialidad` y `MedicoEspecialidad` en `app/src/core/models/`. | Aprobada. |
