# WORKFLOW: Escenario 26 – Verificar el ingreso desde una máquina nueva
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-26`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Paciente`, `Médico`, `Gerente médico`, `Administrativo`, `Bioinformático`, `Transportista`, `Admin general` |
| **Objetos** | `Código de verificación` |
| **Verbos** | `Iniciar sesión` |
| **Estados** | *(Transición de seguridad de acceso: `CodigoVerificacion.usado` pasa de `False` a `True` y se registra el equipo en `DispositivoConocido`)* |

---

## Overview

- **Objetivo**: Confirmar la identidad del usuario cuando intenta **iniciar sesión** desde una máquina que el sistema no conoce.
- **Contexto**: El usuario (de cualquiera de los 7 roles del sistema) ingresó su correo electrónico y su contraseña correctamente desde un dispositivo cuyo `identificador` no figura en la tabla `dispositivos_conocidos` para ese `usuario_id`.
- **Recursos**: Correo electrónico (`usuarios.email`), **código de verificación** (`codigos_verificacion`), dispositivo de acceso (`dispositivos_conocidos`).
- **Episodios**:
  1. El sistema detecta que el acceso se realiza desde una máquina nueva (no existe fila en `dispositivos_conocidos` con `(usuario_id, identificador)`).
  2. El sistema genera un **código de verificación** temporal, guarda su hash en `codigos_verificacion` (`codigo_hash`, `dispositivo_identificador`, `expira_en`, `usado = False`) y lo envía al correo electrónico del usuario.
  3. El usuario ingresa el **código de verificación** recibido en su correo electrónico.
  4. El sistema valida el **código de verificación** (vigencia, coincidencia de hash y de dispositivo, `usado == False`), marca `usado = True`, registra el dispositivo en `dispositivos_conocidos` y habilita el acceso emitiendo la sesión activa.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` / `Médico` / `Gerente médico` / `Administrativo` / `Bioinformático` / `Transportista` / `Admin general` (Sujetos LEL) | Usuario de cualquiera de los 7 roles (`Rol`) que se autentica desde un dispositivo nuevo y confirma su identidad con el **código de verificación**. |
| `auth_router` (`app/src/routers/`) | Capa `router`: gestiona el desafío de máquina nueva y expone el endpoint `POST /api/v1/auth/verificar-dispositivo` (y reenvío `POST /api/v1/auth/reenviar-codigo-dispositivo`). |
| `auth_service` (`app/src/services/`) | Capa `service`: detecta la ausencia de `DispositivoConocido`, genera el **código de verificación** de 6 dígitos, calcula su `codigo_hash`, fija su expiración (`expira_en`), solicita el envío por mail y luego verifica el código ingresado por el usuario. |
| `usuario_repo` (`app/src/repos/`) | Capa `repo`: consulta e inserta en `dispositivos_conocidos` y `codigos_verificacion` en `PostgreSQL`. |
| `notificacion_client` (`app/src/clients/`) | Capa `clients`: envía el correo electrónico con el **código de verificación** al `email` del usuario. |
| `PostgreSQL` | Almacena las tablas `usuarios`, `codigos_verificacion` y `dispositivos_conocidos`. |

---

## Prerequisites

- El usuario existe en la tabla `usuarios` y acaba de ingresar credenciales válidas (`email` y `password`) en el flujo de `Iniciar sesión` (Escenario 27).
- El usuario no tiene pendiente el cambio de contraseña inicial (`usuario.debe_cambiar_password == False`).
- No existe una fila en `dispositivos_conocidos` para `(usuario_id = usuario.id, identificador = hash(dispositivo_identificador))`.

---

## Trigger

- **Fase A (Emisión del desafío – Episodios 1 y 2)**: Disparada automáticamente durante `POST /api/v1/auth/login` cuando las credenciales son válidas pero el `dispositivo_identificador` no está en `dispositivos_conocidos`.
- **Fase B (Confirmación del código – Episodios 3 y 4)**: El usuario ingresa el **código de verificación** y envía `POST /api/v1/auth/verificar-dispositivo`.

---

## Workflow Tree

### STEP 1: Detección de máquina nueva y generación de `CodigoVerificacion`
**Actor**: `auth_service` -> `usuario_repo` -> `PostgreSQL`
**Action**:
1. Comprueba en `dispositivos_conocidos` que no existe el par `(usuario_id, identificador_hash)`.
2. Invalida cualquier código previo no utilizado para el mismo `(usuario_id, dispositivo_identificador)` marcando `usado = True`.
3. Genera un **código de verificación** numérico criptográficamente aleatorio de 6 dígitos (ej. `"482910"`), calcula su `codigo_hash` y define `expira_en = now() + 10 minutos`.
4. Inserta en `codigos_verificacion` una fila con `usuario_id`, `codigo_hash`, `dispositivo_identificador = identificador_hash`, `expira_en` y `usado = False`.
**Timeout**: `3s`
**Input**: `{ usuario_id: int, email: str, dispositivo_identificador: str }`
**Output on SUCCESS**: `{ codigo_verificacion_id: int, codigo_plano: str, expira_en: datetime }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(database_error)` / `FAILURE(timeout)`: Error al escribir en `codigos_verificacion` -> `ABORT_CLEANUP` (`ROLLBACK`) -> retorna `503 Service Unavailable` (`code: "ERROR_GENERACION_CODIGO"`, `retryable: true`).

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: "Detectamos un ingreso desde un dispositivo nuevo. Enviando código de verificación a su correo...".
  - Operator sees: Nueva fila en `codigos_verificacion` con `usado = false`.
  - Database: `codigos_verificacion` contiene 1 código vigente (`usado = false`, `expira_en > now()`); `dispositivos_conocidos` aún no contiene el dispositivo.
  - Logs: `[auth_service] step_1_maquina_nueva_detectada usuario_id=<id> codigo_id=<id>`

---

### STEP 2: Envío del `Código de verificación` por correo electrónico
**Actor**: `auth_service` -> `notificacion_client`
**Action**:
1. Envía un correo electrónico a `usuario.email` con el **código de verificación** en texto plano y su tiempo de validez (10 minutos).
2. Emite un token temporal de desafío (`challenge_token` con `scope = "verificar_dispositivo"`) y responde al frontend indicando `requiere_verificacion_dispositivo: true` para que muestre el formulario de ingreso del código.
**Timeout**: `6s` (con 2 reintentos y backoff de `1s`, `2s`)
**Input**: `{ usuario_id: int, email: str, codigo_plano: str, expira_en: datetime }`
**Output on SUCCESS**: `{ requiere_verificacion_dispositivo: true, challenge_token: str, expira_en: datetime }` -> Espera el input del usuario en STEP 3.
**Output on FAILURE**:
  - `FAILURE(transient_external_error)`: El servicio de correo falla tras 2 reintentos -> ejecuta `ABORT_CLEANUP` (invalida el `CodigoVerificacion` recién creado) y retorna `503 Service Unavailable` (`code: "ERROR_ENVIO_CODIGO_MAIL"`, `retryable: true`).

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Pantalla "Verificar dispositivo nuevo: ingrese el código de 6 dígitos enviado a su correo electrónico" y recibe el mail en su bandeja de entrada.
  - Operator sees: Correo despachado por `notificacion_client`; sesión aún no habilitada para rutas protegidas.
  - Database: `codigos_verificacion.usado = false`.
  - Logs: `[notificacion_client] step_2_codigo_verificacion_enviado usuario_id=<id> codigo_id=<id>`

---

### STEP 3: Recepción y validación del `Código de verificación` ingresado por el usuario
**Actor**: `auth_router` -> `auth_service` -> `usuario_repo` -> `PostgreSQL`
**Action**:
1. El usuario envía `POST /api/v1/auth/verificar-dispositivo` con el `challenge_token`, el `codigo` de 6 dígitos y el `dispositivo_identificador`.
2. Obtiene la fila en `codigos_verificacion` para `(usuario_id, dispositivo_identificador)` con `SELECT ... FOR UPDATE`.
3. Verifica:
   - Que exista el registro en `codigos_verificacion`.
   - Que `codigo_verificacion.usado == False`.
   - Que `codigo_verificacion.expira_en >= now()`.
   - Que el hash de `codigo` coincida exactamente con `codigo_verificacion.codigo_hash` (comparación en tiempo constante).
**Timeout**: `3s`
**Input**: `{ challenge_token: str, codigo: str, dispositivo_identificador: str }`
**Output on SUCCESS**: `CodigoVerificacion` válido y bloqueado en transacción -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(validation_error)`: Formato de `codigo` inválido (no tiene 6 dígitos) -> retorna `400 Bad Request` (`code: "FORMATO_CODIGO_INVALIDO"`).
  - `FAILURE(invalid_state_usado)`: `codigo_verificacion.usado == True` -> retorna `409 Conflict` (`code: "CODIGO_YA_UTILIZADO"`).
  - `FAILURE(expired)`: `codigo_verificacion.expira_en < now()` -> marca `usado = True` y retorna `410 Gone` (`code: "CODIGO_EXPIRADO"`), indicando solicitar un nuevo código.
  - `FAILURE(unauthorized)`: `codigo` no coincide con `codigo_hash` o `dispositivo_identificador` no coincide -> retorna `401 Unauthorized` (`code: "CODIGO_VERIFICACION_INCORRECTO"`).

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Spinner "Verificando código...".
  - Operator sees: Validación de `codigos_verificacion` en curso.
  - Database: Lectura con lock (`FOR UPDATE`) sobre `codigos_verificacion`.
  - Logs: `[auth_service] step_3_validar_codigo_verificacion usuario_id=<id> codigo_id=<id>`

---

### STEP 4: Consumo del código, registro en `DispositivoConocido` y habilitación del acceso
**Actor**: `auth_service` -> `usuario_repo` -> `PostgreSQL`
**Action**:
1. Actualiza `codigos_verificacion.usado = True`.
2. Inserta en `dispositivos_conocidos` una nueva fila con `usuario_id`, `identificador = identificador_hash`, `ultimo_acceso = func.now()` (respetando `UniqueConstraint("usuario_id", "identificador")` mediante upsert si ya existiese).
3. Realiza `COMMIT` de la transacción.
4. Genera y devuelve el token/cookie de sesión activa completa según el `rol` del usuario.
**Timeout**: `3s`
**Input**: `{ usuario_id: int, codigo_verificacion_id: int, identificador_hash: str }`
**Output on SUCCESS**: `{ usuario_id: int, rol: str, dispositivo_verificado: true, access_token: str }` -> Retorna `200 OK` y habilita el ingreso al sistema.
**Output on FAILURE**:
  - `FAILURE(conflict)`: Doble clic concurrente en "Verificar" -> la primera petición completa `STEP 4` y la segunda recibe `409 Conflict` (`CODIGO_YA_UTILIZADO`) en `STEP 3`.
  - `FAILURE(database_error)` / `FAILURE(timeout)`: Error al insertar en `dispositivos_conocidos` -> ejecuta `ABORT_CLEANUP` (`ROLLBACK` para que `codigos_verificacion.usado` vuelva a `False` y el usuario pueda reintentar con el mismo código) -> retorna `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Acceso habilitado y redirección al panel principal correspondiente a su rol.
  - Operator sees: Dispositivo registrado en `dispositivos_conocidos` y sesión iniciada.
  - Database:
    - `codigos_verificacion`: `usado = true`.
    - `dispositivos_conocidos`: nueva fila `(usuario_id, identificador, ultimo_acceso = now())`.
  - Logs: `[auth_service] step_4_dispositivo_verificado_acceso_habilitado usuario_id=<id> rol=<rol>`

---

### ABORT_CLEANUP: Limpieza ante fallo en envío de correo o fallo al registrar dispositivo
**Triggered by**:
- Fallo de envío de correo en `STEP 2`: invalida/elimina la fila creada en `codigos_verificacion` en `STEP 1`.
- Fallo de base de datos en `STEP 4`: ejecuta `ROLLBACK` para mantener `codigos_verificacion.usado = False` y no dejar un código consumido sin haber registrado el `DispositivoConocido`.
**Actions** (in order):
  1. Si el fallo ocurrió en `STEP 2`, actualizar `codigos_verificacion.usado = True` (o `DELETE FROM codigos_verificacion WHERE id = :id`) y hacer `COMMIT`.
  2. Si el fallo ocurrió en `STEP 4`, ejecutar `ROLLBACK` de la transacción activa.
  3. Registrar alerta en los logs de seguridad.
**What customer (Usuario) sees**: Mensaje de error claro con opción de reenviar el código (si falló `STEP 2`) o reintentar la validación (si falló `STEP 4`).
**What operator sees**: Sin dispositivos registrados sin verificar ni códigos colgados tras fallo de correo.

---

## State Transitions

```
[Dispositivo no registrado + Credenciales válidas]
   -> (STEP 1-2: máquina nueva detectada y mail enviado)
   -> [CodigoVerificacion(usado=False, expira_en > now()) + Sesión en espera de verificación]

[CodigoVerificacion(usado=False, expira_en > now())]
   -> (STEP 3-4: usuario ingresa código correcto a tiempo)
   -> [CodigoVerificacion(usado=True) + DispositivoConocido creado + Sesión activa habilitada]

[CodigoVerificacion(usado=False)]
   -> (El reloj supera expira_en)
   -> [CodigoVerificacion expirado (410 Gone) -> requiere nuevo código]
```

---

## Handoff Contracts

### 1. Frontend (Usuario) -> Backend (`auth_router`) – Confirmar código de verificación
**Endpoint**: `POST /api/v1/auth/verificar-dispositivo`
**Headers**: `Authorization: Bearer <challenge_token>`
**Payload**:
```json
{
  "codigo": "482910",
  "dispositivo_identificador": "fp_sha256_nuevo_equipo_casa_09"
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "usuario_id": 64,
    "email": "martin.gomez@hospital.org.ar",
    "rol": "medico",
    "dispositivo_verificado": true,
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
    "redirect_to": "/medico/dashboard"
  }
}
```
**Failure response** (`400` / `401` / `409` / `410` / `503`):
```json
{
  "ok": false,
  "error": "El código de verificación ingresado es incorrecto.",
  "code": "CODIGO_VERIFICACION_INCORRECTO",
  "retryable": false
}
```
**Timeout**: `5s`

### 2. `auth_service` -> `notificacion_client` (Servicio de Correo)
**Endpoint**: `POST /internal/mail/send`
**Payload**:
```json
{
  "to": "martin.gomez@hospital.org.ar",
  "subject": "Código de verificación por ingreso desde un equipo nuevo",
  "template": "verificacion_maquina_nueva",
  "variables": {
    "nombre_completo": "Martín Gómez",
    "codigo_verificacion": "482910",
    "minutos_expiracion": 10
  }
}
```
**Success response**:
```json
{
  "ok": true,
  "message_id": "msg-20261028-2fa-0091"
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "SMTP connection refused",
  "code": "MAIL_DELIVERY_FAILED",
  "retryable": true
}
```
**Timeout**: `6s`
**ON FAILURE**: Reintentar hasta 2 veces con backoff (`1s`, `2s`); si falla, ejecutar `ABORT_CLEANUP` invalidando el código en BD.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Fila en `codigos_verificacion` (`usado = False`) | Step 1 | `ABORT_CLEANUP` (si falla envío de mail en Step 2) | `DELETE` o `UPDATE codigos_verificacion SET usado = true` |
| Actualización `codigos_verificacion.usado = True` y fila en `dispositivos_conocidos` | Step 4 | `ABORT_CLEANUP` (si falla commit en Step 4) | `ROLLBACK` de la transacción SQL |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/usuarios.py` (líneas 40-64), los modelos `DispositivoConocido` (`usuario_id`, `identificador`, `ultimo_acceso`, `UniqueConstraint("usuario_id", "identificador")`) y `CodigoVerificacion` (`usuario_id`, `codigo_hash`, `dispositivo_identificador`, `expira_en`, `usado`) existen con las columnas exactas necesarias para este escenario. | Low | Todo el documento | Alineado 100% con los nombres de tablas y columnas de `app/src/core/models/usuarios.py`. |
| RC-2 | En `CodigoVerificacion`, se guarda `codigo_hash` (nunca el código en texto plano) y `dispositivo_identificador` para atar el código al dispositivo específico que disparó el desafío. | Medium | STEP 1 / STEP 3 | En `STEP 3` se valida tanto `codigo_hash` como `dispositivo_identificador`, evitando que un código generado para un dispositivo sea canjeado desde otro distinto. |
| RC-3 | No existen aún `auth_router.py`, `auth_service.py`, `usuario_repo.py` ni `notificacion_client.py`. | Medium | Actors | Especificados para su implementación en el flujo SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Ingreso desde máquina nueva y verificación exitosa con código | Login desde `dispositivo_identificador` no registrado -> envío de mail -> `POST /api/v1/auth/verificar-dispositivo` con código válido | Retorna `200 OK` con `access_token`; `codigos_verificacion.usado` pasa a `True`; se crea fila en `dispositivos_conocidos`. |
| `TC-02`: Código de verificación incorrecto | `POST /api/v1/auth/verificar-dispositivo` con un código de 6 dígitos que no coincide con `codigo_hash` | Retorna `401 Unauthorized` (`code: "CODIGO_VERIFICACION_INCORRECTO"`); `usado` sigue en `False` y no se crea `DispositivoConocido`. |
| `TC-03`: Código de verificación expirado | `POST /api/v1/auth/verificar-dispositivo` cuando `now() > codigos_verificacion.expira_en` | Retorna `410 Gone` (`code: "CODIGO_EXPIRADO"`); no habilita el acceso. |
| `TC-04`: Reutilización de un código ya usado | `POST /api/v1/auth/verificar-dispositivo` con un código que ya tiene `usado = True` | Retorna `409 Conflict` (`code: "CODIGO_YA_UTILIZADO"`). |
| `TC-05`: Intento de canjear el código desde un `dispositivo_identificador` distinto al que lo originó | `POST /api/v1/auth/verificar-dispositivo` cambiando `dispositivo_identificador` | Retorna `401 Unauthorized` (`code: "CODIGO_VERIFICACION_INCORRECTO"`). |
| `TC-06`: Bloqueo de rutas protegidas con el `challenge_token` antes de verificar el código | El usuario intenta llamar a una ruta de negocio usando el `challenge_token` sin haber completado `STEP 4` | El middleware rechaza la petición con `403 Forbidden` (`code: "DISPOSITIVO_NO_VERIFICADO"`). |
| `TC-07`: Fallo del servicio de correo al enviar el código | `notificacion_client` falla en los 3 intentos durante `STEP 2` | `ABORT_CLEANUP` invalida el registro en `codigos_verificacion` y retorna `503 Service Unavailable`. |
| `TC-08`: Aplicación transversal a los 7 roles del LEL | Prueba parametrizada con usuarios de cada uno de los 7 valores de `Rol` (`PACIENTE`, `MEDICO`, `GERENTE_MEDICO`, `ADMINISTRATIVO`, `BIOINFORMATICO`, `TRANSPORTISTA`, `ADMIN_GENERAL`) | Todos requieren y completan la verificación al ingresar desde una máquina nueva. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El tiempo de expiración (`expira_en`) de cada `CodigoVerificacion` es de 10 minutos (configurable por variable de entorno `VERIFICATION_CODE_TTL_MINUTES = 10`). | `app/src/core/models/usuarios.py` (`CodigoVerificacion.expira_en`) | Bajo. |
| A2 | El identificador del dispositivo (`dispositivo_identificador`) se obtiene a partir de una cookie firmada/huella del cliente y se almacena hasheado en `dispositivos_conocidos.identificador` y `codigos_verificacion.dispositivo_identificador`. | `app/src/core/models/usuarios.py` (línea 47: `# hash de huella / cookie de dispositivo`) | Bajo. |

## Open Questions

- Ninguna. El modelo de datos en `app/src/core/models/usuarios.py` ya contempla exactamente `DispositivoConocido` y `CodigoVerificacion`.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/usuarios.py` (`DispositivoConocido`, `CodigoVerificacion`, `Usuario`). | Aprobada para implementación. |
