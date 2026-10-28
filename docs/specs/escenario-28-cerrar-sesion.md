# WORKFLOW: Escenario 28 – Cerrar sesión
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-28`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Paciente`, `Médico`, `Gerente médico`, `Administrativo`, `Bioinformático`, `Transportista`, `Admin general` |
| **Objetos** | *(Sesión activa, dispositivo de acceso)* |
| **Verbos** | `Cerrar sesión`, `Iniciar sesión` |
| **Estados** | *(Transición de sesión: de `Sesión activa` a `Sesión finalizada / revocada`, conservando el `DispositivoConocido`)* |

---

## Overview

- **Objetivo**: Permitir que un usuario finalice su sesión de forma segura para que nadie más pueda usar su cuenta desde ese equipo.
- **Contexto**: El usuario (de cualquiera de los 7 roles del sistema) inició sesión previamente y quiere terminar de usar el sistema, por ejemplo al retirarse de un equipo compartido.
- **Recursos**: Sesión activa (token de acceso / cookie de sesión), dispositivo de acceso (`dispositivos_conocidos`).
- **Episodios**:
  1. El usuario solicita **cerrar sesión**.
  2. El sistema finaliza e invalida la sesión activa en el servidor y limpia las credenciales de sesión del cliente.
  3. El sistema redirige al usuario a la pantalla de ingreso (`/login`).
  4. El sistema impide acceder a las pantallas y endpoints protegidos con la sesión cerrada sin volver a **iniciar sesión**.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` / `Médico` / `Gerente médico` / `Administrativo` / `Bioinformático` / `Transportista` / `Admin general` (Sujetos LEL) | Usuario con sesión activa que solicita **cerrar sesión**. |
| `auth_router` (`app/src/routers/`) | Capa `router`: recibe `POST /api/v1/auth/logout`, limpia cookies de sesión (`Set-Cookie` expirada) y devuelve la instrucción de redirección a `/login`. |
| `auth_service` (`app/src/services/`) | Capa `service`: revoca el identificador de sesión/token actual (`jti` / sesión de servidor) para que cualquier intento posterior de reutilizar ese token sea rechazado con `401 Unauthorized`, manteniendo intacto el registro en `dispositivos_conocidos`. |
| `usuario_repo` (`app/src/repos/`) | Capa `repo`: verifica opcionalmente al usuario y actualiza `dispositivos_conocidos.ultimo_acceso` sin eliminar el `DispositivoConocido` (para que la máquina siga siendo conocida en el próximo login del mismo usuario). |
| `PostgreSQL` | Mantiene intactas las filas de `usuarios` y `dispositivos_conocidos`. |

---

## Prerequisites

- El usuario cuenta con una sesión activa (o un token de primer ingreso / desafío de dispositivo) emitida por el sistema.

---

## Trigger

El usuario hace clic en el botón "Cerrar sesión" en la barra de navegación del sistema.
- **Endpoint HTTP**: `POST /api/v1/auth/logout`

---

## Workflow Tree

### STEP 1: Recepción de solicitud de `Cerrar sesión` e identificación de la sesión activa
**Actor**: `auth_router` -> `auth_service`
**Action**:
1. Extrae el token de sesión del header `Authorization: Bearer <token>` o de la cookie `HttpOnly` de sesión.
2. Decodifica y valida la estructura del token para obtener `usuario_id`, `rol` y el identificador único de sesión (`jti`).
**Timeout**: `1s`
**Input**: `{ authorization_header: Optional[str], session_cookie: Optional[str] }`
**Output on SUCCESS**: `{ usuario_id: int, jti: str, exp: datetime }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: No se envió ningún token o el token ya estaba expirado/inválido -> por idempotencia de cierre de sesión segura, limpia igualmente cualquier cookie en la respuesta y retorna `200 OK` (o `401 Unauthorized` si se invoca sin credenciales desde API pura) redirigiendo a `/login` para garantizar que el cliente quede fuera de las pantallas protegidas.

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Indicador "Cerrando sesión...".
  - Operator sees: Solicitud `POST /api/v1/auth/logout` en curso.
  - Database: Sin cambios.
  - Logs: `[auth_service] step_1_iniciar_logout usuario_id=<id> jti=<jti>`

---

### STEP 2: Finalización e invalidación de la sesión activa en el servidor
**Actor**: `auth_service` -> `usuario_repo`
**Action**:
1. Registra el `jti` (o token de sesión) en el registro de sesiones revocadas / invalida la sesión del lado del servidor hasta su fecha `exp`, de modo que ninguna petición subsiguiente que presente ese mismo token sea aceptada por el middleware de autenticación.
2. **Importante**: **No elimina** la fila de `dispositivos_conocidos` en `PostgreSQL`, ya que el hecho de **cerrar sesión** no convierte a una máquina conocida en una máquina desconocida para ese usuario.
3. Instruye al `auth_router` a emitir el header `Clear-Site-Data: "cookies", "storage"` / `Set-Cookie: session=; Max-Age=0; HttpOnly; SameSite=Lax`.
**Timeout**: `2s`
**Input**: `{ usuario_id: int, jti: str, exp: datetime }`
**Output on SUCCESS**: `{ sesion_finalizada: true, redirect_to: "/login" }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(timeout)` / `FAILURE(internal_error)`: Si falla la actualización auxiliar de `ultimo_acceso`, el servicio **prioriza siempre revocar la sesión en memoria/registro y borrar la cookie del cliente** (`ABORT_CLEANUP`), garantizando que la sesión no quede abierta en el equipo compartido.

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Redirección inmediata a la pantalla de ingreso (`/login`).
  - Operator sees: Token `jti` revocado; sesión finalizada.
  - Database: `usuarios` y `dispositivos_conocidos` permanecen íntegros.
  - Logs: `[auth_service] step_2_sesion_finalizada_ok usuario_id=<id> jti=<jti>`

---

### STEP 3: Bloqueo de acceso a pantallas y endpoints protegidos tras el cierre de sesión
**Actor**: Middleware de autenticación (`auth_router` / `auth_service`)
**Action**:
1. Cuando el navegador o cualquier cliente HTTP intenta acceder a cualquier pantalla o endpoint protegido (o presiona el botón "Atrás" del navegador) utilizando el token/sesión recién cerrado o sin token:
2. El middleware comprueba que la sesión está ausente o que su `jti` figura como revocado.
3. Rechaza la solicitud con `401 Unauthorized` (`code: "SESION_CERRADA_O_INVALIDA"`) e instruye al frontend a mantenerse en `/login`.
**Timeout**: `1s`
**Input**: Cualquier petición subsiguiente a un endpoint protegido (`/api/v1/estudios`, `/api/v1/pacientes`, `/api/v1/patologias`, etc.) con el token revocado.
**Output on SUCCESS**: Bloqueo efectivo (`401 Unauthorized`) -> El usuario debe volver a ejecutar `Iniciar sesión` (Escenario 27) para ingresar.
**Output on FAILURE**: *(Nunca debe permitir paso con un token revocado).*

**Observable states during this step**:
  - Customer/Actor (Usuario) sees: Pantalla de ingreso (`/login`); si intenta navegar a una URL protegida o usar el botón "Atrás", es redirigido inmediatamente a `/login`.
  - Operator sees: Rechazo `401 Unauthorized` ante cualquier intento de uso de token revocado.
  - Database: Sin lecturas ni escrituras de negocio permitidas.
  - Logs: `[auth_middleware] step_3_acceso_denegado_sesion_cerrada jti=<jti> path=<path>`

---

### ABORT_CLEANUP: Cierre forzoso de sesión del lado cliente ante fallo interno
**Triggered by**: Cualquier excepción inesperada o timeout en `STEP 2`.
**Actions** (in order):
  1. Revocar el `jti` en el almacén de revocación en memoria del proceso.
  2. Emitir igualmente los headers `Set-Cookie: session=; Max-Age=0` y `Clear-Site-Data` en la respuesta HTTP.
  3. Retornar respuesta indicando al frontend limpiar el almacenamiento local y redirigir a `/login`.
**What customer (Usuario) sees**: Redirección segura a la pantalla de ingreso (`/login`) con su sesión local completamente eliminada.
**What operator sees**: Warning en logs indicando fallo secundario durante `logout`, pero con sesión revocada exitosamente.

---

## State Transitions

```
[Sesión activa (access_token vigente)]
   -> (STEP 1-2: POST /api/v1/auth/logout)
   -> [Sesión finalizada / Token revocado + Redirección a /login (DispositivoConocido se conserva)]

[Sesión finalizada / Token revocado]
   -> (STEP 3: Intento de acceder a ruta protegida con el token anterior o sin sesión)
   -> [Acceso denegado (401 Unauthorized SESION_CERRADA_O_INVALIDA)]

[Sesión finalizada / Token revocado]
   -> (Usuario vuelve a ejecutar Escenario 27: Iniciar sesión)
   -> [Nueva sesión activa con nuevo jti]
```

---

## Handoff Contracts

### 1. Frontend (Usuario) -> Backend (`auth_router`) – Solicitud de cierre de sesión
**Endpoint**: `POST /api/v1/auth/logout`
**Headers**: `Authorization: Bearer <access_token>`
**Payload**:
```json
{}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "sesion_finalizada": true,
    "mensaje": "La sesión se ha cerrado correctamente.",
    "redirect_to": "/login"
  }
}
```
**Timeout**: `3s`

### 2. Frontend / Cliente -> Backend (Cualquier endpoint protegido tras cerrar sesión)
**Endpoint**: `GET /api/v1/estudios` (o cualquier ruta protegida) con el `access_token` revocado
**Failure response** (`401 Unauthorized`):
```json
{
  "ok": false,
  "error": "Su sesión ha finalizado. Por favor, vuelva a iniciar sesión.",
  "code": "SESION_CERRADA_O_INVALIDA",
  "retryable": false
}
```
**Timeout**: `1s`
**ON FAILURE**: El frontend limpia cualquier estado en memoria y redirige a `/login`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Sesión activa / Token `jti` | Escenario 27 (`Iniciar sesión`) | `STEP 2` (`Cerrar sesión`) | Revocación de `jti` en servidor + expiración inmediata de cookie (`Max-Age=0`) |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `.ai/2-Glosario_LEL.md` (`Verbo: Cerrar sesión`) y `.ai/3-Escenarios.md` (`Escenario 28`), el impacto exige cuatro efectos explícitos: (1) el usuario solicita cerrar sesión, (2) el sistema finaliza la sesión, (3) el sistema redirige al usuario a la pantalla de ingreso, y (4) el sistema impide acceder a las pantallas protegidas sin volver a iniciar sesión. | High | STEP 1 / STEP 2 / STEP 3 | Si se usan JWTs stateless sin lista de revocación, el episodio 4 fallaría ante reutilización del token antes de su expiración. Por ello, `STEP 2` y `STEP 3` exigen revocación explícita del `jti`/sesión en el backend además de limpiar el cliente. |
| RC-2 | En `app/src/core/models/usuarios.py`, `DispositivoConocido` modela las máquinas desde las que el usuario ya ingresó. Cerrar sesión no debe borrar `DispositivoConocido`, pues de lo contrario cada cierre de sesión obligaría a pedir código por mail en la misma máquina. | Medium | STEP 2 | Especificado explícitamente en `STEP 2` y probado en `TC-05`. |
| RC-3 | No existen aún `auth_router.py` ni `auth_service.py`. | Medium | Actors | Documentados para su implementación en el flujo SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Cerrar sesión activa | `POST /api/v1/auth/logout` con un `access_token` válido | Retorna `200 OK` con `sesion_finalizada: true`, `redirect_to: "/login"` y limpia cookies de sesión. |
| `TC-02`: Bloqueo de pantallas/endpoints protegidos tras cerrar sesión | Llamar a `POST /api/v1/auth/logout` y luego invocar cualquier endpoint protegido (ej. `GET /api/v1/estudios`) con el mismo `access_token` | El segundo llamado es rechazado con `401 Unauthorized` (`code: "SESION_CERRADA_O_INVALIDA"`). |
| `TC-03`: Acceso sin sesión a endpoint protegido | Invocar un endpoint protegido sin header `Authorization` ni cookie de sesión | Retorna `401 Unauthorized` (`code: "SESION_CERRADA_O_INVALIDA"`). |
| `TC-04`: Idempotencia al cerrar sesión dos veces seguidas | Invocar `POST /api/v1/auth/logout` dos veces consecutivas con el mismo token | Ambas peticiones dejan la sesión revocada y redirigen a `/login` sin producir error `500`. |
| `TC-05`: Conservación de `DispositivoConocido` tras cerrar sesión | Usuario cierra sesión (`POST /api/v1/auth/logout`) y luego vuelve a ejecutar `POST /api/v1/auth/login` desde el mismo `dispositivo_identificador` | El nuevo login reconoce la máquina como conocida (`dispositivos_conocidos` conserva la fila) e ingresa sin pedir un nuevo `CodigoVerificacion`. |
| `TC-06`: Cierre de sesión durante estado intermedio (primer ingreso o verificación de dispositivo) | Un usuario con `primer_ingreso_token` o `challenge_token` invoca `POST /api/v1/auth/logout` | El token temporal queda revocado y el usuario es redirigido a `/login`. |
| `TC-07`: Aplicación transversal a los 7 roles del LEL | Prueba parametrizada de `POST /api/v1/auth/logout` para usuarios de los 7 valores de `Rol` | Todos finalizan su sesión y quedan impedidos de acceder a sus respectivas rutas protegidas sin volver a iniciar sesión. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El backend mantiene un conjunto de revocación de `jti` (o tabla/almacén de sesiones activas) para invalidar instantáneamente los tokens al ejecutar `Cerrar sesión`. | `.ai/2-Glosario_LEL.md` (`Verbo: Cerrar sesión`) y `.ai/3-Escenarios.md` (`Escenario 28`, Episodio 4) | Medio: si solo se borrara el token en el frontend sin invalidarlo en el backend, un token capturado seguiría siendo aceptado por la API hasta su expiración. |

## Open Questions

- Ninguna. Los cuatro episodios del Escenario 28 están completamente cubiertos y verificables mediante `pytest`.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `.ai/2-Glosario_LEL.md`, `.ai/3-Escenarios.md` y `app/src/core/models/usuarios.py`. | Aprobada para implementación. |
