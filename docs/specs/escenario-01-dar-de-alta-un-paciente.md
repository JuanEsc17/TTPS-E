# WORKFLOW: Escenario 1 – Dar de alta un paciente
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-1`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Médico` (sinónimos: médico tratante, médico derivante), `Gerente médico` (médico con facultades adicionales), `Paciente` |
| **Objetos** | `Patología`, `Síntoma`, `Síntoma cardinal`, `Síntoma secundario`, `SNOMED`, `Historia clínica`, `Transcriptor de audio`, `Familiar`, `Familiograma`, `API de familiograma`, `Aviso` |
| **Verbos** | `Dar de alta paciente`, `Cargar síntomas`, `Grabar historia clínica`, `Cambiar contraseña inicial` |
| **Estados** | *(No aplica transición de `EstadoEstudio`; habilita el posterior `Dar de alta estudio` hacia `Creado`)* |

---

## Overview

- **Objetivo**: Registrar un `Paciente` con sus datos personales, clínicos (`Diagnóstico presuntivo`, `Historia clínica`, `Síntomas` codificados en `SNOMED`, `tipo_sospecha`) y familiares (`Familiar` y `Familiograma` opcional) para poder iniciar posteriormente un `Estudio` de exoma clínico.
- **Contexto**: El `Paciente` es atendido en consulta inicial por un `Médico` tratante (o `Gerente médico`) y necesita ser incorporado al sistema si aún no existe. Si el `Paciente` es menor de edad, el padre/madre/tutor realiza el proceso y se registran los datos del responsable (`responsable_nombre`, `responsable_dni`) usando su correo electrónico.
- **Recursos**: DNI, datos personales (`nombre`, `apellido`, `telefono`, `email`, `fecha_nacimiento`), datos de responsable (si es menor), `diagnostico_presuntivo_id` (`Patología`), `historia_clinica` (texto o dictado mediante `Transcriptor de audio`), `tipo_sospecha` (`"clinica"` | `"familiar"`), lista de `Síntomas` (`SNOMED`), datos de `Familiares` y PDF de `Familiograma`.
- **Episodios**:
  1. El `Médico` selecciona o busca al `Paciente` por DNI para verificar que no exista previamente.
  2. El `Médico` registra los datos personales del `Paciente` y la `Historia clínica` (escribiéndola o mediante `Grabar historia clínica` con el `Transcriptor de audio`, ver Escenario 35).
  3. El `Médico` registra el diagnóstico presuntivo eligiendo una `Patología` y el `tipo_sospecha` (`"clinica"` o `"familiar"`).
  4. El `Médico` registra los `Síntomas` del `Paciente` codificados en `SNOMED` (ver Escenario 36) y, opcionalmente, la lista de `Familiares` (ver Escenarios 18 y 19).
  5. El sistema valida la correspondencia entre el diagnóstico presuntivo (`Patología`) y los `Síntomas` cargados (al menos 1 `Síntoma cardinal` o al menos 2 `Síntomas secundarios` de esa `Patología`).
  6. El sistema registra al `Usuario` (con `rol = Rol.PACIENTE` y `debe_cambiar_password = True`) y al `Paciente`, solicita el PDF a la `API de familiograma` si se cargaron `Familiares`, y envía por mail e inserta un `Aviso` con el usuario y la contraseña temporal inicial.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Médico` / `Gerente médico` | Sujeto LEL que atiende al `Paciente` en la consulta inicial e inicia el alta desde la interfaz médica. |
| `Paciente` | Sujeto LEL cuyos datos clínicos y familiares son registrados; recibe por correo sus credenciales iniciales (`debe_cambiar_password = True`). |
| `router` (`pacientes_router`) | Capa HTTP Flask (`POST /api/v1/pacientes`). Valida autenticación JWT/sesión, rol (`Rol.MEDICO` o `Rol.GERENTE_MEDICO`) y esquema del payload JSON. |
| `service` (`paciente_service`) | Capa de negocio que ejecuta la regla de validación clínica (`Patología` vs `Síntoma cardinal` / `Síntomas secundarios`), coordina el guardado y orquesta clientes externos. |
| `repo` (`paciente_repo`, `clinica_repo`, `usuario_repo`) | Capa de acceso a datos SQLAlchemy sobre `usuarios`, `pacientes`, `pacientes_sintomas`, `familiares`, `familiares_sintomas`, `patologias_sintomas`, `avisos`. |
| `clients` (`familiograma_client`, `snomed_client`, `notificacion_client`) | Clientes HTTP (`httpx`) hacia la `API de familiograma`, el buscador `SNOMED` y el servicio de envío de correos/avisos. |
| `PostgreSQL` | Base de datos relacional que garantiza integridad transaccional y unicidad de `usuarios.email` y `pacientes.dni`. |

---

## Prerequisites

- El usuario autenticado tiene sesión activa, no tiene `debe_cambiar_password = True` y posee `Usuario.rol in (Rol.MEDICO, Rol.GERENTE_MEDICO)` con perfil existente en la tabla `medicos` (`medicos.usuario_id == usuario.id`).
- Existe en la tabla `patologias` la `Patología` seleccionada como diagnóstico presuntivo (`patologias.id == diagnostico_presuntivo_id`), configurada previamente por un `Gerente médico` con su `Síntoma cardinal` (`es_cardinal = True`) y sus `Síntomas secundarios` (`es_cardinal = False`) en `patologias_sintomas`.
- Los `Síntomas` enviados existen o fueron sincronizados en la tabla `sintomas` (`snomed_id`, `descripcion`).
- No existe ningún registro en `pacientes` con el mismo `dni` ni en `usuarios` con el mismo `email`.

---

## Trigger

El `Médico` completa el formulario de alta de paciente en la vista de consulta médica y envía la solicitud:
- **Endpoint HTTP**: `POST /api/v1/pacientes` (autenticado con rol `medico` o `gerente_medico`).
- *(Previamente, de forma interactiva en el formulario, el `Médico` pudo invocar `GET /api/v1/snomed/sintomas?q=...` para buscar `Síntomas` y `POST /api/v1/transcripciones` para transcribir el audio de la `Historia clínica`).*

---

## Workflow Tree

### STEP 1: Autenticación, autorización de rol y validación estructural del payload
**Actor**: `router` (`pacientes_router`) -> `service` (`paciente_service`)
**Action**: Verifica el token/sesión activa del `Médico`, comprueba que el rol sea `Rol.MEDICO` o `Rol.GERENTE_MEDICO`, y valida que todos los campos obligatorios estén presentes y bien formados (`dni`, `nombre`, `apellido`, `telefono`, `email`, `fecha_nacimiento`, `diagnostico_presuntivo_id`, `historia_clinica`, `tipo_sospecha` en `{"clinica", "familiar"}`, `sintomas_snomed_ids` no vacío; y si la edad calculada a partir de `fecha_nacimiento` es menor a 18 años, `responsable_nombre` y `responsable_dni` obligatorios).
**Timeout**: `2s`
**Input**: Payload JSON de `POST /api/v1/pacientes` + contexto de sesión (`usuario_actual`).
**Output on SUCCESS**: DTO validado `DatosAltaPacienteDTO` + `medico_id` -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario autenticado no tiene rol `Rol.MEDICO` ni `Rol.GERENTE_MEDICO`, o no posee registro en `medicos` -> `return 403 Forbidden` con `{"ok": false, "error": "Solo un médico tratante o gerente médico puede dar de alta pacientes", "code": "FORBIDDEN_ROLE", "retryable": false}`. No requiere cleanup.
  - `FAILURE(validation_error)`: Falta algún campo obligatorio (por ejemplo `historia_clinica` vacía, `dni` inválido, `tipo_sospecha` distinto de `"clinica"`/`"familiar"`, o paciente menor de 18 años sin `responsable_nombre`/`responsable_dni`) -> `return 400 Bad Request` con detalle de campos inválidos (`code: "VALIDATION_ERROR"`). No requiere cleanup.

**Observable states during this step**:
  - **Customer/Actor (`Médico`) sees**: Indicador de carga `"Validando datos del paciente..."` en el botón de guardar.
  - **Operator sees**: Request HTTP entrante en el API Gateway / Flask server.
  - **Database**: Sin escrituras; lectura de `usuarios` y `medicos` para verificar sesión.
  - **Logs**: `[pacientes_router] STEP 1 iniciado medico_usuario_id=<id> dni=<dni>`

---

### STEP 2: Verificación de unicidad (`dni` y `email`) y validación clínica de `Síntomas` contra `Patología`
**Actor**: `service` (`paciente_service`) -> `repo` (`paciente_repo`, `clinica_repo`)
**Action**:
1. Consulta en `pacientes` si ya existe `pacientes.dni == input.dni` y en `usuarios` si ya existe `usuarios.email == input.email`.
2. Obtiene la `Patología` (`patologias.id == input.diagnostico_presuntivo_id`) junto con sus relaciones en `patologias_sintomas` y `sintomas`.
3. Verifica que los `snomed_id` recibidos en `sintomas_snomed_ids` existan en `sintomas` (o los sincroniza desde el catálogo local/SNOMED).
4. Aplica la regla de negocio del LEL: cuenta cuántos de los `Síntomas` del `Paciente` coinciden con el `Síntoma cardinal` (`patologias_sintomas.es_cardinal == True`) y cuántos coinciden con los `Síntomas secundarios` (`patologias_sintomas.es_cardinal == False`) de la `Patología` elegida. La validación es satisfactoria si y solo si:
   - `cantidad_cardinales >= 1` **O BIEN** `cantidad_secundarios >= 2`.
**Timeout**: `3s`
**Input**: `DatosAltaPacienteDTO`
**Output on SUCCESS**: Entidades `Patologia` y lista de `Sintoma` validadas -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(conflict)`: Ya existe un `Paciente` con ese `dni` o un `Usuario` con ese `email` -> `return 409 Conflict` (`{"ok": false, "error": "Ya existe un paciente registrado con ese DNI o email", "code": "PACIENTE_DUPLICADO", "retryable": false}`). No requiere cleanup.
  - `FAILURE(validation_error)`: `diagnostico_presuntivo_id` no existe en `patologias` -> `return 404 Not Found` (`code: "PATOLOGIA_NO_ENCONTRADA"`).
  - `FAILURE(validation_error)`: Los síntomas del paciente no cumplen la regla de correspondencia con la `Patología` (0 cardinales y menos de 2 secundarios de esa patología) -> `return 422 Unprocessable Entity` (`{"ok": false, "error": "Los síntomas seleccionados no corresponden al diagnóstico presuntivo: se requiere el síntoma cardinal o al menos dos síntomas secundarios de la patología", "code": "SINTOMAS_INCOMPATIBLES_PATOLOGIA", "retryable": false}`). No requiere cleanup.
  - `FAILURE(timeout)`: La consulta a `PostgreSQL` excede `3s` -> Reintento automático 1 vez con backoff de `500ms`; si persiste -> `return 503 Service Unavailable`.

**Observable states during this step**:
  - **Customer/Actor (`Médico`) sees**: Spinner de validación clínica; si falla por `SINTOMAS_INCOMPATIBLES_PATOLOGIA`, alerta roja en el formulario indicando que debe incluir el `Síntoma cardinal` o al menos dos `Síntomas secundarios` de la `Patología`.
  - **Operator sees**: Sin cambios en tablas persistidas.
  - **Database**: Lecturas (`SELECT`) en `usuarios`, `pacientes`, `patologias`, `patologias_sintomas`, `sintomas`.
  - **Logs**: `[paciente_service] STEP 2 validacion_clinica patologia_id=<id> cardinales=<n> secundarios=<m>`

---

### STEP 3: Persistencia transaccional de `Usuario`, `Paciente`, `PacienteSintoma` y `Familiar`
**Actor**: `service` (`paciente_service`) -> `repo` (`usuario_repo`, `paciente_repo`) -> `PostgreSQL`
**Action**: Dentro de una transacción de base de datos:
1. Genera una contraseña temporal aleatoria segura y calcula su `password_hash` (bcrypt/argon2).
2. Inserta una fila en `usuarios` con `email`, `password_hash`, `rol = Rol.PACIENTE`, `nombre`, `apellido`, `telefono`, `debe_cambiar_password = True`.
3. Inserta una fila en `pacientes` con `usuario_id = usuario.id`, `medico_id = medico.id`, `dni`, `fecha_nacimiento`, `diagnostico_presuntivo_id`, `historia_clinica`, `tipo_sospecha`, `familiograma_pdf_path = None`, `responsable_nombre`, `responsable_dni`.
4. Inserta las filas correspondientes en `pacientes_sintomas` (`paciente_id`, `sintoma_id`).
5. Si `input.familiares` no está vacío (Escenario 18), inserta cada fila en `familiares` (`paciente_id`, `parentesco`, `nombre`, `diagnostico_previo`) y sus síntomas en `familiares_sintomas` (`familiar_id`, `sintoma_id`). Si está vacío (Escenario 19), no inserta filas en `familiares`.
**Timeout**: `5s`
**Input**: `DatosAltaPacienteDTO`, `medico_id`, `password_temporal`
**Output on SUCCESS**: `paciente.id`, `usuario.id` (en sesión transaccional pendiente de confirmación o recién confirmada) -> `GO TO STEP 4`
**Output on FAILURE**:
  - `FAILURE(conflict)`: `IntegrityError` por carrera concurrente en `usuarios.email` o `pacientes.dni` -> `session.rollback()` -> `return 409 Conflict` (`code: "PACIENTE_DUPLICADO"`).
  - `FAILURE(timeout)` / `FAILURE(db_error)`: Error de conexión o timeout de base de datos -> `session.rollback()` -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Médico`) sees**: `"Guardando historia clínica y datos familiares..."`
  - **Operator sees**: Transacción activa en `PostgreSQL`.
  - **Database**: Filas creadas en `usuarios`, `pacientes`, `pacientes_sintomas` y opcionalmente `familiares` y `familiares_sintomas`.
  - **Logs**: `[paciente_repo] STEP 3 persistido paciente_id=<id> usuario_id=<uid> familiares_count=<k>`

---

### STEP 4: Generación y asociación del `Familiograma` vía `API de familiograma` (Condicional)
**Actor**: `service` (`paciente_service`) -> `clients` (`familiograma_client`) -> `API de familiograma`
**Action**:
- **Rama 4A (Sin familiares — Escenario 19)**: Si `input.familiares` es vacío (`[]`), omite la llamada externa, mantiene `pacientes.familiograma_pdf_path = None` y pasa directo a `STEP 5`.
- **Rama 4B (Con familiares — Escenario 18)**: Si `input.familiares` contiene al menos un `Familiar`, invoca `POST /api/v1/familiogramas` en la `API de familiograma` enviando los datos del `Paciente` y la lista de `Familiares` (parentesco, nombre, síntomas SNOMED, diagnóstico previo). Guarda el PDF devuelto en el almacenamiento local (`storage/familiogramas/paciente_<id>.pdf`) y actualiza `pacientes.familiograma_pdf_path`.
**Timeout**: `10s` por intento (máximo 3 intentos con exponential backoff: `1s`, `2s`, `4s`).
**Input**: `paciente`, lista de `familiares` con sus `sintomas`.
**Output on SUCCESS**: `familiograma_pdf_path` actualizado en `pacientes` (o `None` si no hay familiares) -> `GO TO STEP 5`
**Output on FAILURE**:
  - `FAILURE(transient_external_error)` / `FAILURE(timeout)`: La `API de familiograma` devuelve `5xx` o excede `10s` -> Reintentar hasta 2 veces adicionales (`1s`, `2s` backoff). Si agota reintentos -> `GO TO ABORT_CLEANUP` (revierte el alta para no dejar un paciente con familiares declarados pero sin familiograma generado, o devuelve error `502 Bad Gateway` con `retryable: true`).
  - `FAILURE(permanent_external_error)`: La `API de familiograma` rechaza el árbol familiar con `400/422` (parentesco inválido) -> `GO TO ABORT_CLEANUP` -> `return 422 Unprocessable Entity` (`code: "FAMILIOGRAMA_INVALIDO"`).

**Observable states during this step**:
  - **Customer/Actor (`Médico`) sees**: `"Generando familiograma en PDF..."` (si cargó familiares).
  - **Operator sees**: Llamada saliente hacia `API de familiograma`.
  - **Database**: `pacientes.familiograma_pdf_path = 'storage/familiogramas/paciente_<id>.pdf'` (si Rama 4B) o `NULL` (si Rama 4A).
  - **Logs**: `[familiograma_client] STEP 4 paciente_id=<id> status=200 pdf_path=<path>`

---

### STEP 5: Creación de `Aviso` y envío de correo con credenciales iniciales al `Paciente`
**Actor**: `service` (`paciente_service`) -> `repo` (`usuario_repo`) + `clients` (`notificacion_client`)
**Action**:
1. Inserta en la tabla `avisos` una notificación para el `Paciente` (`usuario_id = usuario.id`, `canal = CanalAviso.MAIL`, `mensaje = "Bienvenido al Laboratorio de Exoma Clínico. Debe cambiar su contraseña inicial en su primer ingreso."`).
2. Envía el correo electrónico al `email` del `Paciente` (o del padre/tutor si es menor) con el usuario (`email`) y la contraseña inicial temporal, indicando que el sistema exigirá `Cambiar contraseña inicial` en su primer ingreso.
3. Si el envío de mail tiene éxito, actualiza `avisos.enviado = True` y `avisos.enviado_en = func.now()`, y hace `COMMIT` definitivo.
**Timeout**: `5s` (con 2 reintentos de `1s` y `2s` ante fallo SMTP/HTTP).
**Input**: `usuario.id`, `usuario.email`, `password_temporal`
**Output on SUCCESS**: Respuesta `201 Created` con los datos del `Paciente` dado de alta -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(transient_mail_error)` / `FAILURE(timeout)`: El servidor de correo falla tras 2 reintentos -> Si el envío de credenciales iniciales es indispensable para que el paciente ingrese, se ejecuta `GO TO ABORT_CLEANUP` y se retorna `502 Bad Gateway` (`code: "MAIL_DELIVERY_FAILED", "retryable": true`) para que el `Médico` reintente sin dejar un usuario bloqueado sin contraseña conocida.

**Observable states during this step**:
  - **Customer/Actor (`Médico`) sees**: Pantalla de confirmación `"Paciente dado de alta exitosamente"` con botón para `"Dar de alta estudio"` para ese `Paciente`.
  - **Actor (`Paciente`) sees**: Correo electrónico en su bandeja de entrada con su usuario (`email`) y contraseña temporal.
  - **Operator sees**: Paciente activo en el listado y registro en `avisos` con `enviado = True`.
  - **Database**: `usuarios` (`debe_cambiar_password = True`), `pacientes` (`familiograma_pdf_path` poblado o `NULL`), `pacientes_sintomas`, `familiares`, `familiares_sintomas`, `avisos` (`enviado = True`, `enviado_en != NULL`).
  - **Logs**: `[paciente_service] STEP 5 completado paciente_id=<id> email_enviado=True`

---

### ABORT_CLEANUP: Reversión integral del alta de paciente
**Triggered by**: Fallos en `STEP 3`, `STEP 4` (fallo de `API de familiograma` tras reintentos) o `STEP 5` (imposibilidad de enviar credenciales iniciales).
**Actions** (en orden inverso a la creación):
  1. Si se escribió un archivo PDF en disco (`storage/familiogramas/paciente_<id>.pdf`) en `STEP 4`, eliminar el archivo físico del sistema de archivos.
  2. Hacer `ROLLBACK` de la transacción en `PostgreSQL` (o eliminar en cascada `avisos`, `familiares_sintomas`, `familiares`, `pacientes_sintomas`, `pacientes` y `usuarios` creados en `STEP 3`).
  3. Registrar en el log de errores la causa raíz y devolver al `Médico` la respuesta HTTP de error estructurada.
**What customer (`Médico`) sees**: Mensaje de error claro indicando el motivo del fallo y permitiendo reintentar el envío del formulario sin perder los datos cargados en pantalla.
**What operator sees**: Alerta de fallo en logs con `code` específico; 0 registros huérfanos en `usuarios` o `pacientes`.

---

## State Transitions

```
[Paciente No Registrado]
   |-- (STEP 1-2 fallan: rol inválido, datos faltantes, DNI/email duplicado o síntomas incompatibles con Patología)
   |       --> [Rechazado sin cambios en BD (400 / 403 / 409 / 422)]
   |
   |-- (STEP 3-5 tienen éxito con familiares)
   |       --> [Usuario creado (rol=PACIENTE, debe_cambiar_password=True)]
   |       --> [Paciente activo con familiograma_pdf_path != NULL]
   |
   |-- (STEP 3-5 tienen éxito sin familiares - Escenario 19)
   |       --> [Usuario creado (rol=PACIENTE, debe_cambiar_password=True)]
   |       --> [Paciente activo con familiograma_pdf_path = NULL]
   |
   +-- (STEP 4 o STEP 5 fallan tras reintentos -> ABORT_CLEANUP)
           --> [Rollback completo -> Paciente No Registrado]
```

*(Nota: Este escenario no modifica `EstadoEstudio` ya que el `Estudio` se crea recién en el Escenario 2 en estado `EstadoEstudio.CREADO`).*

---

## Handoff Contracts

### 1. Frontend Médico -> Backend (`router` -> `service`)
**Endpoint**: `POST /api/v1/pacientes`
**Payload**:
```json
{
  "dni": "string — DNI único del paciente (ej. '40123456')",
  "nombre": "string — Nombre del paciente",
  "apellido": "string — Apellido del paciente",
  "telefono": "string — Teléfono de contacto",
  "email": "string — Correo electrónico del paciente (o del padre si es menor)",
  "fecha_nacimiento": "string (YYYY-MM-DD) — Fecha de nacimiento",
  "diagnostico_presuntivo_id": "integer — ID de la Patología en tabla patologias",
  "historia_clinica": "string — Resumen clínico (escrito o transcripto por audio)",
  "tipo_sospecha": "string — 'clinica' | 'familiar'",
  "responsable_nombre": "string | null — Obligatorio si es menor de 18 años",
  "responsable_dni": "string | null — Obligatorio si es menor de 18 años",
  "sintomas_snomed_ids": [
    "string — Código SNOMED de cada síntoma del paciente (ej. '25064002')"
  ],
  "familiares": [
    {
      "parentesco": "string — Ej. 'padre', 'madre', 'hermano', 'primo'",
      "nombre": "string — Nombre completo del familiar",
      "diagnostico_previo": "string | null — Diagnóstico previo si lo tiene",
      "sintomas_snomed_ids": [
        "string — Código SNOMED de síntomas del familiar"
      ]
    }
  ]
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "paciente_id": 42,
    "usuario_id": 105,
    "dni": "40123456",
    "nombre": "Juan",
    "apellido": "Pérez",
    "email": "juan.perez@example.com",
    "diagnostico_presuntivo_id": 1,
    "tipo_sospecha": "clinica",
    "familiograma_pdf_path": "storage/familiogramas/paciente_42.pdf",
    "debe_cambiar_password": true
  }
}
```
**Failure response** (`400` / `403` / `409` / `422` / `502`):
```json
{
  "ok": false,
  "error": "Los síntomas seleccionados no corresponden al diagnóstico presuntivo: se requiere el síntoma cardinal o al menos dos síntomas secundarios de la patología",
  "code": "SINTOMAS_INCOMPATIBLES_PATOLOGIA",
  "retryable": false
}
```
**Timeout**: `15s`
**ON FAILURE**: Si ocurre antes de `STEP 3`, retorno inmediato sin efectos secundarios; si ocurre en `STEP 4` o `STEP 5`, ejecuta `ABORT_CLEANUP`.

---

### 2. Backend (`familiograma_client`) -> `API de familiograma`
**Endpoint**: `POST /api/v1/familiogramas`
**Payload**:
```json
{
  "paciente": {
    "dni": "40123456",
    "nombre": "Juan Pérez",
    "fecha_nacimiento": "1995-04-12",
    "diagnostico_presuntivo": "Fabry",
    "sintomas": ["25064002", "102498003"]
  },
  "familiares": [
    {
      "parentesco": "primo",
      "nombre": "Carlos Pérez",
      "diagnostico_previo": "Fabry",
      "sintomas": ["25064002"]
    }
  ]
}
```
**Success response** (`200 OK`):
- Cuerpo binario `application/pdf` o JSON `{"ok": true, "pdf_base64": "JVBERi0xLjQK..."}`.
**Failure response**:
```json
{
  "ok": false,
  "error": "Servicio de generación de familiograma no disponible temporalmente",
  "code": "FAMILIOGRAMA_SERVICE_ERROR",
  "retryable": true
}
```
**Timeout**: `10s` por intento (hasta 3 intentos con backoff `1s`, `2s`, `4s`).
**ON FAILURE**: Reintentar si `retryable == true`; si falla definitivamente, invocar `ABORT_CLEANUP`.

---

### 3. Backend (`snomed_client`) -> `SNOMED` (Consulta de autocompletado previa/auxiliar)
**Endpoint**: `GET /api/v1/snomed/conceptos?search={prefijo_3_letras}`
**Payload**: Query param `search` (mínimo 3 caracteres, ej. `cef`).
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "items": [
    {
      "snomed_id": "25064002",
      "descripcion": "Cefalea"
    }
  ]
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "Timeout consultando servidor SNOMED",
  "code": "SNOMED_TIMEOUT",
  "retryable": true
}
```
**Timeout**: `3s`
**ON FAILURE**: Degradación elegante consultando la caché local en la tabla `sintomas` (`SELECT id, snomed_id, descripcion FROM sintomas WHERE descripcion ILIKE 'cef%'`).

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Registro en `usuarios` (`rol=PACIENTE`) | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` / `DELETE FROM usuarios WHERE id = :uid` |
| Registro en `pacientes` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` (cascada desde `usuarios`) |
| Registros en `pacientes_sintomas` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` (cascada `ondelete="CASCADE"`) |
| Registros en `familiares` y `familiares_sintomas` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` (cascada `ondelete="CASCADE"`) |
| Archivo PDF en `storage/familiogramas/paciente_<id>.pdf` | STEP 4 | `ABORT_CLEANUP` | `os.remove(familiograma_pdf_path)` si existe en disco |
| Registro en `avisos` | STEP 5 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | Los modelos SQLAlchemy en `app/src/core/models/perfiles.py` (`Paciente`, `Medico`), `usuarios.py` (`Usuario`, `Aviso`) y `clinica.py` (`Patologia`, `Sintoma`, `PatologiaSintoma`, `PacienteSintoma`, `Familiar`, `FamiliarSintoma`) ya existen y soportan todos los campos requeridos, incluyendo `familiograma_pdf_path` nullable y `responsable_nombre`/`responsable_dni`. | Low | Database & Prerequisites | Alineado 100% con los nombres exactos de tablas y columnas de `app/src/core/models/`. |
| RC-2 | En `clinica.py`, `PatologiaSintoma` tiene restricción parcial única `uq_un_cardinal_por_patologia` (`es_cardinal = True`), garantizando a nivel de esquema que exista a lo sumo un `Síntoma cardinal` por `Patología`. | Low | STEP 2 | Documentado en STEP 2. |
| RC-3 | Las capas `router`, `service`, `repo` y `clients` aún no están implementadas en `app/src/`. | Medium | Actors & Handoff Contracts | Especificadas las responsabilidades exactas de cada capa para su implementación SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path con síntoma cardinal y familiares** | `POST /api/v1/pacientes` por un `Médico` con datos válidos, 1 `Síntoma cardinal` de la `Patología` y 2 `Familiares`. | Retorna `201 Created`; crea `Usuario` (`debe_cambiar_password=True`), `Paciente`, `PacienteSintoma`, `Familiar`; invoca `API de familiograma`, guarda `familiograma_pdf_path` y envía mail inicial (`Aviso`). |
| **TC-02: Happy path con dos síntomas secundarios y sin familiares (Escenario 19)** | `POST /api/v1/pacientes` con 0 síntomas cardinales, 2 `Síntomas secundarios` de la `Patología` y `familiares: []`. | Retorna `201 Created`; `familiograma_pdf_path` queda en `None`; no se invoca `API de familiograma`; se crean `Usuario` y `Paciente`. |
| **TC-03: Rechazo por síntomas incompatibles con la patología** | `POST /api/v1/pacientes` con solo 1 `Síntoma secundario` y 0 cardinales para la `Patología` indicada. | Retorna `422 Unprocessable Entity` con `code: "SINTOMAS_INCOMPATIBLES_PATOLOGIA"`; 0 filas creadas en `usuarios` y `pacientes`. |
| **TC-04: Conflicto por DNI o email duplicado** | `POST /api/v1/pacientes` con un `dni` o `email` que ya existe en la base de datos. | Retorna `409 Conflict` con `code: "PACIENTE_DUPLICADO"`; no modifica el registro existente. |
| **TC-05: Usuario sin rol Médico ni Gerente médico** | `POST /api/v1/pacientes` invocado por un `Administrativo` o `Paciente`. | Retorna `403 Forbidden` con `code: "FORBIDDEN_ROLE"`. |
| **TC-06: Paciente menor de edad sin datos del padre/responsable** | `POST /api/v1/pacientes` con `fecha_nacimiento` de hace 3 meses y `responsable_nombre = null`. | Retorna `400 Bad Request` con `code: "VALIDATION_ERROR"` exigiendo los datos del padre/responsable. |
| **TC-07: Fallo permanente o timeout agotado en API de familiograma** | `POST /api/v1/pacientes` con familiares cuando la `API de familiograma` devuelve `503` en los 3 intentos. | Ejecuta `ABORT_CLEANUP`, hace rollback de `Usuario`, `Paciente` y `Familiar`, y retorna `502 Bad Gateway` (`retryable: true`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Cuando `tipo_sospecha == "familiar"` (primo asintomático derivado por estudio positivo de familiar), el formulario o las reglas de la patología siguen requiriendo validar la carga según el episodio 5 del Escenario 1 y el episodio 5 del Escenario 36. | `.ai/2-Glosario_LEL.md` (`Dar de alta paciente`, `Síntoma cardinal`, `Síntoma secundario`) y `.ai/3-Escenarios.md` (Escenarios 1 y 36). | Si para sospecha familiar se eximiera la regla de síntomas, requeriría un bypass explícito en STEP 2. |
| A2 | La contraseña inicial del paciente se genera aleatoriamente y se envía por mail junto con la marca `usuarios.debe_cambiar_password = True`. | `app/src/core/models/usuarios.py` línea 30 y `.ai/2-Glosario_LEL.md`. | Bajo. |

## Open Questions

- ¿Existe un tamaño máximo en bytes para el PDF devuelto por la `API de familiograma` antes de guardarlo en el sistema de archivos local?

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/usuarios.py`, `perfiles.py` y `clinica.py`. | Marcada como `Approved`. |
