# WORKFLOW: Escenario 25 – Consultar el chatbot sobre patologías
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-25`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Paciente` |
| **Objetos** | `Chatbot`, `Patología` |
| **Verbos** | *(Consultar al `Chatbot` sobre las `Patologías`)* |
| **Estados** | *(No altera el estado de ningún `Estudio`; requiere que el `Paciente` haya completado `Cambiar contraseña inicial`)* |

---

## Overview

- **Objetivo**: Obtener respuestas claras y confiables sobre las cinco **patologías** lisosomales contempladas por el sistema (enfermedad de Fabry, enfermedad de Pompe, mucopolisacaridosis 1, Gaucher y ASMD).
- **Contexto**: El **paciente** autenticado tiene dudas sobre alguna de las **patologías** y utiliza la pantalla del **chatbot** dentro del sistema. Conforme a la entrevista y al LEL, el **chatbot** es un módulo externo especializado que no deriva a operadores humanos.
- **Recursos**: `Chatbot` (API externa), información sobre `Patologías` (`patologias`).
- **Episodios**:
  1. El **paciente** formula una pregunta en la interfaz del sistema.
  2. El sistema valida la consulta y la deriva al **chatbot** externo.
  3. El **chatbot** genera una respuesta sobre las **patologías**.
  4. El sistema recibe la respuesta y la muestra al **paciente** en la interfaz gráfica.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` (Sujeto LEL) | Usuario autenticado (`Rol.PACIENTE`, con `debe_cambiar_password == False`) que formula preguntas sobre las **patologías**. |
| `Chatbot` (Objeto LEL) | Módulo externo preparado para responder consultas del **paciente** sobre las cinco **patologías** lisosomales. |
| `chatbot_router` (`app/src/routers/`) | Capa `router`: valida la sesión activa del **paciente** y el formato de la pregunta recibida. |
| `chatbot_service` (`app/src/services/`) | Capa `service`: valida que el **paciente** exista, enriquece opcionalmente el contexto con las **patologías** registradas en `patologias` (sin exponer datos genéticos sensibles ni PII innecesaria al servicio externo) y delega la pregunta al `chatbot_client`. |
| `clinica_repo` / `paciente_repo` (`app/src/repos/`) | Capa `repo`: verifica el perfil del **paciente** y obtiene el catálogo de nombres de **patologías** válidas (`patologias`). |
| `chatbot_client` (`app/src/clients/`) | Capa `clients`: cliente HTTP (`httpx`) que envía la pregunta al **chatbot** externo con timeout y política de reintentos. |
| `PostgreSQL` | Provee lectura de `usuarios`, `pacientes` y `patologias` (flujo sin mutación de estado de negocio en base de datos). |

---

## Prerequisites

- El **paciente** ha iniciado sesión (`Rol.PACIENTE`), ya completó el cambio de su contraseña inicial (`usuarios.debe_cambiar_password == False`) y su dispositivo de acceso está verificado.
- El módulo externo **Chatbot** se encuentra configurado mediante variables de entorno (`CHATBOT_API_URL`, `CHATBOT_API_TIMEOUT_SECONDS`).

---

## Trigger

El **paciente** escribe una pregunta en el cuadro de consulta sobre **patologías** y presiona "Enviar".
- **Endpoint HTTP**: `POST /api/v1/chatbot/consultas`

---

## Workflow Tree

### STEP 1: Autorización del `Paciente` y validación de la pregunta
**Actor**: `chatbot_router` -> `chatbot_service`
**Action**:
1. Verifica que el usuario autenticado tenga `Rol.PACIENTE` y que `usuario.debe_cambiar_password == False`.
2. Valida que el campo `pregunta` sea una cadena no vacía (después de `strip()`) con longitud entre `3` y `1000` caracteres.
3. Si se envió opcionalmente `patologia_id`, verifica en `clinica_repo` que corresponda a una **patología** existente en la tabla `patologias`.
**Timeout**: `2s`
**Input**: `{ usuario_id: int, pregunta: str, patologia_id: Optional[int] }`
**Output on SUCCESS**: `{ paciente_id: int, pregunta_limpia: str, patologia_nombre: Optional[str] }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no tiene `Rol.PACIENTE` o aún tiene `debe_cambiar_password == True` -> retorna `403 Forbidden` (`code: "ACCESO_CHATBOT_NO_AUTORIZADO"`).
  - `FAILURE(validation_error)`: La `pregunta` está vacía, tiene menos de 3 caracteres o supera los 1000 caracteres -> retorna `400 Bad Request` (`code: "PREGUNTA_INVALIDA"`).
  - `FAILURE(not_found)`: Se indicó un `patologia_id` que no existe en `patologias` -> retorna `404 Not Found` (`code: "PATOLOGIA_NO_ENCONTRADA"`).
  - `FAILURE(timeout)`: Supera `2s` -> retorna `504 Gateway Timeout` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: Su pregunta aparece en el historial del chat con estado "Enviando consulta...".
  - Operator sees: Petición `POST /api/v1/chatbot/consultas` en validación.
  - Database: Solo lectura en `usuarios`, `pacientes` y `patologias`.
  - Logs: `[chatbot_service] step_1_validar_consulta_chatbot paciente_id=<id> patologia_id=<id>`

---

### STEP 2: Derivación de la consulta al módulo externo `Chatbot`
**Actor**: `chatbot_service` -> `chatbot_client` -> `Chatbot` (API externa)
**Action**:
1. Construye el payload para el **chatbot** externo incluyendo únicamente la `pregunta`, el contexto de la **patología** consultada (si fue indicada o la asociada al diagnóstico presuntivo) y la lista de las 5 **patologías** contempladas por el laboratorio (`Fabry`, `Pompe`, `Mucopolisacaridosis 1`, `Gaucher`, `ASMD`), **sin enviar DNI, correo ni variantes genéticas del paciente** (principio de minimización de datos / seguridad mencionado en la entrevista, línea 315).
2. Envía la petición HTTP `POST` al endpoint del **chatbot** externo.
**Timeout**: `10s` por intento (con 1 reintento automático con backoff de `1s` ante errores de red o `502/503/504`)
**Input**: `{ pregunta: str, patologia_contexto: Optional[str], patologias_habilitadas: list[str] }`
**Output on SUCCESS**: `{ respuesta: str, patologias_relacionadas: list[str] }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(timeout)`: El **chatbot** externo tarda más de `10s` en ambos intentos -> `ABORT_CLEANUP` -> retorna `504 Gateway Timeout` (`code: "CHATBOT_TIMEOUT"`, `retryable: true`).
  - `FAILURE(transient_external_error)`: El **chatbot** externo devuelve `502`/`503` o error de conexión tras el reintento -> `ABORT_CLEANUP` -> retorna `503 Service Unavailable` (`code: "CHATBOT_NO_DISPONIBLE"`, `retryable: true`).
  - `FAILURE(permanent_external_error)`: El **chatbot** externo rechaza la consulta (`400`/`422`, ej. consulta fuera de dominio o formato rechazado) -> retorna `422 Unprocessable Entity` (`code: "CONSULTA_NO_PROCESABLE_POR_CHATBOT"`, `retryable: false`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: Indicador "El asistente está escribiendo una respuesta...".
  - Operator sees: Petición HTTP saliente desde `chatbot_client` hacia `Chatbot`.
  - Database: Sin escrituras.
  - Logs: `[chatbot_client] step_2_derivar_pregunta_chatbot status=<status> latency_ms=<ms>`

---

### STEP 3: Formateo y entrega de la respuesta al `Paciente`
**Actor**: `chatbot_service` -> `chatbot_router` -> Frontend (`Paciente`)
**Action**:
1. Verifica que la respuesta recibida del **chatbot** no sea vacía y la sanea contra inyección de HTML/scripts.
2. Retorna la respuesta estructurada al frontend para su visualización inmediata por el **paciente** (recordando que el **chatbot** no transfiere la conversación a ningún operador humano).
**Timeout**: `1s`
**Input**: `{ pregunta: str, respuesta: str, patologias_relacionadas: list[str] }`
**Output on SUCCESS**: `{ pregunta: str, respuesta: str, patologias_relacionadas: list[str], respondido_en: datetime }` -> Retorna `200 OK`.
**Output on FAILURE**:
  - `FAILURE(empty_upstream_response)`: El **chatbot** respondió `200 OK` pero con texto vacío -> retorna `502 Bad Gateway` (`code: "RESPUESTA_CHATBOT_VACIA"`, `retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Paciente`) sees: La respuesta del **chatbot** sobre la **patología** desplegada en la ventana de conversación.
  - Operator sees: Solicitud completada con `200 OK`.
  - Database: Sin modificaciones en tablas de negocio (`0` filas creadas/alteradas).
  - Logs: `[chatbot_service] step_3_respuesta_entregada_ok paciente_id=<id> chars=<len>`

---

### ABORT_CLEANUP: Manejo de fallo de comunicación con el `Chatbot`
**Triggered by**: Timeout o caída del módulo externo **Chatbot** en `STEP 2` o respuesta vacía en `STEP 3`.
**Actions** (in order):
  1. Cerrar limpiamente el socket/conexión HTTP en `chatbot_client`.
  2. Registrar el evento de indisponibilidad del **chatbot** en los logs del sistema.
  *(No hay recursos en base de datos que revertir dado que la consulta es de solo lectura).*
**What customer (`Paciente`) sees**: Mensaje amigable en la ventana del chat ("El asistente de consultas sobre patologías no se encuentra disponible en este momento. Por favor, intente nuevamente en unos instantes.") con botón "Reintentar envío".
**What operator sees**: Métrica/log de error de conectividad con `CHATBOT_API_URL`.

---

## State Transitions

```
[Sesión activa de Paciente]
   -> (STEP 1: pregunta válida)
   -> [Consulta enviada a Chatbot externo]
   -> (STEP 2-3: Chatbot responde exitosamente)
   -> [Respuesta mostrada al Paciente (sin alterar estados en PostgreSQL)]

[Consulta enviada a Chatbot externo]
   -> (STEP 2: timeout o error 5xx tras reintento -> ABORT_CLEANUP)
   -> [Estado de error recuperable en UI con opción de reintento]
```

---

## Handoff Contracts

### 1. Frontend (`Paciente`) -> Backend (`chatbot_router`)
**Endpoint**: `POST /api/v1/chatbot/consultas`
**Payload**:
```json
{
  "pregunta": "¿Qué es la enfermedad de Fabry y cuáles son sus síntomas principales?",
  "patologia_id": 1
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "pregunta": "¿Qué es la enfermedad de Fabry y cuáles son sus síntomas principales?",
    "respuesta": "La enfermedad de Fabry es una patología lisosomal genética causada por la deficiencia de la enzima alfa-galactosidasa A. Su síntoma cardinal suele ser la acroparestesia (dolor o ardor en manos y pies), acompañada de síntomas secundarios como angioqueratomas e hipohidrosis.",
    "patologias_relacionadas": ["Enfermedad de Fabry"],
    "respondido_en": "2026-10-28T19:55:00Z"
  }
}
```
**Failure response** (`400` / `403` / `404` / `503` / `504`):
```json
{
  "ok": false,
  "error": "El servicio de chatbot sobre patologías no respondió dentro del tiempo esperado.",
  "code": "CHATBOT_TIMEOUT",
  "retryable": true
}
```
**Timeout**: `22s`

### 2. `chatbot_service` (`chatbot_client`) -> `Chatbot` (API Externa)
**Endpoint**: `POST /api/v1/chatbot/ask`
**Payload**:
```json
{
  "pregunta": "¿Qué es la enfermedad de Fabry y cuáles son sus síntomas principales?",
  "patologia_contexto": "Enfermedad de Fabry",
  "patologias_habilitadas": [
    "Enfermedad de Fabry",
    "Enfermedad de Pompe",
    "Mucopolisacaridosis 1",
    "Enfermedad de Gaucher",
    "ASMD"
  ]
}
```
**Success response**:
```json
{
  "ok": true,
  "respuesta": "La enfermedad de Fabry es una patología lisosomal genética causada por la deficiencia de la enzima alfa-galactosidasa A...",
  "patologias_relacionadas": ["Enfermedad de Fabry"]
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Model inference timeout",
  "code": "UPSTREAM_MODEL_TIMEOUT",
  "retryable": true
}
```
**Timeout**: `10s`
**ON FAILURE**: Reintentar 1 vez con backoff de `1s`; si persiste, ejecutar `ABORT_CLEANUP` y devolver `503`/`504` con `retryable: true`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Conexión HTTP en `chatbot_client` | Step 2 | `ABORT_CLEANUP` | Cierre de contexto `httpx.AsyncClient` / `httpx.Client` |
| *(Ningún registro creado en `PostgreSQL`)* | — | — | — |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/`, no existe ninguna tabla de historial de conversaciones de chatbot; conforme a `.ai/1-Entrevista.md` (líneas 492, 497-498): *"Ustedes le van a tirar la pregunta y van a recibir una respuesta y se la van a mostrar en la interfaz gráfica al usuario, no más que eso"*. | Low | Overview / STEP 2 / STEP 3 | El flujo se diseña sin persistencia de mensajes en base de datos, alineado 100% con los modelos existentes y con la entrevista. |
| RC-2 | En `.ai/1-Entrevista.md` (línea 315), se enfatiza la privacidad de los datos genéticos del paciente. | Medium | STEP 2 | El contrato hacia la API externa del **Chatbot** excluye explícitamente el DNI, nombre, email y variantes del **paciente**. |
| RC-3 | No existen aún `chatbot_router.py`, `chatbot_service.py` ni `chatbot_client.py`. | Medium | Actors | Especificados para su implementación bajo la arquitectura en capas del proyecto. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Consulta válida sobre una de las 5 patologías | `POST /api/v1/chatbot/consultas` por `Rol.PACIENTE` con pregunta sobre Fabry/Pompe/MPS1/Gaucher/ASMD | Retorna `200 OK` con la respuesta generada por el `Chatbot`; verifica que `chatbot_client` fue invocado sin enviar PII del paciente. |
| `TC-02`: Pregunta vacía o demasiado corta | `POST /api/v1/chatbot/consultas` con `pregunta: "   "` | Retorna `400 Bad Request` (`code: "PREGUNTA_INVALIDA"`); no invoca a `chatbot_client`. |
| `TC-03`: Pregunta excede longitud máxima | `POST /api/v1/chatbot/consultas` con `pregunta` > 1000 caracteres | Retorna `400 Bad Request` (`code: "PREGUNTA_INVALIDA"`). |
| `TC-04`: Usuario no autorizado (otro rol o paciente sin cambiar contraseña inicial) | `POST /api/v1/chatbot/consultas` por `Rol.ADMINISTRATIVO` o por un `Paciente` con `debe_cambiar_password=True` | Retorna `403 Forbidden` (`code: "ACCESO_CHATBOT_NO_AUTORIZADO"`). |
| `TC-05`: Fallo transitorio recuperado en el reintento | `chatbot_client` lanza timeout en el primer intento y responde `200 OK` en el segundo intento | El servicio reintenta automáticamente y retorna `200 OK` al **paciente**. |
| `TC-06`: Caída total o timeout del `Chatbot` externo | `chatbot_client` falla por timeout en ambos intentos | Ejecuta `ABORT_CLEANUP` y retorna `504 Gateway Timeout` (`code: "CHATBOT_TIMEOUT"`, `retryable: true`). |
| `TC-07`: Respuesta vacía del `Chatbot` externo | `chatbot_client` devuelve `{"ok": true, "respuesta": ""}` | Retorna `502 Bad Gateway` (`code: "RESPUESTA_CHATBOT_VACIA"`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El **chatbot** es de uso exclusivo para el rol `Paciente` a través de la aplicación web, y responde en forma síncrona por cada pregunta enviada sin requerir almacenamiento de sesiones de chat en `PostgreSQL`. | `.ai/2-Glosario_LEL.md` (`Objeto: Chatbot`) y `.ai/1-Entrevista.md` (líneas 492, 497-498) | Bajo. |

## Open Questions

- Ninguna. El alcance del módulo externo **Chatbot** está acotado explícitamente en la entrevista y en el LEL.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `.ai/2-Glosario_LEL.md`, `.ai/3-Escenarios.md` y `app/src/core/models/`. | Aprobada para implementación. |
