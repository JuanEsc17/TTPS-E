# WORKFLOW: Escenario 20 – Cambiar la contraseña inicial
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-20`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Paciente`, `Médico` (contexto: quien dio de alta al paciente) |
| **Objetos** | *(Credenciales iniciales del usuario: usuario/correo electrónico, contraseña inicial, nueva contraseña)* |
| **Verbos** | `Cambiar contraseña inicial`, `Iniciar sesión`, `Dar de alta paciente` |
| **Estados** | *(Transición de seguridad de cuenta: `Usuario.debe_cambiar_password` pasa de `True` a `False` y registra `DispositivoConocido`)* |

---

## Overview

- **Objetivo**: Permitir que el **paciente** establezca una contraseña propia en su primer ingreso al sistema.
- **Contexto**: El **médico** creó al **paciente** (`Dar de alta paciente`) y el sistema envió sus credenciales iniciales por correo electrónico, dejando `usuarios.debe_cambiar_password = True`.
- **Recursos**: Usuario (`email`), contraseña inicial, nueva contraseña, confirmación de nueva contraseña, huella del dispositivo (`dispositivo_identificador`).
- **Episodios**:
  1. El **paciente** recibe sus credenciales iniciales por correo electrónico.
  2. El **paciente** ingresa con la contraseña inicial (`Iniciar sesión` -> detecta `debe_cambiar_password == True`).
  3. El sistema solicita obligatoriamente cambiar la contraseña antes de habilitar el acceso a cualquier funcionalidad protegida.
  4. El **paciente** establece una nueva contraseña; el sistema actualiza `password_hash`, pasa `debe_cambiar_password = False`, registra el dispositivo actual en `dispositivos_conocidos` y habilita la sesión activa del **paciente**.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` (Sujeto LEL) | Usuario con `Rol.PACIENTE` (o su padre/responsable si es menor de edad) que ingresa por primera vez y reemplaza la contraseña inicial por una propia. |
| `auth_router` (`app/src/routers/`) | Capa `router`: recibe la petición de cambio de contraseña inicial, valida el token temporal de primer ingreso (o credenciales iniciales) y el formato del payload. |
| `auth_service` (`app/src/services/`) | Capa `service`: verifica que `usuario.debe_cambiar_password == True`, comprueba la contraseña inicial, valida la política de seguridad de la nueva contraseña (y que sea distinta de la inicial), genera el nuevo `password_hash`, marca `debe_cambiar_password = False`, registra el `DispositivoConocido` inicial y emite la sesión definitiva. |
| `usuario_repo` (`app/src/repos/`) | Capa `repo`: lee y actualiza la fila en `usuarios` y crea/actualiza la fila en `dispositivos_conocidos` de manera atómica. |
| `PostgreSQL` | Persiste el cambio en `usuarios` (`password_hash`, `debe_cambiar_password = False`, `updated_at`) y en `dispositivos_conocidos`. |

---

## Prerequisites

- El **paciente** existe en la tabla `usuarios` con `rol = Rol.PACIENTE` y `debe_cambiar_password = True`, y tiene su perfil asociado en la tabla `pacientes`.
- El **paciente** ha recibido el correo electrónico con su `email` y su contraseña inicial (o acaba de completar el paso de validación de credenciales iniciales en `Iniciar sesión` recibiendo el estado `requiere_cambio_password = true` / token de alcance limitado `scope = "cambio_password_inicial"`).

---

## Trigger

El **paciente**, tras autenticarse con su contraseña inicial y ser redirigido a la pantalla obligatoria de cambio de contraseña inicial, envía su nueva contraseña.
- **Endpoint HTTP**: `POST /api/v1/auth/cambiar-password-inicial`

---

## Workflow Tree

### STEP 1: Validación de contexto de primer ingreso y formato de la nueva contraseña
**Actor**: `auth_router` -> `auth_service`
**Action**:
1. Valida el token temporal de primer ingreso (o el par `email` + `password_inicial` enviado) y obtiene el `usuario_id`.
2. Verifica que `nueva_password` y `confirmacion_password` coincidan exactamente.
3. Verifica que `nueva_password` cumpla los requisitos mínimos de seguridad (longitud >= 8 caracteres, al menos una letra y un número) y que **no sea idéntica** a `password_inicial`.
**Timeout**: `2s`
**Input**: `{ password_inicial: str, nueva_password: str, confirmacion_password: str, dispositivo_identificador: str }` (más token de primer ingreso o `email`).
**Output on SUCCESS**: Datos de entrada validados -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Token de primer ingreso ausente, expirado o inválido -> retorna `401 Unauthorized` (`code: "TOKEN_PRIMER_INGRESO_INVALIDO"`).
  - `FAILURE(validation_error)`: `nueva_password != confirmacion_password`, longitud menor a 8 caracteres, o `nueva_password == password_inicial` -> retorna `400 Bad Request` (`code: "NUEVA_PASSWORD_INVALIDA"`), indicando el motivo específico al **paciente**.
  - `FAILURE(timeout)`: Supera `2s` -> retorna `504 Gateway Timeout` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: Pantalla "Cambiar contraseña inicial" con indicador de validación en curso.
  - Operator sees: Solicitud `POST /api/v1/auth/cambiar-password-inicial` en ejecución.
  - Database: `usuarios.debe_cambiar_password` continúa en `true`.
  - Logs: `[auth_service] step_1_validar_cambio_password_inicial usuario_id=<id>`

---

### STEP 2: Verificación de estado `debe_cambiar_password` y comprobación de contraseña inicial en BD
**Actor**: `auth_service` -> `usuario_repo` -> `PostgreSQL`
**Action**:
1. Obtiene la fila de `usuarios` con `SELECT ... FOR UPDATE` para evitar condiciones de carrera por doble envío simultáneo.
2. Verifica que el usuario tenga `debe_cambiar_password == True`.
3. Verifica criptográficamente que `password_inicial` coincida con `usuario.password_hash` actual (y que el hash de `nueva_password` no coincida con `usuario.password_hash`).
**Timeout**: `3s`
**Input**: `{ usuario_id: int, password_inicial: str, nueva_password: str }`
**Output on SUCCESS**: Usuario bloqueado en transacción y verificado -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(invalid_state)`: `usuario.debe_cambiar_password == False` (el **paciente** ya había cambiado su contraseña inicial previamente) -> libera lock y retorna `409 Conflict` (`code: "PASSWORD_INICIAL_YA_CAMBIADA"`), redirigiendo al flujo normal de `Iniciar sesión` o `Cambiar contraseña`.
  - `FAILURE(unauthorized)`: `password_inicial` no coincide con `usuario.password_hash` -> libera lock y retorna `401 Unauthorized` (`code: "PASSWORD_INICIAL_INCORRECTA"`).
  - `FAILURE(validation_error)`: `nueva_password` coincide con el hash actual -> retorna `400 Bad Request` (`code: "PASSWORD_IGUAL_A_INICIAL"`).
  - `FAILURE(timeout)`: Bloqueo en `PostgreSQL` > `3s` -> retorna `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: Spinner "Actualizando contraseña...".
  - Operator sees: Lock de fila en `usuarios` para `id = usuario_id`.
  - Database: Sin cambios confirmados todavía (`debe_cambiar_password = true`).
  - Logs: `[usuario_repo] step_2_verificar_usuario_primer_ingreso usuario_id=<id> debe_cambiar_password=True`

---

### STEP 3: Actualización de `password_hash`, desactivación de `debe_cambiar_password`, registro de `DispositivoConocido` y emisión de sesión
**Actor**: `auth_service` -> `usuario_repo` -> `PostgreSQL`
**Action**:
1. Calcula el nuevo hash seguro (`argon2`/`bcrypt`) para `nueva_password`.
2. Actualiza en `usuarios`: `password_hash = nuevo_hash`, `debe_cambiar_password = False`, `updated_at = func.now()`.
3. Conforme a la entrevista (`.ai/1-Entrevista.md` líneas 321-323: *"con el cambio de contraseña ya puede ingresar"* sin pedir doble factor adicional en ese primer ingreso porque la contraseña inicial llegó a su mail), inserta o actualiza en `dispositivos_conocidos` la fila `(usuario_id, identificador = hash(dispositivo_identificador), ultimo_acceso = func.now())`.
4. Realiza `COMMIT` de la transacción y emite el token/cookie de sesión autenticada completa para el **paciente**.
**Timeout**: `3s`
**Input**: `{ usuario_id: int, nuevo_password_hash: str, dispositivo_identificador: str }`
**Output on SUCCESS**: `{ usuario_id: int, rol: "paciente", debe_cambiar_password: false, sesion_activa: true }` -> Retorna `200 OK` con sesión iniciada y redirige al panel principal del **paciente**.
**Output on FAILURE**:
  - `FAILURE(database_error)` / `FAILURE(timeout)`: Error al escribir en `usuarios` o `dispositivos_conocidos` -> ejecuta `ABORT_CLEANUP` (`ROLLBACK`) -> retorna `500 Internal Server Error` / `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: Mensaje "Contraseña actualizada con éxito. Bienvenido/a." y acceso directo a su panel de **paciente**.
  - Operator sees: Sesión activa emitida; `debe_cambiar_password = false`.
  - Database:
    - `usuarios`: `password_hash` actualizado, `debe_cambiar_password = false`, `updated_at` actualizado.
    - `dispositivos_conocidos`: fila registrada para `(usuario_id, identificador)` con `ultimo_acceso = now()`.
  - Logs: `[auth_service] step_3_password_inicial_cambiada_ok usuario_id=<id> dispositivo_registrado=True`

---

### ABORT_CLEANUP: Reversión de cambio de contraseña inicial inconcluso
**Triggered by**: Fallo de base de datos o timeout en `STEP 3`.
**Actions** (in order):
  1. Ejecutar `ROLLBACK` de la transacción en `PostgreSQL` para garantizar que `usuarios.password_hash` conserve el hash de la contraseña inicial y `usuarios.debe_cambiar_password` permanezca en `True`.
  2. No emitir token de sesión completa ni eliminar el token temporal de primer ingreso (si aún no expiró), permitiendo al **paciente** reintentar el envío.
**What customer (`Paciente`) sees**: Mensaje de error temporal ("No se pudo guardar la nueva contraseña por un problema temporal. Intente nuevamente.") permaneciendo en la pantalla de cambio de contraseña inicial.
**What operator sees**: Error registrado en logs sin desincronización entre `password_hash` y `debe_cambiar_password`.

---

## State Transitions

```
[Usuario(debe_cambiar_password=True, sesion=primer_ingreso_restringido)]
   -> (STEP 1-3 exitosos)
   -> [Usuario(debe_cambiar_password=False, sesion=activa_completa) + DispositivoConocido registrado]

[Usuario(debe_cambiar_password=True)]
   -> (Fallo en STEP 1 o STEP 2)
   -> [Usuario(debe_cambiar_password=True, sesion=primer_ingreso_restringido)]

[Usuario(debe_cambiar_password=False)]
   -> (Intento de invocar endpoint de cambio inicial en STEP 2)
   -> [409 Conflict PASSWORD_INICIAL_YA_CAMBIADA (sin cambios)]
```

---

## Handoff Contracts

### Frontend (`Paciente`) -> Backend (`auth_router`)
**Endpoint**: `POST /api/v1/auth/cambiar-password-inicial`
**Headers**: `Authorization: Bearer <token_temporal_primer_ingreso>` (y cookie/header `X-Device-Id`)
**Payload**:
```json
{
  "password_inicial": "Tmp#98aB!2",
  "nueva_password": "MiClaveSegura2026!",
  "confirmacion_password": "MiClaveSegura2026!",
  "dispositivo_identificador": "fp_sha256_9f86d081884c7d659a2feaa0c55ad015"
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "usuario_id": 108,
    "email": "lucia.fernandez@example.com",
    "rol": "paciente",
    "debe_cambiar_password": false,
    "dispositivo_registrado": true,
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
    "redirect_to": "/paciente/estudios"
  }
}
```
**Failure response** (`400` / `401` / `409` / `503`):
```json
{
  "ok": false,
  "error": "La nueva contraseña no puede ser igual a la contraseña inicial.",
  "code": "PASSWORD_IGUAL_A_INICIAL",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Si `code == "PASSWORD_INICIAL_YA_CAMBIADA"`, redirigir a `/login`; si es `400/401`, mostrar error en formulario; si `retryable == true`, permitir reintento.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Actualización de `usuarios.password_hash` y `debe_cambiar_password` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` de transacción SQL |
| Fila en `dispositivos_conocidos` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` de transacción SQL |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/usuarios.py` (líneas 29-30), `Usuario.debe_cambiar_password` existe explícitamente con el comentario `# True hasta que el paciente cambia la contrasena inicial (escenario 20)`. | Low | Overview / STEP 2 / STEP 3 | Alineado 100% con el modelo SQLAlchemy. |
| RC-2 | En `.ai/1-Entrevista.md` (líneas 321-323), el cliente especifica que cuando el **paciente** ingresa por primera vez con la contraseña recibida por mail y la cambia, ya ingresa directamente al sistema sin pedirle además un código de verificación por máquina nueva en ese mismo acto. | Medium | STEP 3 | En `STEP 3` se registra automáticamente el `DispositivoConocido` actual al completar el cambio de contraseña inicial, evitando un doble bloqueo innecesario en el primer ingreso. |
| RC-3 | Los módulos `auth_router.py`, `auth_service.py` y `usuario_repo.py` aún no están creados en `app/src/`. | Medium | Actors | Especificados para su implementación bajo arquitectura `router` -> `service` -> `repo`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Cambio exitoso de contraseña inicial | `POST /api/v1/auth/cambiar-password-inicial` con `password_inicial` correcta y `nueva_password` válida | Retorna `200 OK`; `usuarios.debe_cambiar_password` pasa a `False`; `password_hash` cambia; se inserta `DispositivoConocido`; el **paciente** puede iniciar sesión luego con `nueva_password`. |
| `TC-02`: Nueva contraseña igual a la contraseña inicial | `POST /api/v1/auth/cambiar-password-inicial` donde `nueva_password == password_inicial` | Retorna `400 Bad Request` (`code: "PASSWORD_IGUAL_A_INICIAL"` o `"NUEVA_PASSWORD_INVALIDA"`); `debe_cambiar_password` sigue en `True`. |
| `TC-03`: Confirmación de contraseña no coincide | `nueva_password != confirmacion_password` | Retorna `400 Bad Request` (`code: "NUEVA_PASSWORD_INVALIDA"`). |
| `TC-04`: Contraseña inicial incorrecta | `password_inicial` no coincide con `usuarios.password_hash` | Retorna `401 Unauthorized` (`code: "PASSWORD_INICIAL_INCORRECTA"`); no modifica la base de datos. |
| `TC-05`: Intento de usar el flujo inicial cuando ya fue cambiada | Usuario con `debe_cambiar_password == False` invoca `POST /api/v1/auth/cambiar-password-inicial` | Retorna `409 Conflict` (`code: "PASSWORD_INICIAL_YA_CAMBIADA"`). |
| `TC-06`: Bloqueo de endpoints protegidos mientras `debe_cambiar_password == True` | El **paciente** intenta invocar `GET /api/v1/estudios` o `POST /api/v1/chatbot/consultas` antes de completar el Escenario 20 | El middleware/dependencia de autenticación rechaza la petición con `403 Forbidden` (`code: "DEBE_CAMBIAR_PASSWORD_INICIAL"`). |
| `TC-07`: Solicitudes concurrentes de cambio de contraseña inicial | Dos peticiones simultáneas para el mismo `usuario_id` | La primera actualiza a `debe_cambiar_password = False` (`200 OK`); la segunda recibe `409 Conflict` gracias al `SELECT ... FOR UPDATE`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Mientras `Usuario.debe_cambiar_password` sea `True`, el token emitido tras validar las credenciales iniciales solo autoriza llamar a `POST /api/v1/auth/cambiar-password-inicial` y `POST /api/v1/auth/logout`, bloqueando cualquier otra ruta. | `.ai/2-Glosario_LEL.md` (`Verbo: Cambiar contraseña inicial`) y `.ai/1-Entrevista.md` (línea 36) | Bajo: refuerza la obligatoriedad en backend además del frontend. |
| A2 | Al cambiar la contraseña inicial (que el **paciente** obtuvo desde su propio correo electrónico), el dispositivo actual queda registrado en `dispositivos_conocidos` para cumplir con la entrevista (líneas 321-323). | `.ai/1-Entrevista.md` (líneas 321-323) | Bajo. |

## Open Questions

- ¿Existe alguna política específica de complejidad de contraseñas (mayúsculas, caracteres especiales, historial) además de un mínimo de 8 caracteres alfanuméricos? *(Se adopta mínimo 8 caracteres con letras y números como estándar base configurable).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/usuarios.py` (`Usuario.debe_cambiar_password`, `DispositivoConocido`). | Aprobada para implementación. |
