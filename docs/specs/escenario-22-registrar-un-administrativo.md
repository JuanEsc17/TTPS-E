# WORKFLOW: Escenario 22 – Registrar un administrativo
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-22`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Administrativo` |
| **Objetos** | *(Datos personales y de contacto del `Administrativo` del laboratorio central: `nombre`, `apellido`, `telefono`, `email`)* |
| **Verbos** | *(Autoregistro / Alta de `Administrativo`; habilita posteriormente `Iniciar sesión`, emitir `Presupuesto`, cargar autorización/rechazo de `Obra social`, cargar `Datos crudos`, `Retirar sample set`)* |
| **Estados** | *(No aplica estado de `Estudio`; crea `Usuario` con `Rol.ADMINISTRATIVO` y `debe_cambiar_password = False`)* |

---

## Overview

- **Objetivo**: Permitir que un **administrativo** del **laboratorio central** se registre por sí mismo como usuario del sistema.
- **Contexto**: El profesional **administrativo** necesita utilizar el sistema para gestionar los trámites de los **estudios** (presupuestos, autorizaciones de **obra social**, carga de **datos crudos** de Corea y programación de **retiro** de **sample set** con **FedEx**). Conforme al LEL, el **administrativo** se da de alta por sí mismo con nombre, apellido, teléfono y mail, y no puede darse de baja ni borrar su información.
- **Recursos**: `nombre`, `apellido`, `telefono`, correo electrónico (`email`), contraseña (`password`).
- **Episodios**:
  1. El **administrativo** ingresa sus datos personales (`nombre`, `apellido`).
  2. El **administrativo** registra sus datos de contacto (`telefono`, `email`) y su contraseña de acceso (`password`).
  3. El sistema registra al **administrativo** en la tabla `usuarios` con `rol = Rol.ADMINISTRATIVO`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Administrativo` (Sujeto LEL) | Persona del **laboratorio central** que se da de alta por sí misma para gestionar los trámites de los **estudios**. |
| `usuarios_router` / `administrativos_router` (`app/src/routers/`) | Capa `router`: recibe la solicitud HTTP de autoregistro de **administrativo** y valida el esquema de entrada. |
| `usuario_service` (`app/src/services/`) | Capa `service`: valida los campos obligatorios (`nombre`, `apellido`, `telefono`, `email`, `password`), verifica que el correo electrónico no esté en uso, genera el `password_hash` y crea el usuario con `Rol.ADMINISTRATIVO`. |
| `usuario_repo` (`app/src/repos/`) | Capa `repo`: consulta e inserta en la tabla `usuarios` (y opcionalmente registra el dispositivo en `dispositivos_conocidos`). |
| `PostgreSQL` | Persiste la fila en `usuarios` garantizando la restricción `UNIQUE(email)`. |

---

## Prerequisites

- El **administrativo** no posee aún una cuenta registrada con el mismo `email` en la tabla `usuarios`.
- La base de datos `PostgreSQL` se encuentra operativa con la migración de `usuarios` aplicada.

---

## Trigger

El **administrativo** completa el formulario de autoregistro de personal administrativo y confirma la operación.
- **Endpoint HTTP**: `POST /api/v1/administrativos/registro`

---

## Workflow Tree

### STEP 1: Validación de datos personales, datos de contacto y contraseña
**Actor**: `administrativos_router` -> `usuario_service`
**Action**:
1. Verifica que `nombre`, `apellido`, `telefono`, `email` y `password` estén presentes y no contengan cadenas vacías.
2. Valida longitudes máximas conforme al modelo `Usuario` (`nombre <= 100`, `apellido <= 100`, `telefono <= 30`, `email <= 255`), formato válido de correo electrónico y requisitos mínimos de `password` (>= 8 caracteres).
**Timeout**: `2s`
**Input**: `{ nombre: str, apellido: str, telefono: str, email: str, password: str, dispositivo_identificador: Optional[str] }`
**Output on SUCCESS**: Datos normalizados (`email` en minúsculas y sin espacios laterales) -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(validation_error)`: Falta `nombre`, `apellido`, `telefono`, `email` o `password`, el formato del correo es inválido, o se superan las longitudes de columna de `usuarios` -> retorna `400 Bad Request` (`code: "DATOS_ADMINISTRATIVO_INVALIDOS"`), sin efectos secundarios.
  - `FAILURE(timeout)`: Supera `2s` -> retorna `504 Gateway Timeout` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Administrativo`) sees: Indicador "Validando datos de registro...".
  - Operator sees: Solicitud `POST /api/v1/administrativos/registro` en proceso.
  - Database: Sin escrituras.
  - Logs: `[usuario_service] step_1_validar_registro_administrativo email=<email>`

---

### STEP 2: Verificación de disponibilidad del correo electrónico
**Actor**: `usuario_service` -> `usuario_repo` -> `PostgreSQL`
**Action**: Consulta la tabla `usuarios` filtrando por `usuarios.email == email` para comprobar que no exista ningún usuario (de cualquier rol) con ese correo electrónico.
**Timeout**: `3s`
**Input**: `{ email: str }`
**Output on SUCCESS**: `email` disponible -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(conflict)`: Ya existe una fila en `usuarios` con el mismo `email` -> retorna `409 Conflict` (`code: "EMAIL_YA_REGISTRADO"`), sin efectos secundarios.
  - `FAILURE(timeout)`: Consulta a `PostgreSQL` excede `3s` -> reintenta 1 vez (`500ms`); si persiste, retorna `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Administrativo`) sees: Spinner de carga en pantalla de registro.
  - Operator sees: Consulta `SELECT id FROM usuarios WHERE email = :email`.
  - Database: Solo lectura.
  - Logs: `[usuario_repo] step_2_verificar_email_disponible email=<email>`

---

### STEP 3: Persistencia del usuario con `Rol.ADMINISTRATIVO`
**Actor**: `usuario_service` -> `usuario_repo` -> `PostgreSQL`
**Action**:
1. Calcula el `password_hash` seguro de la contraseña ingresada.
2. Inserta en la tabla `usuarios` una nueva fila con:
   - `email = email`
   - `password_hash = password_hash`
   - `rol = Rol.ADMINISTRATIVO`
   - `nombre = nombre`
   - `apellido = apellido`
   - `telefono = telefono`
   - `debe_cambiar_password = False`
   *(Nota de modelo: a diferencia de `Medico`, `Paciente` y `Transportista`, el `Administrativo` no requiere tabla de perfil separada en `app/src/core/models/perfiles.py` porque todos sus atributos residen en `usuarios`).*
3. Si se proporcionó `dispositivo_identificador`, inserta la fila correspondiente en `dispositivos_conocidos` dentro de la misma transacción.
4. Ejecuta `COMMIT`.
**Timeout**: `3s`
**Input**: `{ nombre: str, apellido: str, telefono: str, email: str, password_hash: str, dispositivo_identificador: Optional[str] }`
**Output on SUCCESS**: `{ usuario_id: int, nombre: str, apellido: str, telefono: str, email: str, rol: "administrativo" }` -> Retorna `201 Created`.
**Output on FAILURE**:
  - `FAILURE(conflict)`: Inserción concurrente con el mismo `email` que dispara `IntegrityError` sobre `ix_usuarios_email` -> `ABORT_CLEANUP` (`ROLLBACK`) -> retorna `409 Conflict` (`code: "EMAIL_YA_REGISTRADO"`).
  - `FAILURE(database_error)` / `FAILURE(timeout)`: Fallo en `PostgreSQL` -> `ABORT_CLEANUP` (`ROLLBACK`) -> retorna `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Administrativo`) sees: Mensaje "Cuenta administrativa creada exitosamente. Ya puede iniciar sesión."
  - Operator sees: Nuevo usuario con `rol = 'ADMINISTRATIVO'` activo en `usuarios`.
  - Database:
    - `usuarios`: 1 nueva fila con `rol = 'ADMINISTRATIVO'`, `debe_cambiar_password = false`.
    - `dispositivos_conocidos`: 1 fila opcional si se envió `dispositivo_identificador`.
  - Logs: `[usuario_repo] step_3_administrativo_registrado_ok usuario_id=<id> email=<email>`

---

### ABORT_CLEANUP: Reversión de alta de administrativo
**Triggered by**: `IntegrityError`, error de conexión o timeout en `STEP 3`.
**Actions** (in order):
  1. Ejecutar `ROLLBACK` de la transacción activa en `PostgreSQL`.
  2. Registrar el fallo en los logs de aplicación.
**What customer (`Administrativo`) sees**: Mensaje de error claro indicando si el correo ya fue registrado (`409`) o si ocurrió un problema temporal (`503`).
**What operator sees**: Sin registros incompletos en `usuarios`.

---

## State Transitions

```
[No registrado] -> (STEP 1-3 exitosos) -> [Administrativo activo en usuarios (rol = Rol.ADMINISTRATIVO, debe_cambiar_password = False)]
[No registrado] -> (Fallo en STEP 1 o STEP 2) -> [No registrado]
[En persistencia STEP 3] -> (Fallo o colisión concurrente -> ABORT_CLEANUP) -> [No registrado]
[Administrativo activo] -> (Regla LEL: no existe transición de baja ni borrado de información) -> [Administrativo activo (permanente)]
```

---

## Handoff Contracts

### Frontend (`Administrativo`) -> Backend (`administrativos_router`)
**Endpoint**: `POST /api/v1/administrativos/registro`
**Payload**:
```json
{
  "nombre": "Carolina",
  "apellido": "Suárez",
  "telefono": "+5492216001122",
  "email": "carolina.suarez@labcentral.com.ar",
  "password": "AdminLab2026!Secure",
  "dispositivo_identificador": "fp_sha256_labcentral_pc04"
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "usuario_id": 71,
    "nombre": "Carolina",
    "apellido": "Suárez",
    "telefono": "+5492216001122",
    "email": "carolina.suarez@labcentral.com.ar",
    "rol": "administrativo",
    "debe_cambiar_password": false
  }
}
```
**Failure response** (`400` / `409` / `503`):
```json
{
  "ok": false,
  "error": "El correo electrónico ya se encuentra registrado en el sistema.",
  "code": "EMAIL_YA_REGISTRADO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: En caso de `400` o `409`, mostrar validación en formulario; en caso de `503`, permitir reintentar.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Fila en `usuarios` (`Rol.ADMINISTRATIVO`) | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` de la transacción SQL |
| Fila opcional en `dispositivos_conocidos` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` de la transacción SQL |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/usuarios.py` y `perfiles.py`, el rol `Rol.ADMINISTRATIVO` está definido en `enums.py` (línea 9) y todos sus datos (`nombre`, `apellido`, `telefono`, `email`, `password_hash`) están íntegramente contenidos en la tabla `usuarios`, sin tabla secundaria en `perfiles.py`. | Low | STEP 3 | Reflejado con exactitud en `STEP 3`: solo se inserta en `usuarios` (y opcionalmente `dispositivos_conocidos`). |
| RC-2 | En `.ai/2-Glosario_LEL.md` (`Sujeto: Administrativo`), se establece: *"El administrativo no puede darse de baja ni borrar su información"*. | Low | State Transitions / Test Cases | No se expone endpoint `DELETE` de cuenta y se incluye caso de prueba `TC-06` para verificar que el borrado/baja esté prohibido (`403`/`405`). |
| RC-3 | Los archivos `administrativos_router.py`, `usuario_service.py` y `usuario_repo.py` aún no existen en `app/src/`. | Medium | Actors | Especificados para su construcción en el flujo SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Registro válido de administrativo | `POST /api/v1/administrativos/registro` con `nombre`, `apellido`, `telefono`, `email` y `password` válidos | Retorna `201 Created`; crea fila en `usuarios` con `rol = Rol.ADMINISTRATIVO` y `debe_cambiar_password = False`. |
| `TC-02`: Campos obligatorios faltantes o vacíos | `POST /api/v1/administrativos/registro` sin `telefono` o con `nombre: ""` | Retorna `400 Bad Request` (`code: "DATOS_ADMINISTRATIVO_INVALIDOS"`); `0` filas insertadas en `usuarios`. |
| `TC-03`: Formato de correo electrónico inválido | `POST /api/v1/administrativos/registro` con `email: "correo-invalido"` | Retorna `400 Bad Request` (`code: "DATOS_ADMINISTRATIVO_INVALIDOS"`). |
| `TC-04`: Correo electrónico duplicado | `POST /api/v1/administrativos/registro` con un `email` ya registrado en `usuarios` | Retorna `409 Conflict` (`code: "EMAIL_YA_REGISTRADO"`). |
| `TC-05`: Colisión concurrente de registro con el mismo email | Dos solicitudes `POST /api/v1/administrativos/registro` simultáneas con igual `email` | Una retorna `201 Created` y la otra recibe `409 Conflict` tras `ABORT_CLEANUP` (`ROLLBACK`). |
| `TC-06`: Prohibición de baja o borrado de información del administrativo | Solicitud `DELETE /api/v1/administrativos/:id` o `DELETE /api/v1/usuarios/me` autenticada como `Rol.ADMINISTRATIVO` | Retorna `403 Forbidden` o `405 Method Not Allowed`, cumpliendo la regla del LEL de que ningún usuario puede darse de baja ni borrar su información. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El autoregistro de **administrativo** es abierto conforme a la entrevista (línea 193: *"Los médicos se autodan de alta y los administrativos también se autodan de alta"*) y al LEL (línea 15: *"Persona del laboratorio central que se da de alta por sí misma con nombre, apellido, teléfono y mail"*). | `.ai/1-Entrevista.md` (líneas 193, 201-202) y `.ai/2-Glosario_LEL.md` | Bajo. |

## Open Questions

- Ninguna. Los atributos requeridos y el comportamiento de autoregistro están completamente determinados en el LEL y en `app/src/core/models/usuarios.py`.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/usuarios.py` (`Usuario`) y `enums.py` (`Rol.ADMINISTRATIVO`). | Aprobada para implementación. |
