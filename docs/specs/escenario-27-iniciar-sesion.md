# WORKFLOW: Escenario 27 – Iniciar sesión
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-27`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Paciente`, `Médico`, `Gerente médico`, `Administrativo`, `Bioinformático`, `Transportista`, `Admin general` |
| **Objetos** | `Código de verificación` |
| **Verbos** | `Iniciar sesión`, `Cambiar contraseña inicial` |
| **Estados** | *(Evalúa `Usuario.debe_cambiar_password`, `DispositivoConocido` y habilita sesión activa o deriva a los Escenarios 20 / 26)* |

---

## Overview

- **Objetivo**: Permitir que un usuario registrado acceda de forma segura al sistema según su rol.
- **Contexto**: El usuario (de cualquiera de los 7 sujetos del LEL) cuenta con credenciales (`email` y `password`) y necesita ingresar al sistema.
- **Recursos**: Correo electrónico (`usuarios.email`), contraseña (`usuarios.password_hash`), contraseña inicial (`usuarios.debe_cambiar_password`), **código de verificación** (`codigos_verificacion`), dispositivo de acceso (`dispositivos_conocidos`).
- **Episodios**:
  1. El usuario ingresa su correo electrónico y su contraseña.
  2. El sistema valida las credenciales contra la tabla `usuarios`.
  3. El sistema solicita cambiar la contraseña cuando es el primer ingreso (`usuario.debe_cambiar_password == True`, derivando al Escenario 20).
  4. Si no es el primer ingreso, el sistema verifica si el acceso se realiza desde una máquina conocida (`dispositivos_conocidos`):
     - Si es una máquina conocida, actualiza `dispositivos_conocidos.ultimo_acceso` y pasa al episodio 5.
     - Si es una máquina nueva, deriva al flujo de verificación por **código de verificación** (Escenario 26).
  5. El sistema habilita el acceso al usuario emitiendo su sesión autenticada con su `Rol`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` / `Médico` / `Gerente médico` / `Administrativo` / `Bioinformático` / `Transportista` / `Admin general` (Sujetos LEL) | Usuario registrado que ingresa su correo electrónico y contraseña para acceder al sistema. |
| `auth_router` (`app/src/routers/`) | Capa `router`: recibe las credenciales en `POST /api/v1/auth/login`, extrae el identificador de dispositivo y devuelve el resultado de autenticación o el desafío requerido. |
| `auth_service` (`app/src/services/`) | Capa `service`: verifica credenciales en tiempo constante, evalúa el árbol de decisión (`debe_cambiar_password` -> `DispositivoConocido` -> sesión activa) y coordina la emisión de tokens o desafíos. |
| `usuario_repo` (`app/src/repos/`) | Capa `repo`: busca al `Usuario` por `email`, consulta/actualiza `DispositivoConocido` y crea `CodigoVerificacion` cuando corresponde. |
| `notificacion_client` (`app/src/clients/`) | Capa `clients`: envía por correo el **código de verificación** si durante el login se detecta una máquina nueva. |
| `PostgreSQL` | Almacena `usuarios`, `dispositivos_conocidos` y `codigos_verificacion`. |

---

## Prerequisites

- El usuario se encuentra registrado en la tabla `usuarios` con un `email`, `password_hash` y `rol` válidos (`Rol.PACIENTE`, `Rol.MEDICO`, `Rol.GERENTE_MEDICO`, `Rol.ADMINISTRATIVO`, `Rol.BIOINFORMATICO`, `Rol.TRANSPORTISTA` o `Rol.ADMIN_GENERAL`).
- El cliente web envía junto con las credenciales el identificador de dispositivo (`dispositivo_identificador`).

---

## Trigger

El usuario completa su correo electrónico y contraseña en la pantalla de ingreso y presiona "Iniciar sesión".
- **Endpoint HTTP**: `POST /api/v1/auth/login`

---

## Workflow Tree

### STEP 1: Validación de formato de entrada (`email`, `password`, `dispositivo_identificador`)
**Actor**: `auth_router` -> `auth_service`
**Action**:
1. Verifica que `email`, `password` y `dispositivo_identificador` estén presentes y no sean cadenas vacías.
2. Normaliza `email` a minúsculas (`email.strip().lower()`) y calcula `identificador_hash = sha256(dispositivo_identificador)`.
**Timeout**: `1s`
**Input**: `{ email: str, password: str, dispositivo_identificador: str }`
**Output on SUCCESS**: `{ email_normalizado: str, password: str, identificador_hash: str }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(validation_error)`: Falta `email`, `password` o `dispositivo_identificador`, o el formato de correo es inválido -> retorna `400 Bad Request` (`code: "DATOS_LOGIN_INVALIDOS"`).

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Botón "Iniciando sesión..." deshabilitado mientras se procesa la solicitud.
  - Operator sees: Petición `POST /api/v1/auth/login` recibida.
  - Database: Sin lecturas ni escrituras aún.
  - Logs: `[auth_service] step_1_login_intento email=<email>`

---

### STEP 2: Validación criptográfica de credenciales contra `usuarios`
**Actor**: `auth_service` -> `usuario_repo` -> `PostgreSQL`
**Action**:
1. Busca en la tabla `usuarios` la fila con `usuarios.email == email_normalizado`.
2. Si el usuario no existe, ejecuta igualmente un cálculo de hash ficticio (dummy hash verification) para prevenir enumeración de usuarios por diferencia de tiempos y falla con error genérico de credenciales.
3. Si el usuario existe, verifica que `password` coincida con `usuario.password_hash`.
**Timeout**: `3s`
**Input**: `{ email_normalizado: str, password: str }`
**Output on SUCCESS**: Instancia `Usuario` autenticada -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Correo inexistente o contraseña incorrecta -> retorna `401 Unauthorized` (`code: "CREDENCIALES_INVALIDAS"`, mensaje genérico: `"Correo electrónico o contraseña incorrectos"`).
  - `FAILURE(timeout)`: Consulta a `PostgreSQL` > `3s` -> retorna `503 Service Unavailable` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Indicador de verificación de credenciales.
  - Operator sees: Lectura en `usuarios` por índice `ix_usuarios_email`.
  - Database: Solo lectura en `usuarios`.
  - Logs: `[auth_service] step_2_credenciales_validadas usuario_id=<id> rol=<rol>`

---

### STEP 3: Evaluación de primer ingreso (`Usuario.debe_cambiar_password`)
**Actor**: `auth_service`
**Action**:
1. Evalúa el flag `usuario.debe_cambiar_password`.
2. **Rama 3A (Primer ingreso del paciente: `usuario.debe_cambiar_password == True`)**:
   - Emite un token temporal restringido exclusivamente al cambio de contraseña inicial (`scope = "cambio_password_inicial"`, TTL `15m`).
   - Retorna `200 OK` con `estado_login = "REQUIERE_CAMBIO_PASSWORD_INICIAL"` y `requiere_cambio_password = true`, redirigiendo al usuario al **Escenario 20** (`Cambiar la contraseña inicial`) sin otorgar aún acceso a las pantallas protegidas.
3. **Rama 3B (`usuario.debe_cambiar_password == False`)**:
   - Continúa a la verificación de máquina conocida -> GO TO STEP 4.
**Timeout**: `1s`
**Input**: `{ usuario: Usuario, identificador_hash: str }`
**Output on SUCCESS**:
  - Si `debe_cambiar_password == True`: Respuesta de redirección a cambio de contraseña inicial (Fin del flujo de login inicial; continúa en Escenario 20).
  - Si `debe_cambiar_password == False`: GO TO STEP 4.
**Output on FAILURE**: *(Paso en memoria sin fallo externo).*

**Observable states during this step**:
  - Customer/Actor (`Paciente` en primer ingreso) sees: Redirección inmediata a la pantalla "Por seguridad, debe cambiar su contraseña inicial antes de continuar".
  - Operator sees: Token de alcance restringido emitido (`scope = cambio_password_inicial`).
  - Database: `usuarios.debe_cambiar_password` permanece en `true` hasta que complete el Escenario 20.
  - Logs: `[auth_service] step_3_evaluar_primer_ingreso usuario_id=<id> debe_cambiar_password=<bool>`

---

### STEP 4: Verificación de dispositivo de acceso (`DispositivoConocido` vs máquina nueva)
**Actor**: `auth_service` -> `usuario_repo` (+ `notificacion_client` si es máquina nueva) -> `PostgreSQL`
**Action**:
1. Consulta la tabla `dispositivos_conocidos` buscando `(usuario_id = usuario.id, identificador = identificador_hash)`.
2. **Rama 4A (Máquina conocida: existe fila en `dispositivos_conocidos`)**:
   - Actualiza `dispositivos_conocidos.ultimo_acceso = func.now()` y ejecuta `COMMIT`.
   - Continúa a habilitar el acceso -> GO TO STEP 5.
3. **Rama 4B (Máquina nueva: no existe fila en `dispositivos_conocidos`)**:
   - Genera un `CodigoVerificacion` en `codigos_verificacion` (`usado = False`, `expira_en = now() + 10m`), lo envía por mail mediante `notificacion_client` y retorna `200 OK` con `estado_login = "REQUIERE_VERIFICACION_DISPOSITIVO"`, `requiere_verificacion_dispositivo = true` y `challenge_token`, derivando al **Escenario 26** (`Verificar el ingreso desde una máquina nueva`).
**Timeout**: `6s`
**Input**: `{ usuario: Usuario, identificador_hash: str }`
**Output on SUCCESS**:
  - Si es máquina conocida: `DispositivoConocido.ultimo_acceso` actualizado -> GO TO STEP 5.
  - Si es máquina nueva: Desafío enviado por mail y respuesta de redirección al Escenario 26.
**Output on FAILURE**:
  - `FAILURE(transient_external_error)`: Es máquina nueva pero falla el envío del correo en `notificacion_client` tras 2 reintentos -> ejecuta `ABORT_CLEANUP` (invalida el `CodigoVerificacion`) -> retorna `503 Service Unavailable` (`code: "ERROR_ENVIO_CODIGO_MAIL"`, `retryable: true`).
  - `FAILURE(database_error)`: Error de escritura en `PostgreSQL` -> `ABORT_CLEANUP` (`ROLLBACK`) -> retorna `503 Service Unavailable`.

**Observable states during this step**:
  - Customer/Actor (Usuario en máquina conocida) sees: Redirección directa al panel principal.
  - Customer/Actor (Usuario en máquina nueva) sees: Pantalla para ingresar el **código de verificación** enviado a su correo.
  - Operator sees: Actualización de `ultimo_acceso` en `dispositivos_conocidos` (Rama 4A) o creación de `codigos_verificacion` (Rama 4B).
  - Database: `dispositivos_conocidos.ultimo_acceso = now()` (Rama 4A) o nueva fila en `codigos_verificacion` (Rama 4B).
  - Logs: `[auth_service] step_4_verificar_dispositivo usuario_id=<id> dispositivo_conocido=<bool>`

---

### STEP 5: Emisión de sesión autenticada y habilitación del acceso al sistema
**Actor**: `auth_service` -> `auth_router`
**Action**:
1. Genera el token/sesión de acceso completo (`access_token` con `sub = usuario.id`, `rol = usuario.rol.value`, `jti` único y fecha de expiración).
2. Retorna `200 OK` con `estado_login = "ACCESO_HABILITADO"`, los datos básicos del usuario (`id`, `nombre`, `apellido`, `email`, `rol`) y la ruta de inicio correspondiente a su rol.
**Timeout**: `1s`
**Input**: `{ usuario: Usuario }`
**Output on SUCCESS**: `{ estado_login: "ACCESO_HABILITADO", access_token: str, usuario: dict }` -> Retorna `200 OK`.
**Output on FAILURE**: *(Sin fallos externos; si falla la firma por configuración inválida, retorna `500 Internal Server Error`).*

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Panel principal del sistema cargado según su rol (`Paciente`, `Médico`, `Gerente médico`, `Administrativo`, `Bioinformático`, `Transportista` o `Admin general`).
  - Operator sees: Sesión activa emitida.
  - Database: `dispositivos_conocidos.ultimo_acceso` actualizado al instante actual.
  - Logs: `[auth_service] step_5_acceso_habilitado usuario_id=<id> rol=<rol>`

---

### ABORT_CLEANUP: Reversión ante fallo en actualización de acceso o envío de código
**Triggered by**: Fallo de base de datos o fallo de envío de correo en `STEP 4`.
**Actions** (in order):
  1. Ejecutar `ROLLBACK` de cualquier cambio pendiente en `dispositivos_conocidos` o `codigos_verificacion`.
  2. Si se había insertado un `CodigoVerificacion` y falló el envío del correo tras los reintentos, marcarlo como `usado = True` o eliminarlo.
  3. No emitir `access_token`.
**What customer (Usuario) sees**: Mensaje de error temporal ("No se pudo completar el inicio de sesión en este momento. Por favor, intente nuevamente.") permaneciendo en la pantalla de ingreso.
**What operator sees**: Transacción revertida sin sesiones a medio abrir.

---

## State Transitions

```
[Sin sesión]
   -> (Credenciales inválidas en STEP 2)
   -> [Sin sesión (401 Unauthorized)]

[Sin sesión + Usuario(debe_cambiar_password=True)]
   -> (Credenciales válidas en STEP 2-3)
   -> [Sesión restringida de primer ingreso (deriva a Escenario 20: Cambiar la contraseña inicial)]

[Sin sesión + Usuario(debe_cambiar_password=False) + Dispositivo NO en dispositivos_conocidos]
   -> (Credenciales válidas en STEP 2-4)
   -> [Desafío CodigoVerificacion activo (deriva a Escenario 26: Verificar el ingreso desde una máquina nueva)]

[Sin sesión + Usuario(debe_cambiar_password=False) + Dispositivo SÍ en dispositivos_conocidos]
   -> (Credenciales válidas en STEP 2-5)
   -> [Sesión activa habilitada + dispositivos_conocidos.ultimo_acceso actualizado]
```

---

## Handoff Contracts

### Frontend (Usuario) -> Backend (`auth_router`)
**Endpoint**: `POST /api/v1/auth/login`
**Payload**:
```json
{
  "email": "martin.gomez@hospital.org.ar",
  "password": "DrGomez2026!Secure",
  "dispositivo_identificador": "fp_sha256_medico_workstation_01"
}
```
**Success response – Caso 1: Máquina conocida y sin cambio de contraseña pendiente** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "estado_login": "ACCESO_HABILITADO",
    "requiere_cambio_password": false,
    "requiere_verificacion_dispositivo": false,
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
    "usuario": {
      "id": 64,
      "nombre": "Martín",
      "apellido": "Gómez",
      "email": "martin.gomez@hospital.org.ar",
      "rol": "medico"
    },
    "redirect_to": "/medico/dashboard"
  }
}
```
**Success response – Caso 2: Primer ingreso del paciente (`debe_cambiar_password = true`)** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "estado_login": "REQUIERE_CAMBIO_PASSWORD_INICIAL",
    "requiere_cambio_password": true,
    "requiere_verificacion_dispositivo": false,
    "primer_ingreso_token": "eyJhbGciOiJIUzI1NiIsInNjb3BlIjoiY2FtYmlvX3Bhc3N3b3JkX2luaWNpYWwi...",
    "redirect_to": "/cambiar-password-inicial"
  }
}
```
**Success response – Caso 3: Máquina nueva (`DispositivoConocido` no encontrado)** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "estado_login": "REQUIERE_VERIFICACION_DISPOSITIVO",
    "requiere_cambio_password": false,
    "requiere_verificacion_dispositivo": true,
    "challenge_token": "eyJhbGciOiJIUzI1NiIsInNjb3BlIjoidmVyaWZpY2FyX2Rpc3Bvc2l0aXZvIi...",
    "expira_en": "2026-10-28T20:05:42Z",
    "redirect_to": "/verificar-dispositivo"
  }
}
```
**Failure response** (`400` / `401` / `503`):
```json
{
  "ok": false,
  "error": "Correo electrónico o contraseña incorrectos.",
  "code": "CREDENCIALES_INVALIDAS",
  "retryable": false
}
```
**Timeout**: `8s`

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Actualización de `dispositivos_conocidos.ultimo_acceso` | Step 4 (Rama 4A) | `ABORT_CLEANUP` | `ROLLBACK` transaccional |
| Fila en `codigos_verificacion` | Step 4 (Rama 4B) | `ABORT_CLEANUP` (si falla envío de mail) | `DELETE` o `UPDATE usado = true` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/usuarios.py`, el modelo `Usuario` posee `debe_cambiar_password` y relaciones directas con `dispositivos` (`DispositivoConocido`) y `codigos_verificacion` (`CodigoVerificacion`). | Low | STEP 3 / STEP 4 | El flujo de `Iniciar sesión` integra de forma exacta las tres entidades tal como lo requiere el Escenario 27 (`.ai/3-Escenarios.md` líneas 458-475). |
| RC-2 | En `app/src/core/models/enums.py` (líneas 5-12), los 7 roles del LEL están modelados en `Rol`: `PACIENTE`, `MEDICO`, `GERENTE_MEDICO`, `ADMINISTRATIVO`, `BIOINFORMATICO`, `TRANSPORTISTA`, `ADMIN_GENERAL`. | Low | Actors / STEP 5 | Todos los sujetos usan el mismo endpoint unificado `POST /api/v1/auth/login`. |
| RC-3 | No existen aún `auth_router.py`, `auth_service.py` ni `usuario_repo.py`. | Medium | Actors | Especificados para su implementación en el flujo SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Inicio de sesión desde máquina conocida | `POST /api/v1/auth/login` con credenciales válidas, `debe_cambiar_password=False` y dispositivo existente en `dispositivos_conocidos` | Retorna `200 OK` con `estado_login: "ACCESO_HABILITADO"`, `access_token` válido y actualiza `dispositivos_conocidos.ultimo_acceso`. |
| `TC-02`: Inicio de sesión en primer ingreso de paciente (`debe_cambiar_password=True`) | `POST /api/v1/auth/login` por un `Paciente` recién creado que aún no cambió su contraseña inicial | Retorna `200 OK` con `estado_login: "REQUIERE_CAMBIO_PASSWORD_INICIAL"` y `primer_ingreso_token` restringido; no emite `access_token` general. |
| `TC-03`: Inicio de sesión desde máquina nueva (`DispositivoConocido` inexistente) | `POST /api/v1/auth/login` con credenciales válidas, `debe_cambiar_password=False` y `dispositivo_identificador` nuevo | Crea fila en `codigos_verificacion`, envía email y retorna `200 OK` con `estado_login: "REQUIERE_VERIFICACION_DISPOSITIVO"` y `challenge_token`. |
| `TC-04`: Contraseña incorrecta | `POST /api/v1/auth/login` con `email` válido y `password` errónea | Retorna `401 Unauthorized` (`code: "CREDENCIALES_INVALIDAS"`). |
| `TC-05`: Correo electrónico inexistente | `POST /api/v1/auth/login` con un `email` que no existe en `usuarios` | Retorna exactamente el mismo `401 Unauthorized` (`code: "CREDENCIALES_INVALIDAS"`) sin revelar si el correo existe. |
| `TC-06`: Campos vacíos o faltantes | `POST /api/v1/auth/login` sin `password` o sin `dispositivo_identificador` | Retorna `400 Bad Request` (`code: "DATOS_LOGIN_INVALIDOS"`). |
| `TC-07`: Autenticación exitosa para los 7 roles del sistema | Prueba parametrizada de `POST /api/v1/auth/login` para los 7 valores de `Rol` | Retorna `200 OK` con el `rol` y `redirect_to` correspondientes a cada sujeto del LEL. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | La prioridad de evaluación tras validar credenciales es: primero verificar `debe_cambiar_password` (Episodio 3) y luego verificar máquina conocida/nueva (Episodio 4), tal como está numerado en `.ai/3-Escenarios.md` (líneas 468-475) y explicado en `.ai/1-Entrevista.md` (líneas 321-323). | `.ai/3-Escenarios.md` y `.ai/1-Entrevista.md` | Bajo. |

## Open Questions

- Ninguna. El flujo completo de `Iniciar sesión` y sus puntos de bifurcación hacia los Escenarios 20 y 26 están completamente definidos en el LEL y en los modelos.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/usuarios.py` (`Usuario`, `DispositivoConocido`, `CodigoVerificacion`) y `enums.py` (`Rol`). | Aprobada para implementación. |
