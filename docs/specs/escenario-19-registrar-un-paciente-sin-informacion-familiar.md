# WORKFLOW: Escenario 19 – Registrar un paciente sin información familiar
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-19`

### Símbolos LEL utilizados

| Categoría | Símbolos LEL exactos |
|---|---|
| **Sujetos** | `Médico` (sinónimos: médico tratante, médico derivante), `Paciente` |
| **Objetos** | `Patología`, `Historia clínica`, `Síntoma`, `Síntoma cardinal`, `Síntoma secundario`, `SNOMED`, `Familiar`, `Familiograma`, `API de familiograma`, `Aviso` |
| **Verbos** | `Dar de alta paciente`, `Cargar síntomas` |
| **Estados** | *(No aplica transición de estado de `Estudio`; impacta en el alta de `Usuario` con `debe_cambiar_password = True` y `Paciente` con `familiograma_pdf_path = None`)* |

---

## Overview

- **Objetivo**: Continuar el registro de un **paciente** cuando no existen datos familiares.
- **Contexto**: El **paciente** no dispone de información familiar para registrar (o decide no brindarla durante la consulta médica inicial).
- **Recursos**: Datos personales, datos clínicos (`dni`, `nombre`, `apellido`, `telefono`, `email`, `fecha_nacimiento`, `diagnostico_presuntivo_id`, `historia_clinica`, `sintomas`, `tipo_sospecha`, datos de responsable si es menor de edad).
- **Episodios**:
  1. El **médico** indica que no existe información familiar (`sin_informacion_familiar = true`, lista `familiares = []`).
  2. El sistema mantiene vacía la sección familiar.
  3. El sistema no crea **familiares** para el **paciente** ni invoca la **API de familiograma**.
  4. El registro del **paciente** continúa, persistiendo el **paciente** con `familiograma_pdf_path = NULL` y enviando las credenciales iniciales por correo electrónico.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Médico` (Sujeto LEL) | Profesional autenticado (`Rol.MEDICO` o `Rol.GERENTE_MEDICO`) que ejecuta `Dar de alta paciente` indicando ausencia de datos familiares. |
| `Paciente` (Sujeto LEL) | Persona para quien se registra la ficha clínica y a quien se envían las credenciales iniciales de acceso (`debe_cambiar_password = True`). |
| `pacientes_router` (`app/src/routers/`) | Capa `router`: valida sesión, rol y esquema del payload de alta sin información familiar. |
| `paciente_service` (`app/src/services/`) | Capa `service`: valida mayoría de edad/responsable, regla clínica de **síntoma cardinal** o 2 **síntomas secundarios** contra la **patología**, omite la llamada a la **API de familiograma**, genera contraseña inicial y coordina el envío de credenciales. |
| `paciente_repo` / `clinica_repo` (`app/src/repos/`) | Capa `repo`: consulta `patologias`, `patologias_sintomas`, `usuarios`, `pacientes` y persiste `Usuario`, `Paciente`, `PacienteSintoma` y `Aviso` en una única transacción sin insertar filas en `familiares`. |
| `notificacion_client` (`app/src/clients/`) | Capa `clients`: envía el correo electrónico con usuario (`email`) y contraseña inicial al **paciente** (o a su padre/responsable si es menor). |
| `PostgreSQL` | Base de datos relacional que almacena `usuarios`, `pacientes`, `pacientes_sintomas` y `avisos`, manteniendo `familiares` sin registros y `pacientes.familiograma_pdf_path = NULL`. |

---

## Prerequisites

- El **médico** ha iniciado sesión (`Rol.MEDICO` o `Rol.GERENTE_MEDICO`) y posee registro válido en la tabla `medicos` asociado a `usuarios.id`.
- La **patología** seleccionada como diagnóstico presuntivo existe en la tabla `patologias` y tiene configurados su **síntoma cardinal** (`es_cardinal = True`) y sus **síntomas secundarios** (`es_cardinal = False`) en `patologias_sintomas`.
- Los **síntomas** seleccionados por el **médico** fueron previamente buscados/codificados mediante **SNOMED** y existen en la tabla `sintomas`.
- No existe otro registro en `pacientes` con el mismo `dni` ni otro registro en `usuarios` con el mismo `email`.

---

## Trigger

El **médico** marca explícitamente la opción "Sin información familiar" (o envía `sin_informacion_familiar: true` y `familiares: []`) y confirma el formulario de `Dar de alta paciente`.
- **Endpoint HTTP**: `POST /api/v1/pacientes`

---

## Workflow Tree

### STEP 1: Validación de sesión, rol y datos obligatorios con sección familiar vacía
**Actor**: `pacientes_router` -> `paciente_service`
**Action**: Verifica el token de sesión del **médico**, comprueba que tenga rol `Rol.MEDICO` o `Rol.GERENTE_MEDICO`, valida la presencia de todos los campos obligatorios del **paciente** (`dni`, `nombre`, `apellido`, `telefono`, `email`, `fecha_nacimiento`, `diagnostico_presuntivo_id`, `historia_clinica`, `tipo_sospecha`, `sintomas_ids`) y verifica la consistencia del indicador `sin_informacion_familiar = true` con `familiares = []`. Si `fecha_nacimiento` indica que el **paciente** es menor de 18 años, exige `responsable_nombre` y `responsable_dni`.
**Timeout**: `2s`
**Input**:
`{ dni: str, nombre: str, apellido: str, telefono: str, email: str, fecha_nacimiento: date, diagnostico_presuntivo_id: int, historia_clinica: str, tipo_sospecha: str, sintomas_ids: list[int], sin_informacion_familiar: bool, familiares: list[dict], responsable_nombre: Optional[str], responsable_dni: Optional[str] }`
**Output on SUCCESS**: Payload validado con `familiares = []` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario autenticado no tiene `Rol.MEDICO` ni `Rol.GERENTE_MEDICO` -> retorna `403 Forbidden` (`code: "ROL_NO_AUTORIZADO"`), sin efectos secundarios.
  - `FAILURE(validation_error)`: Falta algún dato obligatorio (todo es obligatorio salvo el **familiograma**), `tipo_sospecha` no pertenece a `{"clinica", "familiar"}`, es menor de 18 años sin datos de responsable, o se envió `sin_informacion_familiar = true` junto con una lista `familiares` no vacía -> retorna `400 Bad Request` (`code: "DATOS_PACIENTE_INVALIDOS"`), sin limpieza necesaria.
  - `FAILURE(timeout)`: Excede `2s` al validar sesión -> retorna `504 Gateway Timeout` (`retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: Indicador "Validando datos del paciente..." con la sección "Grupo familiar" deshabilitada/vacía.
  - Operator sees: Solicitud entrante `POST /api/v1/pacientes` en curso.
  - Database: Sin escrituras en `usuarios`, `pacientes` ni `familiares`.
  - Logs: `[paciente_service] step_1_validar_alta_sin_familiares medico_id=<id> dni=<dni> sin_informacion_familiar=True`

---

### STEP 2: Verificación de unicidad y validación clínica de síntomas contra la patología
**Actor**: `paciente_service` -> `paciente_repo` / `clinica_repo` -> `PostgreSQL`
**Action**:
1. Verifica en `pacientes` que no exista el `dni` y en `usuarios` que no exista el `email`.
2. Consulta la **patología** (`patologias.id = diagnostico_presuntivo_id`) y sus relaciones en `patologias_sintomas`.
3. Valida que el conjunto `sintomas_ids` del **paciente** incluya al menos el **síntoma cardinal** (`PatologiaSintoma.es_cardinal == True`) o al menos dos **síntomas secundarios** (`PatologiaSintoma.es_cardinal == False`) pertenecientes a la **patología** sospechada.
**Timeout**: `3s`
**Input**: `{ dni: str, email: str, diagnostico_presuntivo_id: int, sintomas_ids: list[int] }`
**Output on SUCCESS**: Unicidad y regla clínica verificadas -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(conflict)`: Ya existe un `Paciente` con el mismo `dni` o un `Usuario` con el mismo `email` -> retorna `409 Conflict` (`code: "PACIENTE_O_EMAIL_DUPLICADO"`), sin limpieza necesaria.
  - `FAILURE(validation_error)`: La **patología** no existe (`404 Not Found`, `code: "PATOLOGIA_NO_ENCONTRADA"`) o los **síntomas** cargados no cumplen la regla de validación clínica (ni 1 **síntoma cardinal** ni 2 **síntomas secundarios** de la **patología**) -> retorna `422 Unprocessable Entity` (`code: "SINTOMAS_INCOMPATIBLES_CON_PATOLOGIA"`), impidiendo dar de alta al **paciente**.
  - `FAILURE(timeout)`: Consulta a `PostgreSQL` supera `3s` -> reintenta 1 vez con backoff de `500ms`; si persiste, retorna `503 Service Unavailable`.

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: Indicador "Validando compatibilidad clínica con la patología sospechada...".
  - Operator sees: Consulta activa sobre `patologias_sintomas`, `pacientes` y `usuarios`.
  - Database: Lecturas en `usuarios`, `pacientes`, `patologias`, `patologias_sintomas`, `sintomas`. Cero filas nuevas.
  - Logs: `[paciente_service] step_2_validar_sintomas_patologia patologia_id=<id> cardinal_presente=<bool> secundarios_count=<n>`

---

### STEP 3: Persistencia atómica de `Usuario`, `Paciente` y `PacienteSintoma` sin crear `Familiar` ni `Familiograma`
**Actor**: `paciente_service` -> `paciente_repo` -> `PostgreSQL`
**Action**:
1. Genera una contraseña temporal aleatoria segura y calcula su `password_hash`.
2. Inserta en `usuarios` una fila con `email`, `password_hash`, `rol = Rol.PACIENTE`, `nombre`, `apellido`, `telefono`, `debe_cambiar_password = True`.
3. Inserta en `pacientes` una fila con `usuario_id`, `medico_id`, `dni`, `fecha_nacimiento`, `diagnostico_presuntivo_id`, `historia_clinica`, `tipo_sospecha`, `familiograma_pdf_path = None`, `responsable_nombre`, `responsable_dni`.
4. Inserta en `pacientes_sintomas` las filas `(paciente_id, sintoma_id)` correspondientes a los **síntomas** seleccionados.
5. **Omite explícitamente** cualquier inserción en `familiares` y `familiares_sintomas`, y **no invoca** a la **API de familiograma**.
**Timeout**: `5s`
**Input**: Datos validados de `Usuario`, `Paciente` y `sintomas_ids`.
**Output on SUCCESS**: `{ usuario_id: int, paciente_id: int, password_inicial_plana: str, familiograma_pdf_path: None }` -> GO TO STEP 4
**Output on FAILURE**:
  - `FAILURE(conflict)`: Violación concurrente de constraint `UNIQUE(dni)` en `pacientes` o `UNIQUE(email)` en `usuarios` -> rollback automático de la transacción SQL -> retorna `409 Conflict` (`code: "CONFLICTO_ALTA_CONCURRENTE"`).
  - `FAILURE(timeout)`: Lock o timeout de base de datos mayor a `5s` -> rollback de transacción -> `ABORT_CLEANUP`.

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: "Guardando ficha del paciente sin antecedentes familiares...".
  - Operator sees: Transacción abierta en `PostgreSQL`.
  - Database:
    - `usuarios`: nueva fila con `rol = 'PACIENTE'`, `debe_cambiar_password = true`.
    - `pacientes`: nueva fila con `familiograma_pdf_path = NULL`.
    - `pacientes_sintomas`: N filas asociadas a `pacientes.id`.
    - `familiares`: `0` filas para `paciente_id`.
  - Logs: `[paciente_repo] step_3_persistir_paciente_sin_familiares paciente_id=<id> usuario_id=<id> familiares_creados=0 familiograma_pdf_path=None`

---

### STEP 4: Envío de credenciales iniciales por correo electrónico y registro de aviso
**Actor**: `paciente_service` -> `notificacion_client` + `paciente_repo`
**Action**:
1. Registra un `Aviso` en la tabla `avisos` (`usuario_id`, `canal = CanalAviso.MAIL`, `mensaje = "Alta de paciente y envío de credenciales iniciales"`, `enviado = False`).
2. Envía el correo electrónico al `email` del **paciente** con su usuario y contraseña temporal indicando que deberá cambiarla en su primer ingreso (`Cambiar contraseña inicial`).
3. Si el envío SMTP/HTTP tiene éxito, actualiza `avisos.enviado = True`, `avisos.enviado_en = now()` y hace `COMMIT` definitivo.
**Timeout**: `8s` (con hasta 2 reintentos con backoff exponencial `1s`, `2s`)
**Input**: `{ usuario_id: int, paciente_id: int, email: str, nombre: str, password_inicial_plana: str }`
**Output on SUCCESS**: `{ paciente_id: int, usuario_id: int, familiograma_pdf_path: null, familiares: [], credenciales_enviadas: true }` -> Retorna `201 Created` y habilita continuar con `Dar de alta estudio`.
**Output on FAILURE**:
  - `FAILURE(transient_external_error)`: Fallo de red o timeout en `notificacion_client` -> reintenta hasta 2 veces (`1s`, `2s`). Si tras los reintentos falla permanentemente -> ejecuta `ABORT_CLEANUP` para no dejar un `Usuario` sin credenciales entregadas.
  - `FAILURE(permanent_external_error)`: Dirección de correo rechazada por el proveedor (`550 Invalid recipient`) -> ejecuta `ABORT_CLEANUP` y retorna `422 Unprocessable Entity` (`code: "EMAIL_NO_ENTREGABLE"`).

**Observable states during this step**:
  - Customer/Actor (`Médico`) sees: Confirmación "Paciente registrado correctamente sin información familiar. Puede continuar con el alta del estudio."
  - Customer/Actor (`Paciente`) sees: Correo electrónico recibido con usuario (`email`) y contraseña inicial.
  - Operator sees: `avisos.enviado = true` para el nuevo `usuario_id`.
  - Database: `usuarios`, `pacientes` (`familiograma_pdf_path = NULL`), `pacientes_sintomas` y `avisos` (`enviado = true`) confirmados; `familiares` vacío (`0` filas).
  - Logs: `[notificacion_client] step_4_credenciales_enviadas usuario_id=<id> paciente_id=<id>`

---

### ABORT_CLEANUP: Reversión de alta de paciente por fallo en entrega de credenciales o persistencia
**Triggered by**: Fallo permanente en `STEP 3` o fallo tras reintentos en `STEP 4`.
**Actions** (in order):
  1. Si la transacción de base de datos sigue abierta, ejecutar `ROLLBACK`.
  2. Si `usuarios` y `pacientes` ya habían sido persistidos en sesión previa al fallo de `notificacion_client`, eliminar `Aviso`, `PacienteSintoma`, `Paciente` y `Usuario` (`ON DELETE CASCADE` desde `usuarios.id`).
  3. Registrar evento de error en logs de auditoría.
**What customer (`Médico`) sees**: Mensaje de error claro en la interfaz ("No se pudo completar el registro del paciente ni enviar sus credenciales iniciales. Intente nuevamente.") conservando los datos cargados en el formulario.
**What operator sees**: Alerta de fallo en `notificacion_client` o `PostgreSQL` sin registros huérfanos en `usuarios` ni `pacientes`.

---

## State Transitions

```
[No registrado] -> (STEP 1-4 exitosos con sin_informacion_familiar=True) -> [Paciente registrado (pacientes.familiograma_pdf_path = NULL, familiares = 0 filas, usuarios.debe_cambiar_password = True)]
[No registrado] -> (Fallo de validación en STEP 1 o STEP 2) -> [No registrado (sin efectos en BD)]
[En persistencia] -> (Fallo en STEP 3 o STEP 4 -> ABORT_CLEANUP) -> [No registrado (rollback completo)]
```

---

## Handoff Contracts

### 1. Frontend (`Médico`) -> Backend (`pacientes_router`)
**Endpoint**: `POST /api/v1/pacientes`
**Payload**:
```json
{
  "dni": "40111222",
  "nombre": "Lucía",
  "apellido": "Fernández",
  "telefono": "+5492215550101",
  "email": "lucia.fernandez@example.com",
  "fecha_nacimiento": "1997-04-15",
  "diagnostico_presuntivo_id": 1,
  "historia_clinica": "Paciente derivada por acroparestesias recurrentes sin datos de su grupo familiar.",
  "tipo_sospecha": "clinica",
  "sintomas_ids": [10, 14],
  "sin_informacion_familiar": true,
  "familiares": [],
  "responsable_nombre": null,
  "responsable_dni": null
}
```
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "paciente_id": 42,
    "usuario_id": 108,
    "dni": "40111222",
    "email": "lucia.fernandez@example.com",
    "diagnostico_presuntivo_id": 1,
    "tipo_sospecha": "clinica",
    "sin_informacion_familiar": true,
    "familiares_count": 0,
    "familiograma_pdf_path": null,
    "debe_cambiar_password": true
  }
}
```
**Failure response** (`400` / `403` / `409` / `422` / `503`):
```json
{
  "ok": false,
  "error": "Los síntomas seleccionados no cumplen el criterio clínico de la patología (1 síntoma cardinal o 2 secundarios).",
  "code": "SINTOMAS_INCOMPATIBLES_CON_PATOLOGIA",
  "retryable": false
}
```
**Timeout**: `15s`
**ON FAILURE**: Si `retryable == true`, el cliente puede reintentar; si es `400/409/422`, corregir los datos ingresados.

### 2. `paciente_service` -> `notificacion_client` (Servicio de Correo)
**Endpoint**: `POST /internal/mail/send` (o cliente SMTP configurado)
**Payload**:
```json
{
  "to": "lucia.fernandez@example.com",
  "subject": "Credenciales de acceso – Laboratorio de Exoma Clínico",
  "template": "alta_paciente_credenciales",
  "variables": {
    "nombre_completo": "Lucía Fernández",
    "usuario": "lucia.fernandez@example.com",
    "password_inicial": "Tmp#98aB!2",
    "requiere_cambio_password": true
  }
}
```
**Success response**:
```json
{
  "ok": true,
  "message_id": "msg-20261028-0042"
}
```
**Failure response**:
```json
{
  "ok": false,
  "error": "SMTP timeout connecting to relay",
  "code": "MAIL_DELIVERY_TIMEOUT",
  "retryable": true
}
```
**Timeout**: `8s`
**ON FAILURE**: Reintentar hasta 2 veces con backoff (`1s`, `2s`); si fracasa, ejecutar `ABORT_CLEANUP`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Fila en `usuarios` (`Rol.PACIENTE`) | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` transaccional o `DELETE FROM usuarios WHERE id = :usuario_id` |
| Fila en `pacientes` (`familiograma_pdf_path = NULL`) | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` transaccional / `ON DELETE CASCADE` desde `usuarios` |
| Filas en `pacientes_sintomas` | Step 3 | `ABORT_CLEANUP` | `ROLLBACK` transaccional / `ON DELETE CASCADE` desde `pacientes` |
| Fila en `avisos` | Step 4 | `ABORT_CLEANUP` | `ROLLBACK` transaccional / `ON DELETE CASCADE` desde `usuarios` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/perfiles.py` (línea 71), `Paciente.familiograma_pdf_path` está definido como `Mapped[Optional[str]] = mapped_column(String(500))` con comentario explícito `# PDF devuelto por la API de familiograma (puede no existir, escenario 19)`. | Low | Overview / STEP 3 | Alineado 100% con el modelo SQLAlchemy existente (`familiograma_pdf_path = None`). |
| RC-2 | En `app/src/core/models/clinica.py`, la relación `Paciente.familiares` permite 0 elementos sin restricción mínima. | Low | STEP 3 | Confirmado: la tabla `familiares` permanece con 0 filas para `paciente_id`. |
| RC-3 | No existen aún los módulos `app/src/routers/pacientes.py`, `app/src/services/paciente_service.py` ni `app/src/repos/paciente_repo.py`. | Medium | Actors / Handoff Contracts | Documentado como pendiente de implementación siguiendo este contrato en el flujo SDD. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Alta de paciente sin información familiar con síntoma cardinal | `POST /api/v1/pacientes` con `sin_informacion_familiar=True`, `familiares=[]` y 1 **síntoma cardinal** de la **patología** | Retorna `201 Created`; crea `Usuario` (`debe_cambiar_password=True`) y `Paciente` (`familiograma_pdf_path=None`); `0` filas en `familiares`; no llama a `API de familiograma`; envía mail con credenciales. |
| `TC-02`: Happy path – Alta sin información familiar con 2 síntomas secundarios | `POST /api/v1/pacientes` con `sin_informacion_familiar=True`, `familiares=[]` y 2 **síntomas secundarios** de la **patología** | Retorna `201 Created`; `familiograma_pdf_path=None`; `0` filas en `familiares`. |
| `TC-03`: Contradicción entre flag y lista de familiares | `POST /api/v1/pacientes` con `sin_informacion_familiar=True` y `familiares=[{"nombre": "Juan", "parentesco": "padre"}]` | Retorna `400 Bad Request` (`code: "DATOS_PACIENTE_INVALIDOS"`); no persiste nada en BD. |
| `TC-04`: Fallo de validación clínica de síntomas | `POST /api/v1/pacientes` con `sin_informacion_familiar=True` pero solo 1 **síntoma secundario** y ningún **síntoma cardinal** | Retorna `422 Unprocessable Entity` (`code: "SINTOMAS_INCOMPATIBLES_CON_PATOLOGIA"`); no crea `Usuario` ni `Paciente`. |
| `TC-05`: Paciente menor de edad sin datos del padre/responsable | `POST /api/v1/pacientes` con `fecha_nacimiento` < 18 años y `responsable_dni=None` | Retorna `400 Bad Request` (`code: "DATOS_PACIENTE_INVALIDOS"`). |
| `TC-06`: DNI o correo electrónico duplicado | `POST /api/v1/pacientes` con `dni` o `email` ya existente en `pacientes` / `usuarios` | Retorna `409 Conflict` (`code: "PACIENTE_O_EMAIL_DUPLICADO"`). |
| `TC-07`: Usuario sin rol de médico intenta dar de alta | `POST /api/v1/pacientes` autenticado como `Rol.ADMINISTRATIVO` o `Rol.PACIENTE` | Retorna `403 Forbidden` (`code: "ROL_NO_AUTORIZADO"`). |
| `TC-08`: Fallo permanente en servicio de correo dispara `ABORT_CLEANUP` | `POST /api/v1/pacientes` cuando `notificacion_client` falla en los 3 intentos | Ejecuta `ABORT_CLEANUP`, revierte `Usuario`, `Paciente`, `PacienteSintoma` y `Aviso`, y retorna error `503`/`422`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El alta de un **paciente** con información familiar (Escenario 18) y sin información familiar (Escenario 19) comparten el endpoint `POST /api/v1/pacientes`, diferenciándose por `sin_informacion_familiar: true` y `familiares: []`. | `.ai/1-Entrevista.md` (líneas 113-116, 247-249) y `app/src/core/models/perfiles.py` | Bajo: si el frontend usa un endpoint dedicado o el mismo, el servicio aplica la misma regla de omitir `Familiar` y `API de familiograma`. |
| A2 | Aunque `tipo_sospecha` sea `"familiar"`, el **paciente** puede negarse a dar los datos identificatorios de sus parientes, por lo que `sin_informacion_familiar = true` es válido tanto para sospecha `"clinica"` como `"familiar"`. | `.ai/1-Entrevista.md` (líneas 111-116) | Bajo. |

## Open Questions

- ¿Se desea registrar en auditoría si la ausencia de información familiar se debió a desconocimiento del **paciente** (ej. adoptado) o a negativa expresa de compartir datos de parientes, o basta con mantener la sección vacía (`familiares = []` y `familiograma_pdf_path = NULL`)? *(Por ahora el LEL y la entrevista indican que basta con dejar la sección vacía).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/perfiles.py` (`Paciente.familiograma_pdf_path`), `clinica.py` (`Familiar`, `PatologiaSintoma`) y `usuarios.py` (`Usuario.debe_cambiar_password`). | Aprobada para implementación. |
