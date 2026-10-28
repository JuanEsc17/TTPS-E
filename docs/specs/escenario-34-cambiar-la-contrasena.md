# WORKFLOW: Escenario 34 – Cambiar la contraseña
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-34`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Paciente**, **Médico**, **Gerente médico**, **Administrativo**, **Bioinformático**, **Transportista**, **Admin general** | Modelo `Usuario` (`usuarios`: cualquiera de los 7 valores del enum `Rol` en `app/src/core/models/enums.py`) |
| **Objetos** | *(Credenciales de `Usuario`)* | Columnas `Usuario.password_hash` y `Usuario.debe_cambiar_password` en la tabla `usuarios` |
| **Verbos** | **Cambiar contraseña** | Reemplazar voluntariamente la contraseña actual por una nueva después del primer ingreso |
| **Verbos** | **Iniciar sesión** | El usuario utiliza la nueva contraseña en los próximos ingresos al sistema |
| **Estados** | *(No altera `EstadoEstudio`)* | Operación transversal de seguridad de cuenta sobre `usuarios` |

---

## Overview

- **Objetivo:** Permitir que cualquier usuario registrado y autenticado reemplace su contraseña actual por una nueva cuando lo desee.
- **Contexto:** El usuario ya inició sesión en el sistema, ya completó el cambio de su contraseña inicial si era un **paciente** (`Usuario.debe_cambiar_password == False`), y desea actualizar su contraseña por razones de seguridad o preferencia personal.
- **Recursos:** Sesión activa, contraseña actual (`password_actual`), nueva contraseña (`password_nueva`), hash almacenado (`Usuario.password_hash`).
- **Episodios:**
  1. El usuario solicita **cambiar contraseña**.
  2. El usuario ingresa su contraseña actual.
  3. El usuario ingresa la nueva contraseña.
  4. El sistema valida la contraseña actual.
  5. El sistema registra la nueva contraseña.
  6. El usuario usa la nueva contraseña en los próximos ingresos (**iniciar sesión**).

**Resumen del flujo:** Cualquier usuario autenticado (con rol `PACIENTE`, `MEDICO`, `GERENTE_MEDICO`, `ADMINISTRATIVO`, `BIOINFORMATICO`, `TRANSPORTISTA` o `ADMIN_GENERAL`) envía una petición `POST /api/auth/cambiar-password` (o `PUT /api/usuarios/me/password`) con `password_actual` y `password_nueva` (más `password_nueva_confirmacion`). El servicio de autenticación recupera el registro `Usuario` desde `usuarios`, verifica que `debe_cambiar_password == False` (si fuera `True`, corresponde al flujo de **Cambiar contraseña inicial** del Escenario 20), comprueba criptográficamente `password_actual` contra `Usuario.password_hash`, valida que `password_nueva` cumpla la política de complejidad y sea distinta de `password_actual`, genera el nuevo `password_hash` y actualiza `usuarios.password_hash` en PostgreSQL.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Usuario autenticado** (**Paciente**, **Médico**, **Gerente médico**, **Administrativo**, **Bioinformático**, **Transportista**, **Admin general**) | Solicita el cambio voluntario de su contraseña ingresando la contraseña actual y la nueva. |
| **Router de Autenticación** (`app/src/routers/auth.py`) | Verifica que exista una sesión activa válida, recibe el payload y evita registrar contraseñas en texto plano en los logs. |
| **Servicio de Autenticación** (`app/src/services/auth_service.py`) | Verifica `password_actual` contra `Usuario.password_hash`, aplica las reglas de fortaleza sobre `password_nueva`, calcula el nuevo hash y actualiza el usuario. |
| **Repositorio de Usuarios** (`app/src/repos/usuario_repo.py`) | Lee y actualiza la fila del `Usuario` en la tabla `usuarios`. |
| **PostgreSQL** (`db`) | Persiste de forma atómica el nuevo `password_hash` y actualiza `updated_at`. |

---

## Prerequisites

- **Sesión y Rol:**
  - El usuario debe contar con una sesión activa válida y pertenecer a cualquiera de los 7 roles del sistema (`Rol.PACIENTE`, `Rol.MEDICO`, `Rol.GERENTE_MEDICO`, `Rol.ADMINISTRATIVO`, `Rol.BIOINFORMATICO`, `Rol.TRANSPORTISTA`, `Rol.ADMIN_GENERAL`).
  - `Usuario.debe_cambiar_password` debe ser `False` (el usuario ya realizó el cambio de contraseña inicial si era paciente).
- **Datos existentes en `app/src/core/models/`:**
  - Existe la fila del usuario autenticado en la tabla `usuarios` con su `password_hash` vigente.
- **Estado previo del `Estudio`:** No aplica (`N/A`).

---

## Trigger

- **Acción de usuario:** El usuario accede a la opción "Cambiar contraseña" de su perfil, completa su contraseña actual y la nueva contraseña, y confirma la operación.
- **Endpoint HTTP:** `POST /api/auth/cambiar-password`

---

## Workflow Tree

### STEP 1: Verificación de sesión activa y validación de formato de entrada
**Actor**: Router de Autenticación (`auth.py`) -> Servicio de Autenticación (`auth_service.py`)
**Action**:
  1. Extrae el `usuario_id` de la sesión activa.
  2. Verifica que `password_actual`, `password_nueva` y `password_nueva_confirmacion` estén presentes y no sean cadenas vacías.
  3. Verifica que `password_nueva == password_nueva_confirmacion`.
  4. Verifica que `password_nueva` cumpla la política de seguridad (longitud mínima de 8 caracteres, máximo 128 caracteres) y que `password_nueva != password_actual`.
**Timeout**: `1s`
**Input**:
```json
{
  "usuario_autenticado_id": 15,
  "password_actual": "[REDACTED]",
  "password_nueva": "[REDACTED]",
  "password_nueva_confirmacion": "[REDACTED]"
}
```
**Output on SUCCESS**: `{ usuario_id: 15, password_actual: str, password_nueva: str }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: No existe sesión activa o el token de sesión es inválido -> retornar `401 Unauthorized` (`SESION_NO_VALIDA`).
  - `FAILURE(validation_error)`:
    - Campos vacíos o faltantes -> retornar `422 Unprocessable Entity` (`CAMPOS_REQUERIDOS`).
    - `password_nueva != password_nueva_confirmacion` -> retornar `422 Unprocessable Entity` (`CONFIRMACION_NO_COINCIDE`).
    - `password_nueva` tiene menos de 8 caracteres -> retornar `422 Unprocessable Entity` (`PASSWORD_DEBIL`).
    - `password_nueva == password_actual` -> retornar `422 Unprocessable Entity` (`PASSWORD_IGUAL_A_ACTUAL`).

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Indicador "Actualizando contraseña..." en el formulario.
  - Operator sees: Solicitud `POST /api/auth/cambiar-password` (sin valores de contraseña en logs).
  - Database: Sin accesos ni escrituras aún.
  - Logs: `[auth_service] step=1_validar_input_cambio_password usuario_id=15`

---

### STEP 2: Validación de la contraseña actual contra `Usuario.password_hash`
**Actor**: Servicio de Autenticación (`auth_service.py`) -> Repositorio de Usuarios (`usuario_repo.py`) -> PostgreSQL
**Action**:
  1. Recupera la fila de `usuarios` para `id == usuario_id` con `SELECT ... FOR UPDATE`.
  2. Evalúa `check_password_hash(usuario.password_hash, password_actual)` en tiempo constante.
**Timeout**: `2s`
**Input**: `{ usuario_id: 15, password_actual: "[REDACTED]" }`
**Output on SUCCESS**: `{ usuario: Usuario }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(forbidden / invalid_credentials)`: `check_password_hash` devuelve `False` (la contraseña actual ingresada es incorrecta) -> liberar transacción y retornar `400 Bad Request` / `401 Unauthorized` (`PASSWORD_ACTUAL_INCORRECTA`, `retryable=False`).
  - `FAILURE(not_found)`: El usuario de la sesión no existe en `usuarios` -> retornar `404 Not Found`.

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Validación de credenciales en curso; si falla, ve el mensaje "La contraseña actual ingresada es incorrecta.".
  - Operator sees: Evento de validación de contraseña actual (`ok` o `fallido` para auditoría de seguridad).
  - Database: Lectura de `usuarios.password_hash`; sin modificaciones si la validación falla.
  - Logs: `[auth_service] step=2_verificacion_password_actual usuario_id=15 resultado=<ok|fallo>`

---

### STEP 3: Generación de nuevo hash y persistencia en `usuarios`
**Actor**: Servicio de Autenticación (`auth_service.py`) -> Repositorio de Usuarios (`usuario_repo.py`) -> PostgreSQL
**Action**:
  1. Calcula `nuevo_hash = generate_password_hash(password_nueva)`.
  2. Actualiza `usuario.password_hash = nuevo_hash` y garantiza `usuario.debe_cambiar_password = False`.
  3. Ejecuta `COMMIT` en PostgreSQL.
  4. Rota el identificador de la sesión activa (prevención de session fixation) manteniendo al usuario autenticado en el dispositivo actual.
**Timeout**: `2s`
**Input**: `{ usuario_id: 15, nuevo_hash: "scrypt:32768:8:1$..." }`
**Output on SUCCESS**: `{ usuario_id: 15, actualizado_en: datetime }` -> Retornar `200 OK` al usuario (FIN DEL WORKFLOW).
**Output on FAILURE**:
  - `FAILURE(database_error / timeout)`: Error al persistir el cambio en `usuarios` -> ejecutar `ABORT_CLEANUP` (`rollback`) -> retornar `500 Internal Server Error` (`DB_UPDATE_ERROR`, `retryable=True`).

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Mensaje de confirmación "Tu contraseña ha sido actualizada correctamente.". En futuros inicios de sesión deberá usar la nueva contraseña, mientras que la anterior queda invalidada.
  - Operator sees: `usuarios.updated_at` actualizado para `usuario_id = 15`.
  - Database:
    - Tabla `usuarios`: `password_hash = <nuevo_hash>`, `debe_cambiar_password = False`, `updated_at = now()`.
  - Logs: `[usuario_repo] step=3_password_actualizada_ok usuario_id=15 rol=<rol>`

---

### ABORT_CLEANUP: Rollback ante fallo de persistencia en STEP 3
**Triggered by**: Error de base de datos o timeout en `STEP 3`.
**Actions** (in order):
  1. Ejecutar `db.session.rollback()` para asegurar que `usuarios.password_hash` conserve íntegro el hash de la contraseña anterior.
  2. Mantener la sesión actual sin alteraciones para que el usuario pueda reintentar.
**What customer/actor (Usuario) sees**: Mensaje de error temporal indicando que no se pudo guardar la nueva contraseña y que su contraseña anterior sigue vigente.
**What operator sees**: Log `ERROR` en `usuario_repo` con detalle de la excepción de base de datos.

---

## State Transitions

```
Usuario (usuarios.password_hash):
  [Activo con password_hash = H_actual, debe_cambiar_password = False]
    -- (STEP 1 + STEP 2 + STEP 3 exitosos) -->
  [Activo con password_hash = H_nuevo (H_nuevo != H_actual), debe_cambiar_password = False]

  [Activo con password_hash = H_actual]
    -- (STEP 2 falla por contraseña actual incorrecta o STEP 3 falla + ABORT_CLEANUP) -->
  [Activo con password_hash = H_actual (sin cambios)]

Estudio (EstadoEstudio):
  Sin transición en este escenario.
```

---

## Handoff Contracts

### Frontend (Usuario autenticado) -> Backend (`router` -> `service` -> `repo`)
**Endpoint**: `POST /api/auth/cambiar-password`
**Payload**:
```json
{
  "password_actual": "MiClaveAnterior2025!",
  "password_nueva": "MiNuevaClaveSegura2026#",
  "password_nueva_confirmacion": "MiNuevaClaveSegura2026#"
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "usuario_id": 15,
    "mensaje": "La contraseña se actualizó correctamente.",
    "updated_at": "2026-10-28T20:15:30Z"
  }
}
```
**Failure response – Contraseña actual incorrecta** (`400 Bad Request`):
```json
{
  "ok": false,
  "error": "La contraseña actual ingresada es incorrecta.",
  "code": "PASSWORD_ACTUAL_INCORRECTA",
  "retryable": false
}
```
**Failure response – Nueva contraseña inválida o igual a la actual** (`422 Unprocessable Entity`):
```json
{
  "ok": false,
  "error": "La nueva contraseña debe ser diferente de la contraseña actual y tener al menos 8 caracteres.",
  "code": "PASSWORD_INVALIDA",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Limpiar los campos de contraseña del formulario en el cliente y mostrar el mensaje de error correspondiente.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Modificación de `usuarios.password_hash` en sesión SQLAlchemy | Step 3 | `ABORT_CLEANUP` | `db.session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/usuarios.py`, `Usuario` cuenta con `password_hash: Mapped[str] = mapped_column(String(255))`, `debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=False)` y hereda de `TimestampMixin` (`created_at`, `updated_at`). | Low | Overview, STEP 3 | El modelo soporta directamente el flujo de actualización y registro de auditoría temporal en `updated_at`. |
| RC-2 | El LEL distingue explícitamente entre **Cambiar contraseña inicial** (Escenario 20, obligatorio para el **paciente** en su primer ingreso cuando `debe_cambiar_password == True`) y **Cambiar contraseña** (Escenario 34, voluntario para los 7 roles del sistema). | Low | Overview, Prerequisites | La especificación asegura que `debe_cambiar_password` quede en `False` y que el endpoint esté habilitado para los 7 valores de `Rol`. |
| RC-3 | Seguridad de datos sensibles destacada en `.ai/1-Entrevista.md` (línea 315): nunca deben registrarse `password_actual` ni `password_nueva` en logs ni almacenarse en texto plano. | High | STEP 1, STEP 2, STEP 3 | Se especificó el enmascaramiento `[REDACTED]` en logs y comparación/almacenamiento exclusivamente mediante hashes criptográficos con sal. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Cambio de contraseña exitoso e ingreso posterior con la nueva clave | `POST /api/auth/cambiar-password` con `password_actual` correcta y `password_nueva` válida, seguido de `POST /api/auth/login` | Retorna `200 OK`, actualiza `usuarios.password_hash`; el login con la contraseña anterior falla (`401`) y el login con `password_nueva` tiene éxito (`200`). |
| `TC-02`: Habilitado para los 7 roles del sistema (`Rol`) | Ejecución de `POST /api/auth/cambiar-password` con usuarios de rol `PACIENTE`, `MEDICO`, `GERENTE_MEDICO`, `ADMINISTRATIVO`, `BIOINFORMATICO`, `TRANSPORTISTA` y `ADMIN_GENERAL` | Todos los roles pueden cambiar su contraseña exitosamente (`200 OK`). |
| `TC-03`: Rechazo por contraseña actual incorrecta | `POST /api/auth/cambiar-password` con `password_actual` que no coincide con `usuario.password_hash` | Retorna `400 Bad Request` (`PASSWORD_ACTUAL_INCORRECTA`); `usuarios.password_hash` no se modifica. |
| `TC-04`: Rechazo cuando la nueva contraseña es igual a la actual | `POST /api/auth/cambiar-password` con `password_nueva == password_actual` | Retorna `422 Unprocessable Entity` (`PASSWORD_IGUAL_A_ACTUAL`); no actualiza la base de datos. |
| `TC-05`: Rechazo cuando la confirmación no coincide o la clave es muy corta | `POST /api/auth/cambiar-password` con `password_nueva != password_nueva_confirmacion` o longitud `< 8` | Retorna `422 Unprocessable Entity` (`CONFIRMACION_NO_COINCIDE` / `PASSWORD_DEBIL`). |
| `TC-06`: Rechazo sin sesión activa | `POST /api/auth/cambiar-password` sin cookie/token de autenticación | Retorna `401 Unauthorized` (`SESION_NO_VALIDA`). |
| `TC-07`: Fallo de base de datos en `STEP 3` preserva la contraseña anterior | Simulación de fallo en `db.session.commit()` al guardar `password_hash` | `ABORT_CLEANUP` ejecuta `rollback()` y el usuario sigue pudiendo autenticarse con `password_actual`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | La longitud mínima de una contraseña nueva es de 8 caracteres y debe diferir de la contraseña actual. | Estándar de seguridad de aplicaciones web y `.ai/1-Entrevista.md` (línea 315: "máxima atención en la parte de seguridad"). | Bajo. |
| A2 | Al cambiar la contraseña voluntariamente, los dispositivos conocidos (`dispositivos_conocidos`) del usuario se mantienen registrados, rotándose únicamente el token/cookie de la sesión activa. | Verificado en `app/src/core/models/usuarios.py` (`DispositivoConocido`). | Bajo. |

## Open Questions

- ¿Se desea invalidar simultáneamente todas las demás sesiones activas abiertas del usuario en otros navegadores/dispositivos cuando ejecuta **Cambiar contraseña**? *(Recomendado por seguridad).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada verificando `Usuario` y `Rol` en `app/src/core/models/usuarios.py` y `enums.py`. | Aprobada. |
