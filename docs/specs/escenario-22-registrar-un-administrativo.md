# WORKFLOW: Escenario 22 – Registrar un administrativo
**Versión**: 2.1
**Fecha**: 2026-11-23
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-22`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Admin general** | `Usuario` (`rol = Rol.ADMIN_GENERAL`) |
| **Sujetos** | **Administrativo** | `Usuario` (`rol = Rol.ADMINISTRATIVO`); sin tabla de perfil separada |
| **Objetos** | *(Datos personales y de contacto del **administrativo**)* | `Usuario.nombre`, `Usuario.apellido`, `Usuario.telefono`, `Usuario.email`, `Usuario.password_hash` |
| **Verbos** | **Dar de alta** (por el **admin general**) | Habilita posteriormente al **administrativo** a **iniciar sesión**, emitir **presupuesto**, cargar autorización/rechazo de **obra social**, cargar **datos crudos** y programar el **retiro** del **sample set** |
| **Estados** | *(No altera `EstadoEstudio`)* | Alta administrativa de usuario |

---

## Overview

- **Objetivo:** Dar de alta a un **administrativo** del **laboratorio central** como usuario del sistema.
- **Contexto:** El laboratorio necesita incorporar personal **administrativo** que gestione los trámites de los **estudios** (presupuestos, autorizaciones de **obra social**, carga de **datos crudos** de Corea y **retiro** de **sample set** con **FedEx**). Conforme al LEL, el **admin general** da de alta al **administrativo** con nombre, apellido, teléfono y mail, y el **administrativo** no puede darse de baja ni borrar su información.
- **Recursos:** Nombre (`Usuario.nombre`), apellido (`Usuario.apellido`), teléfono (`Usuario.telefono`), correo electrónico (`Usuario.email`), contraseña (`Usuario.password_hash`).
- **Episodios:**
  1. El **admin general** ingresa los datos personales del **administrativo** (nombre, apellido).
  2. El **admin general** registra sus datos de contacto (teléfono, correo electrónico) y su contraseña.
  3. El sistema registra al **administrativo** creando su usuario con `Rol.ADMINISTRATIVO`.

**Resumen del flujo:** El **admin general** autenticado envía `POST /api/v1/admin/administrativos` con los datos personales, de contacto y la contraseña. El servicio valida que el solicitante tenga `Rol.ADMIN_GENERAL`, que los datos sean válidos y que el correo electrónico no esté registrado en `usuarios`. Luego hashea la contraseña e inserta en `usuarios` una fila con `rol = Rol.ADMINISTRATIVO` y `debe_cambiar_password = False`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Admin general** (Sujeto LEL) | Carga los datos personales, de contacto y la contraseña para dar de alta al **administrativo**. |
| **Administrativo** (Sujeto LEL) | Usuario resultante del alta; no participa activamente en este workflow. |
| **Router HTTP** (`app/src/web/api/admin_usuarios.py`, blueprint `/api/v1/admin`) | Verifica sesión activa (`@requiere_sesion()`), valida el esquema de entrada con `RegistroAdministrativoSchema` (`app/src/web/validators/admin_usuarios_validator.py`) y formatea la respuesta HTTP. |
| **Servicio de Usuarios** (`app/src/core/services/usuario_service.py`, función `registrar_administrativo`) | Verifica el rol `Rol.ADMIN_GENERAL`, valida los datos, verifica la unicidad del email y calcula el `password_hash`. |
| **Repositorio de Usuarios** (`app/src/core/repos/usuario_repo.py`, funciones `buscar_por_email` y `crear_administrativo`) | Consulta e inserta en la tabla `usuarios`. |
| **PostgreSQL** (`db`) | Aplica la restricción `UNIQUE(usuarios.email)`. |

---

## Prerequisites

- **Sesión y Rol:** El usuario que ejecuta la acción debe tener sesión activa con `Usuario.rol == Rol.ADMIN_GENERAL`.
- **Datos existentes:** No debe existir ninguna fila en `usuarios` con el mismo `email`.
- **Estado previo del `Estudio`:** No aplica (`N/A`).

---

## Trigger

- **Acción de usuario:** El **admin general** accede al panel de administración de usuarios, completa el formulario "Alta de Administrativo" (nombre, apellido, teléfono, mail y contraseña) y confirma el registro.
- **Endpoint HTTP:** `POST /api/v1/admin/administrativos`

---

## Workflow Tree

### STEP 1: Verificación de rol `ADMIN_GENERAL` y validación de datos de entrada
**Actor**: Router HTTP (`admin_usuarios.py`) -> Servicio de Usuarios (`usuario_service.py`)
**Action**:
1. Comprueba que el usuario autenticado posea `Rol.ADMIN_GENERAL`.
2. Valida que `nombre`, `apellido`, `telefono`, `email` y `password` estén presentes y no vacíos; longitudes máximas conforme al modelo `Usuario` (`nombre <= 100`, `apellido <= 100`, `telefono <= 30`, `email <= 255`); formato válido de `email`; formato válido de `telefono` (expresión `^\+?[\d\s\-()]{7,20}$`, la misma `_REGEX_TELEFONO` de `usuario_service.py` usada en el Escenario 31); y política mínima de `password` (`validar_politica_password`, >= 8 caracteres).
**Timeout**: `1s`
**Input**:
```json
{
  "admin_usuario_id": 1,
  "rol_autenticado": "Rol.ADMIN_GENERAL",
  "nombre": "Carolina",
  "apellido": "Suárez",
  "telefono": "+5492216001122",
  "email": "carolina.suarez@labcentral.com.ar",
  "password": "********"
}
```
**Output on SUCCESS**: Datos normalizados (strings sin espacios extremos, `email` en minúsculas) -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Sin sesión activa -> retornar `401 Unauthorized`.
  - `FAILURE(forbidden)`: El usuario autenticado no tiene `Rol.ADMIN_GENERAL` (por ejemplo, es `Rol.ADMINISTRATIVO`, `Rol.GERENTE_MEDICO`, `Rol.MEDICO` o `Rol.PACIENTE`) -> retornar `403 Forbidden` (`SOLO_ADMIN_GENERAL`), sin efectos secundarios.
  - `FAILURE(validation_error)`: Campos obligatorios faltantes o vacíos, `email` o `telefono` con formato inválido, longitudes excedidas o `password` que no cumple la política -> retornar `422 Unprocessable Entity` (`DATOS_ENTRADA_INVALIDOS`).

**Observable states during this step**:
  - Customer/Actor (**Admin general**) sees: Indicador de envío en el formulario de alta.
  - Operator sees: Petición `POST /api/v1/admin/administrativos` recibida.
  - Database: Sin escrituras.
  - Logs: `[usuario_service] step=1_validacion_alta_administrativo admin_id=1 email=carolina.suarez@labcentral.com.ar`

---

### STEP 2: Verificación de disponibilidad del correo electrónico
**Actor**: Servicio de Usuarios (`usuario_service.py`) -> Repositorio (`usuario_repo.py`) -> PostgreSQL
**Action**: Consulta `usuario_repo.buscar_por_email(email)` para comprobar que no exista ningún usuario (de cualquier rol) con ese correo electrónico.
**Timeout**: `2s`
**Input**: `{ email: "carolina.suarez@labcentral.com.ar" }`
**Output on SUCCESS**: `email` disponible -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(conflict_email)`: Ya existe un `Usuario` con ese `email` -> retornar `409 Conflict` (`EMAIL_YA_REGISTRADO`, `retryable=False`).

**Observable states during this step**:
  - Customer/Actor (**Admin general**) sees: Validación en curso.
  - Operator sees: Consulta `SELECT` sobre `usuarios` por `email`.
  - Database: Solo lectura.
  - Logs: `[usuario_repo] step=2_email_disponible email=carolina.suarez@labcentral.com.ar`

---

### STEP 3: Hash de contraseña y persistencia del usuario con `Rol.ADMINISTRATIVO`
**Actor**: Servicio de Usuarios (`usuario_service.py`) -> Repositorio (`usuario_repo.py`) -> PostgreSQL
**Action**:
1. Genera `password_hash` con `hashear_password` (`app/src/core/services/seguridad.py`).
2. Inserta en `usuarios` una fila con `email`, `password_hash`, `rol = Rol.ADMINISTRATIVO`, `nombre`, `apellido`, `telefono`, `debe_cambiar_password = False`.
   *(Nota de modelo: a diferencia de `Medico`, `Paciente` y `Transportista`, el **administrativo** no requiere tabla de perfil separada en `app/src/core/models/perfiles.py`).*
3. Ejecuta `COMMIT`.
**Timeout**: `3s`
**Input**: `{ nombre, apellido, telefono, email, password_hash }`
**Output on SUCCESS**: `{ usuario: Usuario }` -> Retornar `201 Created` al **admin general** (FIN DEL WORKFLOW).
**Output on FAILURE**:
  - `FAILURE(conflict)`: Condición de carrera donde otra petición concurrente insertó el mismo `email` entre `STEP 2` y `STEP 3` (`IntegrityError` sobre `usuarios.email`) -> `ABORT_CLEANUP` -> retornar `409 Conflict` (`EMAIL_YA_REGISTRADO`).
  - `FAILURE(database_error / timeout)`: Fallo en PostgreSQL (`SQLAlchemyError`) -> `ABORT_CLEANUP` -> retornar `500 Internal Server Error` (`DB_ERROR`, `retryable=True`), mediante `ErrorBaseDatos` (`app/src/core/services/excepciones.py`).

**Observable states during this step**:
  - Customer/Actor (**Admin general**) sees: Notificación "Administrativo registrado exitosamente" y detalle del usuario creado.
  - Operator sees: Nuevo usuario con `rol = administrativo` activo en `usuarios`.
  - Database:
    - Tabla `usuarios`: 1 nueva fila con `rol = Rol.ADMINISTRATIVO`, `debe_cambiar_password = False`, `created_at = now()`.
  - Logs: `[usuario_repo] step=3_alta_administrativo_ok usuario_id=<uid> email=carolina.suarez@labcentral.com.ar`

---

### ABORT_CLEANUP: Rollback de alta de administrativo
**Triggered by**: Cualquier `IntegrityError` u `OperationalError` durante `STEP 3`.
**Actions** (in order):
  1. Ejecutar `db.session.rollback()`.
  2. Registrar el error en los logs de aplicación con el detalle de la restricción violada.
**What customer/actor (**Admin general**) sees**: Mensaje de error específico (`409` si el correo ya existe, `500` con `retryable=true` si hubo un fallo temporal de base de datos).
**What operator sees**: Log `WARN`/`ERROR` indicando rollback limpio, sin registros incompletos en `usuarios`.

---

## State Transitions

```
Usuario (Administrativo):
  [Inexistente]
    -- (Admin general: STEP 1 + STEP 2 + STEP 3 exitosos) --> [Registrado y Activo:
                                                                usuarios.rol = Rol.ADMINISTRATIVO,
                                                                usuarios.debe_cambiar_password = False]
    -- (Fallo en STEP 1, 2 o 3 + ABORT_CLEANUP) --> [Inexistente (0 filas creadas)]
  [Registrado y Activo]
    -- (Regla LEL: no existe transición de baja ni borrado de información) --> [Registrado y Activo (permanente)]

Estudio (EstadoEstudio):
  Sin transición en este escenario.
```

---

## Handoff Contracts

### Frontend (Admin general) -> Backend (`router` -> `service` -> `repo`)
**Endpoint**: `POST /api/v1/admin/administrativos`
**Payload**:
```json
{
  "nombre": "Carolina",
  "apellido": "Suárez",
  "telefono": "+5492216001122",
  "email": "carolina.suarez@labcentral.com.ar",
  "password": "AdminLab2026!Secure"
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "usuario_id": 71,
    "rol": "administrativo",
    "nombre": "Carolina",
    "apellido": "Suárez",
    "telefono": "+5492216001122",
    "email": "carolina.suarez@labcentral.com.ar",
    "debe_cambiar_password": false,
    "created_at": "2026-11-20T15:30:00Z"
  }
}
```
**Failure response** (`401` / `403` / `409` / `422` / `500`):
```json
{
  "ok": false,
  "error": "El correo electrónico ya se encuentra registrado.",
  "code": "EMAIL_YA_REGISTRADO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Mantener los datos en el formulario del **admin general** resaltando el campo en conflicto (`email`) o con error de validación; en caso de `500` con `retryable=true`, permitir reintentar.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Fila en `usuarios` (`Rol.ADMINISTRATIVO`) | Step 3 | `ABORT_CLEANUP` | `db.session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | `Rol.ADMINISTRATIVO` está definido en `enums.py` y todos los datos del **administrativo** (`nombre`, `apellido`, `telefono`, `email`, `password_hash`) residen en `usuarios`, sin tabla secundaria en `perfiles.py`. | Low | STEP 3 | Solo se inserta en `usuarios`. |
| RC-2 | En `.ai/2-Glosario_LEL.md` (`Sujeto: Administrativo`): *"El administrativo no puede darse de baja ni borrar su información"*. | Low | State Transitions / Test Cases | No se expone endpoint `DELETE`; se incluye `TC-08`. |
| RC-3 | El alta de **gerente médico** (Escenario 31) ya está implementada en `app/src/web/api/admin_usuarios.py` (blueprint `/api/v1/admin`), `app/src/web/validators/admin_usuarios_validator.py` y `usuario_service.registrar_gerente_medico`, con los códigos `SOLO_ADMIN_GENERAL`, `DATOS_ENTRADA_INVALIDOS` y `EMAIL_YA_REGISTRADO`. | Medium | Actors / STEP 1 | Se reutiliza el mismo blueprint, decorador, helpers (`hashear_password`, `validar_politica_password`, `usuario_repo.buscar_por_email`) y códigos de error. Se agregan `RegistroAdministrativoSchema`, `registrar_administrativo` y `usuario_repo.crear_administrativo`. |
| RC-4 | La versión 1.0 recibía `dispositivo_identificador` para registrar el dispositivo en `dispositivos_conocidos`. | Low | STEP 3 / Handoff | Se elimina: el dispositivo de la petición es el del **admin general**. El **administrativo** registra su dispositivo en su primer ingreso (Escenarios 26/27). |
| RC-5 | `ErrorBaseDatos` (`app/src/core/services/excepciones.py`) responde `500` con `reintentable=True` en todo el proyecto (el Escenario 31 lo usa así); la v2.0 de esta spec pedía `503`. | Medium | STEP 3 / ABORT_CLEANUP / Handoff | Se adopta `500 DB_ERROR retryable=true` para no introducir un status distinto solo para este escenario. |
| RC-6 | `usuario_service.registrar_gerente_medico` valida el formato de `telefono` con `_REGEX_TELEFONO`; la v2.0 de esta spec solo validaba la longitud. | Low | STEP 1 / TC-05 | Se reutiliza la misma validación en un helper común de alta por **admin general**. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Alta de administrativo | `POST /api/v1/admin/administrativos` enviado por `Rol.ADMIN_GENERAL` con datos válidos | Retorna `201 Created`; crea 1 fila en `usuarios` con `rol = Rol.ADMINISTRATIVO`, `debe_cambiar_password = False` y `password_hash != password`. |
| `TC-02`: Rechazo por usuario sin rol `ADMIN_GENERAL` | `POST /api/v1/admin/administrativos` enviado por `Rol.ADMINISTRATIVO`, `Rol.GERENTE_MEDICO`, `Rol.MEDICO` o `Rol.PACIENTE` | Retorna `403 Forbidden` (`SOLO_ADMIN_GENERAL`); 0 filas insertadas en `usuarios`. |
| `TC-03`: Rechazo sin sesión | `POST /api/v1/admin/administrativos` sin token | Retorna `401 Unauthorized`. |
| `TC-04`: Campos obligatorios faltantes o vacíos | Payload sin `telefono` o con `nombre: ""` | Retorna `422 Unprocessable Entity` (`DATOS_ENTRADA_INVALIDOS`); 0 filas insertadas. |
| `TC-05`: Email o teléfono con formato inválido, o contraseña que no cumple la política | `email: "correo-invalido"`, `telefono: "hola"` o `password: "123"` | Retorna `422 Unprocessable Entity` (`DATOS_ENTRADA_INVALIDOS`); 0 filas insertadas. |
| `TC-06`: Correo electrónico duplicado | `email` ya registrado en `usuarios` (de cualquier rol) | Retorna `409 Conflict` (`EMAIL_YA_REGISTRADO`). |
| `TC-07`: Colisión concurrente con el mismo email | Dos `POST /api/v1/admin/administrativos` simultáneos con igual `email` | Una retorna `201 Created` y la otra `409 Conflict` tras `ABORT_CLEANUP`. |
| `TC-08`: Prohibición de baja o borrado del administrativo | `DELETE /api/v1/admin/administrativos/:id` o `DELETE /api/v1/usuarios/me` | Retorna `403 Forbidden` o `405 Method Not Allowed`, cumpliendo la regla del LEL. |
| `TC-09`: Fallo de base de datos en la persistencia | `POST /api/v1/admin/administrativos` válido con `COMMIT` que lanza `SQLAlchemyError` | Retorna `500 Internal Server Error` (`DB_ERROR`, `retryable=true`); `ABORT_CLEANUP` deja 0 filas nuevas en `usuarios`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Por decisión del equipo (2026-11-20), el **administrativo** ya no se autorregistra: lo da de alta el **admin general**, del mismo modo que al **gerente médico**. Esto difiere de `.ai/1-Entrevista.md` (línea 193: *"los administrativos también se autodan de alta"*); `.ai/2-Glosario_LEL.md` y `.ai/3-Escenarios.md` fueron actualizados en consecuencia. | `.ai/2-Glosario_LEL.md` (`Sujeto: Administrativo`, `Sujeto: Admin general`), `.ai/3-Escenarios.md#Escenario-22` | Medio: si el cliente exige autorregistro, se debe volver a la versión 1.0. |
| A2 | El **admin general** define la contraseña inicial del **administrativo** y `debe_cambiar_password` queda en `False` (igual que el **gerente médico**, Escenario 31); el **administrativo** puede cambiarla mediante el Escenario 34. | `usuarios.py` (`debe_cambiar_password: default=False`), `.ai/2-Glosario_LEL.md` | Bajo. |

## Open Questions

- ¿Se desea enviar un correo electrónico al **administrativo** con sus credenciales tras el alta, o el **admin general** se las entrega por canal interno del laboratorio? (misma pregunta abierta que el Escenario 31).

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/usuarios.py` (`Usuario`) y `enums.py` (`Rol.ADMINISTRATIVO`). | Aprobada para implementación. |
| 2026-11-20 | Cambio de requerimiento: el **administrativo** ya no se autorregistra; lo da de alta el **admin general** (como en el Escenario 31). Se actualizan `.ai/2-Glosario_LEL.md` y `.ai/3-Escenarios.md`. El endpoint pasa de `POST /api/v1/administrativos/registro` a `POST /api/v1/admin/administrativos`; los códigos de error se alinean con el Escenario 31 (`SOLO_ADMIN_GENERAL`, `DATOS_ENTRADA_INVALIDOS` 422, `EMAIL_YA_REGISTRADO`); se elimina `dispositivo_identificador`. E22 aún no estaba implementado, por lo que no hay código a migrar. | Spec v2.0 aprobada. |
| 2026-11-23 | Al reutilizar la implementación del Escenario 31 se detectaron dos diferencias: (1) el fallo de base de datos se modela con `ErrorBaseDatos`, que responde `500` y no `503`; (2) el Escenario 31 valida el formato de `telefono` y esta spec no lo hacía. | Spec v2.1: `503` → `500 DB_ERROR retryable=true` (STEP 3, ABORT_CLEANUP, Handoff); se agrega la validación de formato de `telefono` (STEP 1, TC-05); se agrega TC-09 (fallo de BD); RC-5 y RC-6. |
