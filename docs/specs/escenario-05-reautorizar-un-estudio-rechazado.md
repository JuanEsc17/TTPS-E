# WORKFLOW: Escenario 5 – Reautorizar un estudio rechazado
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-5`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Paciente`, `Administrativo` |
| **Objetos** | `Estudio`, `Obra social`, `Demanda`, `Presupuesto`, `Aviso` |
| **Verbos** | `Sacar turno` *(habilitado tras la nueva autorización)* |
| **Estados** | `Rechazado`, `Pendiente de autorización`, `Autorizado` |

---

## Overview

- **Objetivo**: Permitir que el `Paciente` cargue una `Demanda` con la documentación judicial favorable en formato PDF cuando su `Obra social` rechazó el `Estudio`, haciendo que el `Estudio` vuelva a `Pendiente de autorización`, y que luego el `Administrativo` solicite y registre la nueva autorización para que el `Estudio` pase a `Autorizado` y continúe su proceso normal.
- **Contexto**: La `Obra social` rechazó la autorización inicial del `Estudio`, por lo que el `Estudio` se encuentra en estado `Rechazado` (`EstadoEstudio.RECHAZADO`). El `Paciente` acude a la justicia, obtiene un fallo judicial favorable en PDF y lo sube al sistema asociado a su `Estudio`.
- **Recursos**: Documento PDF de la decisión judicial favorable (`Demanda.pdf_path`), `Estudio` en estado `Rechazado`, nueva fila en `Autorizacion` vinculada a `demanda_id`, registro financiero `Pago`.
- **Episodios**:
  1. El `Paciente` carga la decisión judicial favorable en PDF (`Demanda`) asociada al `Estudio` en estado `Rechazado` y pide la reautorización; el sistema registra la `Demanda`, crea una nueva `Autorizacion` (`ResultadoAutorizacion.PENDIENTE`, `demanda_id = demanda.id`) y devuelve el `Estudio` al estado `Pendiente de autorización`.
  2. El `Administrativo` recibe el `Aviso`, gestiona/solicita la reautorización ante la `Obra social` respaldada por el PDF de la `Demanda`.
  3. El `Administrativo` registra la nueva autorización (`ResultadoAutorizacion.AUTORIZADA`) sobre la solicitud vinculada a la `Demanda`.
  4. El sistema pasa el `Estudio` al estado `Autorizado`, registra el `Pago` correspondiente y el `Estudio` continúa su proceso habilitando al `Paciente` para `Sacar turno`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Paciente` | Sujeto LEL titular del `Estudio` rechazado que sube el PDF de la decisión judicial favorable (`Demanda`) y solicita la reautorización. |
| `Administrativo` | Sujeto LEL del laboratorio central que gestiona la reautorización con la `Obra social` y registra la nueva autorización. |
| `router` (`demandas_router`, `autorizaciones_router`) | Capa HTTP Flask (`POST /api/v1/estudios/{estudio_id}/demandas` para el `Paciente` y `POST /api/v1/estudios/{estudio_id}/autorizaciones` para el `Administrativo`). |
| `service` (`economia_service`) | Capa de negocio que valida el PDF, crea la `Demanda`, transiciona el `Estudio` de `Rechazado` -> `Pendiente de autorización` -> `Autorizado`, y registra la nueva fila en `autorizaciones` y en `pagos`. |
| `repo` (`economia_repo`, `estudio_repo`, `usuario_repo`) | Capa de acceso a datos SQLAlchemy sobre `demandas`, `autorizaciones`, `estudios`, `pagos`, `avisos`. |
| `clients` (`obras_sociales_client`, `notificacion_client`) | Clientes HTTP hacia `API de obras sociales` y servicio de correo/avisos. |
| `PostgreSQL` | Base de datos relacional que conserva el historial completo de `autorizaciones` y `demandas` del `Estudio`. |

---

## Prerequisites

- **Para la Parte 1 (Carga de la `Demanda` por el `Paciente`)**:
  - El usuario autenticado tiene `Usuario.rol == Rol.PACIENTE`, ya cambió su contraseña inicial (`debe_cambiar_password == False`) y es el titular del `Estudio` (`estudio.paciente.usuario_id == usuario_actual.id`).
  - El `Estudio` se encuentra exactamente en estado `EstadoEstudio.RECHAZADO` (`"Rechazado"`).
  - El archivo subido es un documento PDF válido (`application/pdf`, encabezado `%PDF-`).
- **Para la Parte 2 (Registro de la reautorización por el `Administrativo`)**:
  - El usuario autenticado tiene `Usuario.rol == Rol.ADMINISTRATIVO`.
  - El `Estudio` se encuentra en `EstadoEstudio.PENDIENTE_AUTORIZACION` y posee una `Demanda` registrada y una fila en `autorizaciones` con `demanda_id != None` y `resultado == ResultadoAutorizacion.PENDIENTE`.

---

## Trigger

1. **Trigger Parte 1 (`Paciente`)**: El `Paciente` sube el PDF de la decisión judicial favorable y solicita la reautorización:
   - **Endpoint HTTP**: `POST /api/v1/estudios/{estudio_id}/demandas` (`multipart/form-data` con campo `archivo_pdf`).
2. **Trigger Parte 2 (`Administrativo`)**: El `Administrativo` solicita y registra la nueva autorización:
   - **Endpoint HTTP**: `POST /api/v1/estudios/{estudio_id}/autorizaciones` (`application/json` con `{"resultado": "autorizada", "demanda_id": <id>}`).

---

## Workflow Tree

### STEP 1: Validación de titularidad del `Paciente`, estado `Rechazado` y archivo PDF de la `Demanda`
**Actor**: `router` (`demandas_router`) -> `service` (`economia_service`) -> `repo` (`estudio_repo`)
**Action**:
1. Verifica que el usuario autenticado tenga `Usuario.rol == Rol.PACIENTE`.
2. Carga el `Estudio` por `estudio_id` (`SELECT ... FOR UPDATE`) y verifica que pertenezca al `Paciente` autenticado (`estudio.paciente.usuario_id == usuario_actual.id`).
3. Verifica que `estudio.estado == EstadoEstudio.RECHAZADO`.
4. Valida el archivo recibido en `archivo_pdf`: debe estar presente, tener extensión `.pdf`, MIME type `application/pdf`, magic bytes `%PDF-` al inicio y tamaño entre `1 KB` y `10 MB`.
**Timeout**: `3s`
**Input**: `estudio_id`, archivo binario `archivo_pdf`, `usuario_actual` (`Paciente`).
**Output on SUCCESS**: `Estudio` validado y bytes del PDF verificados -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: El usuario no es `Rol.PACIENTE` o el `Estudio` pertenece a otro paciente -> `return 403 Forbidden` (`code: "FORBIDDEN_NOT_OWNER"`).
  - `FAILURE(not_found)`: `estudio_id` no existe -> `return 404 Not Found` (`code: "ESTUDIO_NO_ENCONTRADO"`).
  - `FAILURE(invalid_state)` / `FAILURE(conflict)`: `estudio.estado != EstadoEstudio.RECHAZADO` -> `return 409 Conflict` (`{"ok": false, "error": "Solo se puede cargar una demanda para un estudio en estado Rechazado", "code": "ESTADO_ESTUDIO_INVALIDO", "retryable": false}`).
  - `FAILURE(validation_error)`: Archivo faltante, vacío, mayor a 10 MB o no es un PDF válido -> `return 400 Bad Request` (`code: "PDF_DEMANDA_INVALIDO"`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Barra de progreso `"Subiendo fallo judicial en PDF..."`.
  - **Operator sees**: Request multipart entrante en `POST /api/v1/estudios/{estudio_id}/demandas`.
  - **Database**: Lectura `FOR UPDATE` sobre `estudios`.
  - **Logs**: `[economia_service] STEP 1 demanda iniciada estudio_id=<id> paciente_id=<pid>`

---

### STEP 2: Almacenamiento del PDF, creación de `Demanda`, nueva fila en `Autorizacion` y transición a `Pendiente de autorización`
**Actor**: `service` (`economia_service`) -> `repo` (`economia_repo`, `estudio_repo`, `usuario_repo`) -> `PostgreSQL`
**Action**:
1. Guarda el archivo PDF en disco bajo `storage/demandas/estudio_<estudio_id>_demanda_<timestamp>.pdf`.
2. Inserta una fila en la tabla `demandas`:
   - `estudio_id = estudio.id`
   - `pdf_path = ruta_archivo`
   - `fecha = func.now()`
3. Inserta una **nueva** fila en la tabla `autorizaciones` (preservando la fila anterior donde `resultado == ResultadoAutorizacion.RECHAZADA`, tal como exige `economia.py` línea 82: *"Una reautorizacion es una nueva fila para el mismo estudio"*):
   - `estudio_id = estudio.id`
   - `resultado = ResultadoAutorizacion.PENDIENTE`
   - `demanda_id = demanda.id`
   - `registrada_por_id = None`
4. Actualiza `estudio.estado = EstadoEstudio.PENDIENTE_AUTORIZACION` (`"Pendiente de autorizacion"`), cumpliendo con el LEL (`Estado: Rechazado -> El paciente carga una demanda y pide la reautorización. El estudio vuelve a Pendiente de autorización`).
5. Inserta un `Aviso` en `avisos` para los usuarios con `Rol.ADMINISTRATIVO` (`"El paciente del estudio #<id> cargó una demanda judicial favorable. Solicitar reautorización."`).
6. Ejecuta `session.commit()` y devuelve `201 Created` al `Paciente`.
**Timeout**: `5s`
**Input**: `Estudio`, bytes del PDF
**Output on SUCCESS**: `Demanda` y nueva `Autorizacion` (`PENDIENTE`) persistidas; `Estudio` en `Pendiente de autorización` -> `GO TO STEP 3` (cuando el `Administrativo` toma el trámite)
**Output on FAILURE**:
  - `FAILURE(io_error)` / `FAILURE(db_error)`: Falla la escritura en disco o el commit en `PostgreSQL` -> `GO TO ABORT_CLEANUP` (elimina el PDF si llegó a crearse y hace `session.rollback()`).

**Observable states during this step**:
  - **Customer/Actor (`Paciente`) sees**: Confirmación `"Demanda judicial cargada correctamente. Su estudio volvió al estado Pendiente de autorización"`.
  - **Actor (`Administrativo`) sees**: Nuevo `Aviso` en su bandeja y el `Estudio` nuevamente en estado `Pendiente de autorización` con enlace para descargar el PDF de la `Demanda`.
  - **Database**: Nueva fila en `demandas`; nueva fila en `autorizaciones` (`demanda_id = demanda.id`, `resultado = PENDIENTE`); `estudios.estado = EstadoEstudio.PENDIENTE_AUTORIZACION`.
  - **Logs**: `[economia_repo] STEP 2 demanda_id=<did> nueva_autorizacion_id=<aid> estudio_id=<eid> estado=Pendiente de autorizacion`

---

### STEP 3: Gestión y registro de la nueva autorización por el `Administrativo`
**Actor**: `Administrativo` -> `router` (`autorizaciones_router`) -> `service` (`economia_service`) -> `repo` (`economia_repo`, `estudio_repo`)
**Action**:
1. El `Administrativo` presenta la solicitud de reautorización ante la `Obra social` acompañada de la decisión judicial favorable y recibe la confirmación.
2. El `Administrativo` invoca `POST /api/v1/estudios/{estudio_id}/autorizaciones` con `{"resultado": "autorizada", "demanda_id": demanda.id}`.
3. El servicio verifica `Usuario.rol == Rol.ADMINISTRATIVO`, comprueba que `estudio.estado == EstadoEstudio.PENDIENTE_AUTORIZACION` y localiza la última fila de `autorizaciones` vinculada a `demanda_id`.
4. Actualiza dicha fila en `autorizaciones`:
   - `resultado = ResultadoAutorizacion.AUTORIZADA`
   - `registrada_por_id = usuario_actual.id`
   - `fecha = func.now()`
5. Cambia `estudio.estado = EstadoEstudio.AUTORIZADO` (`"Autorizado"`).
6. Inserta el registro financiero en `pagos` (`presupuesto_id = estudio.presupuesto.id`, `tipo = TipoPago.OBRA_SOCIAL`, `monto_usd`, `cobertura_obra_social_usd`, `anulado = False`).
7. Crea un `Aviso` y envía correo al `Paciente` informando que su `Estudio` fue reautorizado y ya puede `Sacar turno`.
8. Ejecuta `session.commit()`.
**Timeout**: `5s`
**Input**: `estudio_id`, `resultado = "autorizada"`, `demanda_id`, `usuario_actual` (`Administrativo`).
**Output on SUCCESS**: `Estudio` en estado `Autorizado` con `Pago` registrado -> `WORKFLOW COMPLETE`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Usuario no es `Rol.ADMINISTRATIVO` -> `return 403 Forbidden`.
  - `FAILURE(invalid_state)`: El `Estudio` no está en `EstadoEstudio.PENDIENTE_AUTORIZACION` o no tiene `Demanda` asociada -> `return 409 Conflict` (`code: "ESTADO_ESTUDIO_INVALIDO"`).
  - `FAILURE(db_error)`: Error de base de datos -> `GO TO ABORT_CLEANUP`.

**Observable states during this step**:
  - **Customer/Actor (`Administrativo`) sees**: `"Reautorización registrada exitosamente. Estudio #<id> en estado Autorizado"`.
  - **Actor (`Paciente`) sees**: `Aviso` y correo de confirmación; su `Estudio` figura en estado `Autorizado` con el botón `"Sacar turno"` habilitado.
  - **Database**: `estudios.estado = EstadoEstudio.AUTORIZADO`; `autorizaciones` tiene historial de 2 filas (la 1.ª `RECHAZADA` con `demanda_id=NULL` y la 2.ª `AUTORIZADA` con `demanda_id=demanda.id`); fila creada en `pagos`.
  - **Logs**: `[economia_service] STEP 3 reautorizacion completada estudio_id=<id> demanda_id=<did> pago_id=<pid>`

---

### ABORT_CLEANUP: Reversión de carga de demanda o de reautorización
**Triggered by**: Fallo de I/O o base de datos en `STEP 2` o `STEP 3`.
**Actions**:
  1. Si falló en `STEP 2`: eliminar el archivo físico `storage/demandas/estudio_<id>_...pdf` si fue escrito en disco, y hacer `session.rollback()` para que `estudios.estado` permanezca en `EstadoEstudio.RECHAZADO` sin filas huérfanas en `demandas` ni `autorizaciones`.
  2. Si falló en `STEP 3`: hacer `session.rollback()` para que `estudios.estado` permanezca en `EstadoEstudio.PENDIENTE_AUTORIZACION` y la segunda fila de `autorizaciones` continúe en `ResultadoAutorizacion.PENDIENTE`.
**What customer sees**: Mensaje de error claro indicando que la operación no pudo completarse y que puede reintentar.
**What operator sees**: Log con detalle de la excepción y estado consistente en BD y filesystem.

---

## State Transitions

```
[Estudio.estado = RECHAZADO ("Rechazado")]
   |-- (STEP 1-2: Paciente sube PDF de Demanda judicial favorable)
   |       --> Demanda creada (pdf_path != NULL)
   |       --> Nueva fila en Autorizacion (resultado = PENDIENTE, demanda_id = Demanda.id)
   v
[Estudio.estado = PENDIENTE_AUTORIZACION ("Pendiente de autorizacion")]
   |
   |-- (STEP 3: Administrativo solicita y registra la nueva autorización)
   |       --> Segunda fila de Autorizacion pasa a resultado = AUTORIZADA
   |       --> Pago creado (tipo = TipoPago.OBRA_SOCIAL, anulado = False)
   v
[Estudio.estado = AUTORIZADO ("Autorizado")] --> (Habilitado para Sacar turno)
```

---

## Handoff Contracts

### 1. Frontend Paciente -> Backend (`POST /api/v1/estudios/{estudio_id}/demandas`)
**Endpoint**: `POST /api/v1/estudios/{estudio_id}/demandas` (`Content-Type: multipart/form-data`)
**Payload**:
- `archivo_pdf`: archivo binario PDF con la decisión judicial favorable.
**Success response** (`201 Created`):
```json
{
  "ok": true,
  "data": {
    "demanda_id": 9,
    "estudio_id": 101,
    "pdf_path": "storage/demandas/estudio_101_demanda_20261028.pdf",
    "autorizacion_id": 16,
    "resultado_autorizacion": "pendiente",
    "estado_estudio": "Pendiente de autorizacion"
  }
}
```
**Failure response** (`400` / `403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "Solo se puede cargar una demanda para un estudio en estado Rechazado",
  "code": "ESTADO_ESTUDIO_INVALIDO",
  "retryable": false
}
```
**Timeout**: `10s`
**ON FAILURE**: Eliminar archivo PDF temporal y ejecutar `session.rollback()`.

---

### 2. Frontend Administrativo -> Backend (`POST /api/v1/estudios/{estudio_id}/autorizaciones`)
**Endpoint**: `POST /api/v1/estudios/{estudio_id}/autorizaciones`
**Payload**:
```json
{
  "resultado": "autorizada",
  "demanda_id": 9,
  "solicitud_externa_id": "OS-REAUT-2026-00981"
}
```
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "autorizacion_id": 16,
    "estudio_id": 101,
    "demanda_id": 9,
    "resultado": "autorizada",
    "estado_estudio": "Autorizado",
    "registrada_por_id": 12,
    "pago": {
      "pago_id": 92,
      "presupuesto_id": 33,
      "tipo": "obra_social",
      "monto_usd": "560.00",
      "cobertura_obra_social_usd": "448.00",
      "anulado": false
    }
  }
}
```
**Failure response** (`403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "El estudio no se encuentra en estado Pendiente de autorización",
  "code": "ESTADO_ESTUDIO_INVALIDO",
  "retryable": false
}
```
**Timeout**: `8s`
**ON FAILURE**: `session.rollback()` mediante `ABORT_CLEANUP`.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Archivo PDF en `storage/demandas/estudio_<id>_...pdf` | STEP 2 | `ABORT_CLEANUP` | `os.remove(pdf_path)` |
| Registro en `demandas` | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Nueva fila en `autorizaciones` (`demanda_id != None`) | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Cambio de `estudios.estado` a `PENDIENTE_AUTORIZACION` | STEP 2 | `ABORT_CLEANUP` | `session.rollback()` |
| Actualización de `autorizaciones.resultado = AUTORIZADA`, `pagos` y `estudios.estado = AUTORIZADO` | STEP 3 | `ABORT_CLEANUP` | `session.rollback()` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/economia.py`, `Demanda` tiene `id`, `estudio_id`, `pdf_path` (`String(500)`) y `fecha`, y `Autorizacion` tiene `demanda_id: Mapped[Optional[int]] = mapped_column(ForeignKey("demandas.id"))` con el comentario explícito: *"Una reautorizacion es una nueva fila para el mismo estudio"*. | Low | STEP 2 & STEP 3 | El flujo inserta una nueva fila en `autorizaciones` con `demanda_id = demanda.id`, conservando intacta la fila previa rechazada. |
| RC-2 | En `.ai/2-Glosario_LEL.md` (`Estado: Rechazado`), se especifica: *"El paciente carga una demanda y pide la reautorización. El estudio vuelve a Pendiente de autorización"*. | Low | State Transitions | 100% alineado con los 14 estados del LEL. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Happy path Paciente carga demanda en PDF sobre estudio Rechazado** | `POST /api/v1/estudios/{id}/demandas` con un PDF válido por el `Paciente` titular de un estudio en `EstadoEstudio.RECHAZADO`. | Retorna `201 Created`; crea fila en `demandas`, crea 2.ª fila en `autorizaciones` (`resultado=PENDIENTE`, `demanda_id=demanda.id`) y cambia `Estudio.estado` a `EstadoEstudio.PENDIENTE_AUTORIZACION`. |
| **TC-02: Happy path Administrativo registra la reautorización** | `POST /api/v1/estudios/{id}/autorizaciones` con `{"resultado": "autorizada", "demanda_id": 9}` por un `Administrativo`. | Retorna `200 OK`; la 2.ª fila de `autorizaciones` pasa a `AUTORIZADA` (la 1.ª sigue en `RECHAZADA`); se crea `Pago` (`TipoPago.OBRA_SOCIAL`); `Estudio.estado` pasa a `EstadoEstudio.AUTORIZADO`. |
| **TC-03: Intento de cargar demanda cuando el estudio NO está Rechazado** | `POST /api/v1/estudios/{id}/demandas` sobre un estudio en `Creado` o `Pendiente de autorización`. | Retorna `409 Conflict` (`code: "ESTADO_ESTUDIO_INVALIDO"`); no guarda archivo ni crea `Demanda`. |
| **TC-04: Intento de subir archivo que no es PDF** | `POST /api/v1/estudios/{id}/demandas` adjuntando un archivo `.exe` o `.txt`. | Retorna `400 Bad Request` (`code: "PDF_DEMANDA_INVALIDO"`). |
| **TC-05: Intento de cargar demanda por otro paciente o por un médico** | `POST /api/v1/estudios/{id}/demandas` invocado por un `Paciente` distinto del titular o por un `Médico`. | Retorna `403 Forbidden` (`code: "FORBIDDEN_NOT_OWNER"`). |
| **TC-06: Fallo de base de datos tras escribir el PDF en disco** | Excepción forzada en `session.commit()` durante `STEP 2`. | `ABORT_CLEANUP` borra el archivo PDF del disco y revierte la transacción en BD. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Al existir una decisión judicial favorable (`Demanda`), la reautorización gestionada por el `Administrativo` resulta aprobada (`ResultadoAutorizacion.AUTORIZADA`), aunque el modelo soporta múltiples filas en `demandas` y `autorizaciones` si ocurriera más de un ciclo. | `.ai/1-Entrevista.md` líneas 183-191 y `.ai/3-Escenarios.md` (Escenario 5). | Bajo. |

## Open Questions

- Ninguna. El modelo `Demanda` y la relación `Autorizacion.demanda_id` en `app/src/core/models/economia.py` cubren todos los requisitos sin ambigüedad.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/economia.py` y `estudios.py`. | Marcada como `Approved`. |
