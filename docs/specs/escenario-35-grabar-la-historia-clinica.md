# WORKFLOW: Escenario 35 – Grabar la historia clínica
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-35`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Médico** | `Usuario` (`rol = Rol.MEDICO` o `Rol.GERENTE_MEDICO`) + perfil `Medico` (`medicos.id`, médico tratante) |
| **Sujetos** | **Paciente** | Modelo `Paciente` (`pacientes`: destinatario de la **historia clínica**) |
| **Objetos** | **Historia clínica** | Columna `Paciente.historia_clinica: Mapped[str] = mapped_column(Text)` en la tabla `pacientes` |
| **Objetos** | **Transcriptor de audio** | Cliente HTTP/servicio externo ASR (`app/src/clients/transcriptor_client.py`) que convierte la grabación de voz del **médico** en texto |
| **Verbos** | **Grabar historia clínica** | Dictar la **historia clínica** del **paciente**, transcribirla a texto y guardarla |
| **Verbos** | **Dar de alta paciente** | Flujo contenedor en el que el **médico** registra al **paciente** con su **historia clínica** obligatoria |
| **Estados** | *(No altera `EstadoEstudio`)* | Ocurre durante el alta o actualización clínica del **paciente** |

---

## Overview

- **Objetivo:** Cargar la **historia clínica** del **paciente** dictándola mediante una grabación de voz en lugar de escribirla manualmente.
- **Contexto:** El **médico** tratante está dando de alta a un **paciente** durante la consulta inicial (o editando su resumen clínico) y prefiere grabar con el micrófono de su computadora o celular el resumen de la **historia clínica**.
- **Recursos:** Grabación de audio (`audio`), **transcriptor de audio** (`transcriptor_client`), **historia clínica** (`pacientes.historia_clinica`).
- **Episodios:**
  1. El **médico** graba la **historia clínica** del **paciente**.
  2. El sistema envía la grabación al **transcriptor de audio**.
  3. El **transcriptor de audio** convierte la grabación en texto.
  4. El sistema guarda el texto como **historia clínica** del **paciente** (en `pacientes.historia_clinica`).

**Resumen del flujo:** Durante la consulta médica, el **médico** graba un clip de audio desde el navegador/dispositivo móvil y el frontend lo envía a `POST /api/pacientes/historia-clinica/transcribir` (`multipart/form-data`, incluyendo opcionalmente `paciente_id` si el paciente ya fue creado). El backend valida el rol (`Rol.MEDICO` o `Rol.GERENTE_MEDICO`), el formato MIME (`audio/webm`, `audio/wav`, `audio/mpeg`, `audio/mp4`, `audio/ogg`), la duración/tamaño máximo del archivo y envía el flujo de audio al **transcriptor de audio** a través de `transcriptor_client`. Una vez recibido el texto transcrito no vacío, el sistema elimina inmediatamente el buffer/archivo temporal de audio y:
- Si se indicó un `paciente_id` existente vinculado al **médico**, persiste el texto directamente en `pacientes.historia_clinica`.
- Si se está en el formulario de **Dar de alta paciente** (donde el paciente aún no existe en BD), devuelve el texto transcrito al formulario para que el **médico** lo revise/confirme y el sistema lo guarde en `pacientes.historia_clinica` al enviar el alta (`POST /api/pacientes`).

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Médico** (Sujeto LEL) | Graba el resumen de la **historia clínica** del **paciente** y confirma su guardado. |
| **Router HTTP** (`app/src/routers/pacientes.py`) | Verifica sesión activa y rol `Rol.MEDICO` / `Rol.GERENTE_MEDICO`, valida el archivo `multipart/form-data` y devuelve la transcripción y el estado de guardado. |
| **Servicio de Pacientes / Clínica** (`app/src/services/paciente_service.py`) | Valida el archivo de audio, coordina la llamada al **transcriptor de audio**, asegura el borrado del audio temporal y guarda el texto resultante en `Paciente.historia_clinica`. |
| **Cliente Transcriptor de Audio** (`app/src/clients/transcriptor_client.py`) | Envía el archivo de audio vía `httpx` al servicio **transcriptor de audio** y procesa la respuesta JSON con el texto convertido. |
| **Repositorio de Pacientes** (`app/src/repos/paciente_repo.py`) | Inserta o actualiza `pacientes.historia_clinica` en PostgreSQL. |
| **PostgreSQL** (`db`) | Persiste `pacientes.historia_clinica` (`Text`, obligatorio `NOT NULL`). |

---

## Prerequisites

- **Sesión y Rol:** El usuario autenticado debe poseer una sesión activa válida con `Usuario.rol in (Rol.MEDICO, Rol.GERENTE_MEDICO)` y contar con perfil `Medico` en la tabla `medicos`.
- **Datos existentes en `app/src/core/models/`:**
  - Existe el registro del **médico** en `medicos`.
  - Si se actualiza un **paciente** ya registrado (`paciente_id` provisto), debe existir la fila en `pacientes` con `pacientes.medico_id == medico.id`.
- **Estado previo del `Estudio`:** No aplica (`N/A`).
- **Servicios externos:** El módulo **transcriptor de audio** debe estar configurado en `TRANSCRIPTOR_API_BASE_URL` y accesible.

---

## Trigger

- **Acción de usuario:** El **médico** presiona "Grabar historia clínica", dicta el resumen clínico del **paciente**, detiene la grabación y la envía para transcripción y guardado.
- **Endpoint HTTP:**
  - `POST /api/pacientes/historia-clinica/transcribir` (transcripción del audio y guardado opcional si se provee `paciente_id`).
  - `POST /api/pacientes` o `PATCH /api/pacientes/{paciente_id}/historia-clinica` (persistencia definitiva de `historia_clinica` en la tabla `pacientes`).

---

## Workflow Tree

### STEP 1: Autenticación del médico y validación del archivo de grabación de audio
**Actor**: **Médico** -> Router (`pacientes.py`) -> Servicio (`paciente_service.py`)
**Action**:
  1. Verifica que el usuario autenticado tenga `Rol.MEDICO` o `Rol.GERENTE_MEDICO`.
  2. Comprueba que la petición `multipart/form-data` contenga el archivo `audio` no vacío (`size > 0` y `size <= 15 MB`).
  3. Valida que el tipo MIME o cabecera del archivo sea un formato de audio soportado (`audio/webm`, `audio/wav`, `audio/mpeg`, `audio/mp4`, `audio/ogg`).
  4. Si se incluyó `paciente_id`, verifica en `paciente_repo` que el `Paciente` exista y pertenezca al **médico** (`paciente.medico_id == medico.id`).
**Timeout**: `2s`
**Input**:
```json
{
  "medico_usuario_id": 11,
  "audio_filename": "historia_clinica.webm",
  "audio_content_type": "audio/webm",
  "audio_size_bytes": 482100,
  "paciente_id": 45
}
```
**Output on SUCCESS**: `{ audio_stream: bytes, content_type: str, medico_id: int, paciente_id: int | null }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(unauthorized / forbidden)`: Usuario no autenticado (`401`) o su rol no es `MEDICO` ni `GERENTE_MEDICO` (`403 Forbidden`, `ROL_NO_AUTORIZADO`).
  - `FAILURE(validation_error)`:
    - Archivo `audio` faltante o de `0 bytes` -> retornar `422 Unprocessable Entity` (`AUDIO_VACIO`).
    - Formato MIME no permitido (por ejemplo, `.exe` o `.pdf`) -> retornar `415 Unsupported Media Type` / `422` (`FORMATO_AUDIO_NO_SOPORTADO`).
    - Tamaño superior a `15 MB` -> retornar `413 Payload Too Large` (`AUDIO_EXCEDE_LIMITE`).
  - `FAILURE(not_found / forbidden_patient)`: `paciente_id` inexistente (`404`) o perteneciente a otro médico (`403`, `PACIENTE_AJENO`).

**Observable states during this step**:
  - Customer/Actor (**Médico**) sees: Indicador "Enviando grabación al transcriptor de audio...".
  - Operator sees: Recepción de archivo de audio en `POST /api/pacientes/historia-clinica/transcribir`.
  - Database: Lectura opcional de verificación sobre `medicos` y `pacientes`; sin escrituras.
  - Logs: `[paciente_service] step=1_validar_audio medico_id=6 size_bytes=482100 content_type=audio/webm`

---

### STEP 2: Envío de la grabación al Transcriptor de audio y conversión a texto
**Actor**: Servicio (`paciente_service.py`) -> Cliente Transcriptor (`transcriptor_client.py`) -> **Transcriptor de audio**
**Action**: Envía el archivo de audio mediante `POST /external/asr/transcribe` (con idioma `es-AR`) al **transcriptor de audio**. Recibe el texto transcrito (`texto_historia_clinica`), normaliza espacios en blanco y verifica que la transcripción resultante no esté vacía (por ejemplo, ante un audio silencioso o inaudible).
**Timeout**: `15s` por intento (hasta 2 intentos con backoff de `1.0s` ante fallos de red/5xx).
**Input**: `{ audio_bytes: bytes, content_type: "audio/webm", language: "es-AR" }`
**Output on SUCCESS**: `{ texto_transcrito: str }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(validation_error / audio_inaudible)`: El **transcriptor de audio** devuelve una cadena vacía o código `INAUDIBLE_AUDIO` -> ejecutar `ABORT_CLEANUP` (descartar buffer de audio) -> retornar `422 Unprocessable Entity` (`AUDIO_SIN_VOZ_DETECTADA`, `retryable=True`) indicando al **médico** que vuelva a grabar o escriba el texto.
  - `FAILURE(timeout)`: El **transcriptor de audio** supera los `15s` en ambos intentos -> ejecutar `ABORT_CLEANUP` -> retornar `504 Gateway Timeout` (`TRANSCRIPTOR_TIMEOUT`, `retryable=True`).
  - `FAILURE(transient_external_error)`: El **transcriptor de audio** responde `502`/`503`/`429` -> reintentar 1 vez; si persiste, ejecutar `ABORT_CLEANUP` y retornar `502 Bad Gateway` (`TRANSCRIPTOR_NO_DISPONIBLE`, `retryable=True`).

**Observable states during this step**:
  - Customer/Actor (**Médico**) sees: Animación de transcripción en curso ("Convirtiendo audio en texto...").
  - Operator sees: Llamada saliente a `TRANSCRIPTOR_API_BASE_URL/external/asr/transcribe`.
  - Database: Sin escrituras en PostgreSQL mientras se aguarda la respuesta del servicio externo.
  - Logs: `[transcriptor_client] step=2_transcripcion_ok medico_id=6 chars_transcritos=342`

---

### STEP 3: Guardado del texto como historia clínica del paciente
**Actor**: Servicio (`paciente_service.py`) -> Repositorio (`paciente_repo.py`) -> PostgreSQL
**Action**:
  1. Elimina de memoria/disco temporal cualquier copia del archivo de audio original.
  2. Si la petición incluye `paciente_id` (o cuando el **médico** confirma el formulario de alta de paciente `POST /api/pacientes` / actualización `PATCH /api/pacientes/{paciente_id}/historia-clinica`):
     - Actualiza o inserta `pacientes.historia_clinica = texto_transcrito` en PostgreSQL y ejecuta `COMMIT`.
  3. Si la transcripción se invocó durante la carga del formulario de un **paciente** aún no persistido (`paciente_id == None`), devuelve `texto_transcrito` para poblar el campo `historia_clinica` del formulario, el cual se persiste obligatoriamente en `pacientes.historia_clinica` al confirmar el alta del paciente.
**Timeout**: `3s`
**Input**:
```json
{
  "paciente_id": 45,
  "historia_clinica": "Paciente de 8 años que consulta por acroparestesias en extremidades e hipohidrosis desde los 6 años..."
}
```
**Output on SUCCESS**: `{ paciente_id: 45 | null, historia_clinica: str, guardado_en_bd: bool }` -> Retornar `200 OK` al **médico** (FIN DEL WORKFLOW).
**Output on FAILURE**:
  - `FAILURE(validation_error)`: `historia_clinica` vacía al intentar persistir en `pacientes` -> retornar `422 Unprocessable Entity` (`HISTORIA_CLINica_OBLIGATORIA`).
  - `FAILURE(database_error / timeout)`: Error al actualizar/insertar en `pacientes` -> ejecutar `ABORT_CLEANUP` (`rollback`) -> retornar `500 Internal Server Error` (`DB_ERROR`, `retryable=True`), preservando el `texto_transcrito` en la respuesta o en el cliente para que el **médico** no tenga que volver a dictar.

**Observable states during this step**:
  - Customer/Actor (**Médico**) sees: El texto transcrito aparece cargado en el campo **Historia clínica** del **paciente** y recibe confirmación de guardado.
  - Operator sees: Registro actualizado en `pacientes.historia_clinica`.
  - Database:
    - Tabla `pacientes`: columna `historia_clinica` contiene el texto convertido por el **transcriptor de audio**.
  - Logs: `[paciente_repo] step=3_historia_clinica_guardada paciente_id=45 chars=342`

---

### ABORT_CLEANUP: Limpieza de archivos temporales de audio y rollback de base de datos
**Triggered by**: Cualquier fallo en `STEP 2` o `STEP 3`.
**Actions** (in order):
  1. Si se creó un archivo o buffer temporal de audio en el servidor (`/tmp` o memoria), eliminarlo de inmediato (`os. unlink` / cierre de `BytesIO`) para no retener grabaciones médicas crudas en el servidor.
  2. Si se había iniciado una transacción en PostgreSQL en `STEP 3`, ejecutar `db.session.rollback()`.
**What customer/actor (**Médico**) sees**: Mensaje de error explicativo con opción de reintentar el envío del audio o editar manualmente el campo de **historia clínica**.
**What operator sees**: Log `WARN`/`ERROR` confirmando la limpieza del recurso temporal de audio y el motivo del fallo.

---

## State Transitions

```
Historia Clínica del Paciente (pacientes.historia_clinica):
  Modalidad A – Durante el formulario de Dar de alta paciente:
    [Grabación de audio en navegador]
      -- (STEP 1 + STEP 2: Transcriptor de audio convierte a texto) -->
    [Texto cargado en formulario de alta]
      -- (STEP 3: Médico confirma alta del paciente) -->
    [Persistido en `pacientes.historia_clinica` (NOT NULL)]

  Modalidad B – Sobre un Paciente existente (`paciente_id` provisto):
    [pacientes.historia_clinica = <texto_previo>]
      -- (STEP 1 + STEP 2 + STEP 3 exitosos) -->
    [pacientes.historia_clinica = <nuevo_texto_transcrito>]

Estudio (EstadoEstudio):
  Sin transición en este escenario.
```

---

## Handoff Contracts

### 1. Frontend (Médico) -> Backend: Transcribir y guardar historia clínica
**Endpoint**: `POST /api/pacientes/historia-clinica/transcribir`
**Content-Type**: `multipart/form-data`
**Payload**:
- `audio`: archivo binario (`audio/webm`, `audio/wav`, `audio/mpeg`, `audio/mp4`, `audio/ogg`, máx. `15 MB`)
- `paciente_id`: `int` *(opcional; si se envía, guarda el texto directamente en `pacientes.historia_clinica`)*

**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "paciente_id": 45,
    "historia_clinica": "Paciente de 8 años que consulta por acroparestesias en extremidades e hipohidrosis desde los 6 años.",
    "guardado_en_bd": true
  }
}
```
**Failure response** (`401` / `403` / `413` / `415` / `422` / `502` / `504`):
```json
{
  "ok": false,
  "error": "No se detectó voz clara en la grabación enviada. Por favor, intente grabar nuevamente.",
  "code": "AUDIO_SIN_VOZ_DETECTADA",
  "retryable": true
}
```
**Timeout**: `20s`
**ON FAILURE**: Permitir al **médico** volver a enviar la grabación o escribir directamente en el área de texto de **historia clínica**.

---

### 2. Backend (`transcriptor_client`) -> Transcriptor de audio (API externa)
**Endpoint**: `POST /external/asr/transcribe`
**Content-Type**: `multipart/form-data`
**Payload**:
- `file`: stream binario del audio
- `language`: `"es-AR"`
- `domain`: `"medical_clinical_exome"`

**Success response** (`200 OK`):
```json
{
  "text": "Paciente de 8 años que consulta por acroparestesias en extremidades e hipohidrosis desde los 6 años.",
  "duration_seconds": 14.2,
  "language": "es-AR"
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Servicio de transcripción de audio temporalmente saturado",
  "code": "TRANSCRIPTOR_NO_DISPONIBLE",
  "retryable": true
}
```
**Timeout**: `15s` por intento (máximo 2 intentos).
**ON FAILURE**: Descartar buffer temporal y propagar código `502`/`504` con `retryable = true`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Buffer / archivo temporal de grabación de audio | Step 1 | Step 3 (éxito) o `ABORT_CLEANUP` (fallo) | `buffer.close()` / `Path.unlink(missing_ok=True)` en bloque `finally` |
| Actualización de `pacientes.historia_clinica` en sesión SQLAlchemy | Step 3 | `ABORT_CLEANUP` | `db.session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/perfiles.py`, `Paciente` tiene la columna `historia_clinica: Mapped[str] = mapped_column(Text)` (no anulable, en concordancia con `.ai/1-Entrevista.md` línea 249: "solamente puedes dejar el familiograma, el resto son todos obligatorios"). | Low | Overview, STEP 3 | El modelo almacena directamente el texto transcrito en `pacientes.historia_clinica`; el archivo de audio no se persiste en base de datos. |
| RC-2 | En `.ai/1-Entrevista.md` (líneas 76 y 317-319) se indica que el médico usa este mecanismo al dar de alta al paciente tanto desde computadora como desde celular (diseño responsivo). | Low | STEP 1, Handoff Contracts | Se soportan los contenedores de audio estándar de navegadores de escritorio y móviles (`audio/webm`, `audio/mp4`, `audio/wav`, `audio/mpeg`, `audio/ogg`). |
| RC-3 | No existen aún `app/src/clients/transcriptor_client.py` ni el endpoint en `app/src/routers/pacientes.py`. | Medium | Actors, Handoff Contracts | Definidos los contratos exactos de capa `router -> service -> repo + clients`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Transcripción y guardado en paciente existente | `POST /api/pacientes/historia-clinica/transcribir` con archivo `audio/webm` válido y `paciente_id=45` enviado por su médico tratante | Invoca a `transcriptor_client`, actualiza `pacientes.historia_clinica` en BD, elimina el audio temporal y retorna `200 OK` con `guardado_en_bd=True`. |
| `TC-02`: Happy path – Transcripción durante el formulario de alta de paciente (`paciente_id=None`) y posterior alta | `POST /api/pacientes/historia-clinica/transcribir` sin `paciente_id` seguido de `POST /api/pacientes` con el texto devuelto | El primer llamado retorna `200 OK` con el texto transcrito (`guardado_en_bd=False`); el segundo crea la fila en `pacientes` con `historia_clinica` poblada. |
| `TC-03`: Rechazo por rol no autorizado | `POST /api/pacientes/historia-clinica/transcribir` invocado por `Rol.PACIENTE` o `Rol.ADMINISTRATIVO` | Retorna `403 Forbidden` (`ROL_NO_AUTORIZADO`), sin llamar al **transcriptor de audio**. |
| `TC-04`: Rechazo por archivo vacío o formato inválido | Envío de archivo de `0 bytes` o de tipo `application/pdf` | Retorna `422` (`AUDIO_VACIO`) o `415` (`FORMATO_AUDIO_NO_SOPORTADO`); no invoca al cliente externo. |
| `TC-05`: Grabación sin voz / transcripción vacía | El **transcriptor de audio** devuelve `text: "   "` | Retorna `422 Unprocessable Entity` (`AUDIO_SIN_VOZ_DETECTADA`) y no sobrescribe `pacientes.historia_clinica`. |
| `TC-06`: Timeout del transcriptor de audio con reintento | `transcriptor_client` lanza `httpx.TimeoutException` en los 2 intentos | Limpia el archivo temporal en `ABORT_CLEANUP` y retorna `504 Gateway Timeout` (`TRANSCRIPTOR_TIMEOUT`, `retryable=True`). |
| `TC-07`: Intento de sobrescribir la historia clínica de un paciente de otro médico | `POST /api/pacientes/historia-clinica/transcribir` con `paciente_id` cuyo `medico_id` es distinto al del médico autenticado | Retorna `403 Forbidden` (`PACIENTE_AJENO`), sin llamar al transcriptor ni modificar `pacientes`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El sistema solo almacena en base de datos el texto resultante en `pacientes.historia_clinica` (`Text`), descartando el archivo de audio una vez transcrito. | Verificado en `.ai/2-Glosario_LEL.md` (`Verbo: Grabar historia clínica`: "El sistema guarda el texto como historia clínica del paciente") y `app/src/core/models/perfiles.py` (no existe columna de ruta de audio en `Paciente`). | Bajo. |
| A2 | El **médico** puede editar o complementar el texto devuelto por el **transcriptor de audio** antes de confirmar el alta definitiva del **paciente**. | Estándar de usabilidad clínica en dictado médico. | Bajo. |

## Open Questions

- ¿Cuál es la duración máxima esperada de un dictado de **historia clínica** en consulta (por ejemplo, 3 minutos / `15 MB`) para ajustar el límite del servidor web y el timeout de `httpx`?

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada verificando `Paciente.historia_clinica` en `app/src/core/models/perfiles.py` y el LEL. | Aprobada. |
