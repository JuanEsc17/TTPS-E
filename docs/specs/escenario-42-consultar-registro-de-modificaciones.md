# WORKFLOW: Escenario 42 – Consultar el registro de modificaciones
**Versión**: 1.0
**Fecha**: 2026-11-17
**Autor**: Workflow Architect & Software Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-42`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Administrativo`, `Gerente médico`, `Admin general`, `Médico` |
| **Objetos** | `Registro de modificaciones`, `Sample set`, `Paciente`, `Estudio` |
| **Verbos** | `Registrar modificación`, *(consulta de trazabilidad y auditoría)* |
| **Estados** | *(Solo lectura sobre tabla append-only `registro_modificaciones`; transversales a cualquier `EstadoEstudio` y `EstadoSampleSet`)* |

---

## Overview

- **Objetivo**: Garantizar y exponer un **registro de modificaciones** completo, cronológico e inmutable sobre toda creación, actualización de atributos o cambio de estado que ocurra en **sample sets**, **pacientes** y **estudios**.
- **Contexto**: Para trazabilidad clínica, regulatoria y operativa (Requerimiento 6 / ADR-003), cada mutación realizada tanto por usuarios en la API web como por webhooks externos (MercadoPago, resultados de Corea) o tareas automáticas del sistema (vencimientos, 5 ausencias, seguimiento VUS) debe asentarse atómicamente en la tabla append-only `registro_modificaciones` mediante `AuditoriaService`.
- **Recursos**: `Registro de modificaciones` (`registro_modificaciones`), `Sample set` (`sample_sets`), `Paciente` (`pacientes`), `Estudio` (`estudios`), `Usuario` (`usuarios`).
- **Episodios**:
  1. Ante cualquier escritura sobre `SampleSet`, `Paciente` o `Estudio`, el servicio de dominio involucrado invoca `AuditoriaService.registrar_modificacion(...)` dentro de la misma transacción DB.
  2. Un actor autorizado accede al panel general de auditoría o al historial de una entidad específica (`SampleSet`, `Paciente` o `Estudio`).
  3. El sistema aplica filtros opcionales (`entidad_tipo`, `entidad_id`, `accion`, `usuario_id`, `origen`, rango de fechas) y reglas de visibilidad por rol.
  4. El sistema retorna la línea de tiempo ordenada cronológicamente (más reciente primero) con responsable u origen, acción, snapshot `{campo: {anterior, nuevo}}` y motivo.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Administrativo` | Consulta historial de auditoría de `Sample sets`, `Pacientes` y `Estudios` para control operativo y soporte. |
| `Gerente médico` | Audita cambios en `Estudios`, `Pacientes` y `Sample sets` por supervisión médica/institucional. |
| `Admin general` | Accede al registro completo de auditoría de las tres entidades. |
| `Médico` | Consulta únicamente el historial de modificaciones de `Pacientes` para los que tiene autorización vigente y `Estudios` propios/autorizados. |
| `router` (`auditoria_router`) | Expone los endpoints `GET` de consulta (sin endpoints de escritura, edición o borrado). |
| `service` (`auditoria_service`) | Provee `registrar_modificacion(...)` (uso interno de servicios) y `listar_modificaciones(...)` con control de acceso por rol. |
| `repo` (`auditoria_repo`) | Inserta y consulta `registro_modificaciones` (prohibidos `UPDATE` y `DELETE`). |

---

## Prerequisites

- La migración Alembic que crea `registro_modificaciones` y los enums `EntidadAuditable` (`sample_set`, `paciente`, `estudio`) y `TipoAccionAuditoria` (`creacion`, `modificacion`, `cambio_estado`) fue aplicada.
- Todos los servicios que mutan `SampleSet`, `Paciente` o `Estudio` integran la llamada a `AuditoriaService.registrar_modificacion(...)` antes del `COMMIT`.
- Usuario autenticado con rol en `{ADMINISTRATIVO, GERENTE_MEDICO, ADMIN_GENERAL, MEDICO}`.

---

## Trigger

1. **Escritura transaccional interna**: Invocación a `AuditoriaService.registrar_modificacion(...)` desde `PacienteService`, `EstudioService`, `LogisticaService`, `EconomiaService` o `AnalisisService`.
2. **Consulta global paginada**: `GET /api/v1/auditoria/modificaciones?entidad_tipo=&entidad_id=&accion=&usuario_id=&origen=&desde=&hasta=&page=1&page_size=50`.
3. **Consulta por entidad puntual**:
   - `GET /api/v1/sample-sets/{sample_set_id}/modificaciones`
   - `GET /api/v1/pacientes/{paciente_id}/modificaciones`
   - `GET /api/v1/estudios/{estudio_id}/modificaciones`

---

## Workflow Tree

### STEP 1 (Escritura transversal): Captura atómica en `registro_modificaciones`
**Actor**: Servicio de dominio (`*Service`) -> `AuditoriaService` -> `AuditoriaRepo`
**Action**:
1. Antes de confirmar un cambio en `SampleSet`, `Paciente` o `Estudio`, el servicio compara los campos relevantes antes y después de la operación construyendo el diccionario `cambios = {campo: {"anterior": v_ant, "nuevo": v_new}}` (excluyendo cualquier campo sin cambio real y nunca incluyendo credenciales como `password_hash` o tokens).
2. Verifica que `cambios` no esté vacío (excepto en `creacion`, donde registra atributos iniciales esenciales, pudiendo indicar `anterior = None`).
3. Inserta en `registro_modificaciones`:
   - `entidad_tipo` (`sample_set` | `paciente` | `estudio`)
   - `entidad_id`
   - `accion` (`creacion` | `modificacion` | `cambio_estado`)
   - `usuario_id` (`usuario_actual.id` si es acción humana; `None` si es `webhook_*` o `cron_sistema`)
   - `origen` (`'usuario'`, `'webhook_mercadopago'`, `'webhook_corea'`, `'cron_sistema'`)
   - `cambios` (`JSONB`)
   - `motivo` (nullable; obligatorio cuando haya rollback por baja calidad en Corea o anulación excepcional)
   - `ip_origen` (`request.remote_addr` si aplica, `None` en jobs)
   - `fecha = func.now()`
4. La inserción forma parte de la **misma transacción SQLAlchemy** de la operación de negocio: si falla la auditoría, falla el `COMMIT` completo.
**Timeout**: `< 500ms` dentro de la transacción de dominio.
**Input**: DTO de auditoría desde el servicio de dominio.
**Output on SUCCESS**: Fila persistida de forma inmutable al ejecutarse `COMMIT`.
**Output on FAILURE**:
  - `FAILURE(empty_diff)`: En `modificacion` o `cambio_estado` sin diferencias reales, omite el insert o falla según contrato estricto -> no ensucia el log con eventos vacíos.
  - `FAILURE(db_error)`: Falla la inserción -> `ROLLBACK` total de la mutación de negocio (ninguna modificación queda sin auditar).

**Observable states during this step**:
  - **Operador sees**: Transparente durante su acción normal.
  - **Database**: Nueva fila append-only en `registro_modificaciones` indexada por `(entidad_tipo, entidad_id, fecha DESC)`.
  - **Logs**: `[auditoria_service] STEP 1 modificacion_registrada tipo=<tipo> id=<eid> accion=<accion>`

---

### STEP 2 (Lectura): Validación de permisos y autorización según rol
**Actor**: `router` -> `service` (`auditoria_service`) -> `repo` (`paciente_repo`, `estudio_repo`)
**Action**:
1. Verifica el rol del `usuario_actual`:
   - Si es `Paciente`, `Bioinformático` o `Transportista`: deniega con `403 Forbidden`.
   - Si es `Administrativo`, `Gerente médico` o `Admin general`: autoriza consulta general y por entidad (`sample_set`, `paciente`, `estudio`).
   - Si es `Médico`:
     - Rechaza con `403 Forbidden` consultas sobre `entidad_tipo = 'sample_set'` o listados globales sin filtro de entidad/alcance propio.
     - Para `entidad_tipo = 'paciente'`: verifica autorización activa en `pacientes_medicos_autorizados` (con respaldo transitorio en `paciente.medico_id == medico.id`).
     - Para `entidad_tipo = 'estudio'`: verifica `estudio.medico_id == medico.id` o autorización activa sobre `estudio.paciente_id`.
2. Valida que la entidad consultada por ruta específica exista en DB (sino `404 Not Found`).
**Timeout**: `2s`
**Input**: `usuario_actual`, parámetros de consulta / ruta.
**Output on SUCCESS**: Autorizado -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Rol sin privilegios o médico intentando leer entidad ajena -> `return 403 Forbidden` (`AUDITORIA_NO_AUTORIZADA`).
  - `FAILURE(not_found)`: `sample_set_id`, `paciente_id` o `estudio_id` inexistente -> `return 404 Not Found`.

**Observable states during this step**:
  - **Usuario autorizado sees**: Cargando línea de tiempo.
  - **Usuario sin permiso sees**: `403 Forbidden`.
  - **Database**: Verificación de existencia y autorización.
  - **Logs**: `[auditoria_service] STEP 2 consulta_autorizada rol=<rol> user_id=<uid>`

---

### STEP 3 (Lectura): Recuperación paginada y formateo cronológico de modificaciones
**Actor**: `service` (`auditoria_service`) -> `repo` (`auditoria_repo`)
**Action**:
1. Consulta `registro_modificaciones LEFT JOIN usuarios ON usuarios.id = registro_modificaciones.usuario_id` aplicando filtros (`entidad_tipo`, `entidad_id`, `accion`, `usuario_id`, `origen`, `desde`, `hasta`), usando el índice compuesto `(entidad_tipo, entidad_id, fecha DESC)`.
2. Ordena descendentemente por `fecha DESC, id DESC` y pagina (`page`, `page_size`, máximo `100` filas por página).
3. Serializa cada entrada incluyendo:
   - `id`, `entidad_tipo`, `entidad_id`, `accion`, `fecha` (ISO-8601 UTC)
   - `responsable`: `{ usuario_id, nombre_completo, rol }` (o `null` cuando `origen != 'usuario'`)
   - `origen`, `motivo`, `ip_origen`
   - `cambios`: `{ campo: { anterior, nuevo } }`
4. Retorna `{ items: [...], total: <int>, page: <int>, page_size: <int> }`.
**Timeout**: `2s`
**Input**: Filtros validados, paginación.
**Output on SUCCESS**: `200 OK` con historial cronológico inmutable -> END WORKFLOW.
**Output on FAILURE**:
  - `FAILURE(invalid_filter)`: Rango de fechas inválido (`desde > hasta`) o enum desconocido -> `return 422 Unprocessable Entity`.

**Observable states during this step**:
  - **Operador / Auditor sees**: Línea de tiempo cronológica diferenciando altas, cambios de estado y ediciones de atributos (valor anterior -> valor nuevo), usuario u origen automático y motivo.
  - **Database**: `SELECT` paginado de solo lectura sobre `registro_modificaciones`.
  - **Logs**: `[auditoria_service] STEP 3 modificaciones_listadas total=<n>`

---

## State Transitions

*(La tabla `registro_modificaciones` es exclusivamente **append-only** y carece de estados mutables; resume a continuación los eventos auditados por entidad)*

| Entidad (`entidad_tipo`) | Escenarios que generan filas obligatorias |
|---|---|
| `sample_set` | Escenario 12 (creación/armado, inclusión de muestras, cierre), Escenario 13 (carga de autorización ministerial, envío FedEx, cambio `CERRADO -> EN_VIAJE_COREA`), Escenario 14 (armado y envío de lote Pompe urgente). |
| `paciente` | Escenario 18 / 19 (alta de paciente), Escenario 35 / 36 (edición de `historia_clinica` y síntomas/familiares), Escenario 40 (otorgamiento y revocación en `pacientes_medicos_autorizados`). |
| `estudio` | Escenario 02 (alta), Escenario 03 / 04 / 05 (autorización obra social / demanda), Escenario 06 / 38 (pago y cuotas), Escenario 07 / 08 (turno sacado/cancelado), Escenario 09 / 11 (muestra lista / en lab central), Escenario 10 (remuestreo por baja calidad en Corea / ADN insuficiente), Escenario 13 / 14 (`EN_VIAJE_COREA`), Escenario 15 / 16 / 17 (datos crudos, bioinformática, resultado cargado y reanálisis), Escenario 33 (ausencias / anulación del pago y retorno a `Creado` tras 5 ausencias), Escenario 41 (vínculos familiares), Escenario 43 (`fecha_reevaluacion_vus`). |

---

## Handoff Contracts

| Origen | Destino | Payload / Garantía |
|---|---|---|
| Cualquier servicio que muta `SampleSet`, `Paciente` o `Estudio` | `AuditoriaService.registrar_modificacion(...)` | Mismo `Session` SQLAlchemy; `COMMIT` único atómico. |
| `AuditoriaService` | `Administrativo` / `Gerente médico` / `Admin general` / `Médico` | API JSON paginada de solo lectura con diff `{anterior, nuevo}`. |

---

## Cleanup Inventory

- Ningún proceso ni endpoint puede emitir `UPDATE` ni `DELETE` sobre `registro_modificaciones` (append-only).
- Se prohíbe explícitamente serializar dentro del JSONB `cambios` campos de credenciales o secretos (`password_hash`, códigos 2FA de `codigos_verificacion`, `tokens` externos).
- Para actualizaciones masivas en texto largo (ej. `historia_clinica`), puede almacenarse texto completo o resumen controlado según política, manteniendo trazabilidad exacta de contenido editado.

---

## Reality Checker Findings

- **Existente en código (`app/src/core/models/`)**: Actualmente no existe el archivo `auditoria.py` ni la tabla `registro_modificaciones`, ni existen `AuditoriaService` o `AuditoriaRepo`.
- **Existente en código (`app/src/core/services/logistica_service.py` y `medico_service.py`)**: Las mutaciones ya implementadas sobre `SampleSet`, `Paciente` y `Estudio` aún no registran historial de auditoría.
- **Pendiente de implementación**: Crear modelo `RegistroModificacion`, enums `EntidadAuditable` y `TipoAccionAuditoria`, migración Alembic correspondiente, trigger o permisos PostgreSQL append-only y decorar los servicios existentes con `AuditoriaService.registrar_modificacion(...)`.

---

## Test Cases

1. **TC-01 (Auditoría atómica en alta y cambio de estado de SampleSet)**: Al armar un `SampleSet` (Esc. 12) y enviarlo a Corea (Esc. 13), `GET /api/v1/sample-sets/{id}/modificaciones` retorna la creación (`accion='creacion'`) y los cambios posteriores (`accion='modificacion'` / `'cambio_estado'`) ordenados cronológicamente con `{anterior, nuevo}` y el `usuario_id` del administrativo.
2. **TC-02 (Auditoría de cambios en Paciente incluyendo Escenarios 35 y 40)**: Un médico edita `historia_clinica` y luego el paciente autoriza a un 2.º médico; `GET /api/v1/pacientes/{id}/modificaciones` registra ambas entradas sin exponer `password_hash`.
3. **TC-03 (Auditoría de Estudio incluyendo eventos automáticos con origen != usuario)**: Un rollback de remuestreo en Corea por administrativo (con `motivo`), una vinculación familiar (Esc. 41) y una anulación de pago por 5 ausencias (Esc. 33, `origen='cron_sistema'`, `usuario_id=None`) aparecen íntegros en `GET /api/v1/estudios/{id}/modificaciones`.
4. **TC-04 (Atomicidad ante error de auditoría)**: Se fuerza una falla de escritura en `AuditoriaRepo` durante la actualización de un `Estudio`; la transacción hace `ROLLBACK` y el `Estudio` tampoco cambia de estado.
5. **TC-05 (Control de acceso por rol)**: Un `Médico` consulta modificaciones de un paciente propio autorizado (`200 OK`), recibe `403 Forbidden` al consultar un paciente ajeno no autorizado o `GET /api/v1/sample-sets/{id}/modificaciones`, y un `Paciente` recibe `403 Forbidden` en cualquier endpoint de auditoría.
6. **TC-06 (Inmutabilidad append-only)**: No existen rutas `PATCH`, `PUT` ni `DELETE` sobre `/api/v1/auditoria/modificaciones*` (retornan `404`/`405`).

---

## Assumptions

- Las mutaciones de entidades auxiliares puramente operativas fuera del alcance solicitado (por ejemplo, `posiciones_transporte` cada pocos segundos o `avisos` leídos) **no** se registran en `registro_modificaciones` para no saturar la auditoría, limitando esta tabla estrictamente a `sample_set`, `paciente` y `estudio` (y las sub-relaciones que alteran su alcance clínico/logístico como genes, muestras incluidas, médicos autorizados o vínculos familiares).
- Las fechas se almacenan y retornan en UTC con zona horaria (`DateTime(timezone=True)`).

---

## Open Questions

- Cuando un `Administrativo` o `Admin general` consulta `GET /api/v1/pacientes/{id}/modificaciones`, ¿debe visualizar en `cambios` el diff completo del texto clínico de `historia_clinica` o únicamente una indicación redactada (`"[HISTORIA CLÍNICA ACTUALIZADA]"`) reservando el texto íntegro al `Médico` autorizado y `Gerente médico`? *(A confirmar según criterio de confidencialidad clínica del proyecto).*

---

## Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-11-17 | Especificación creada para el Requerimiento 6 y ADR-003 (registro inmutable de modificaciones sobre `sample_set`, `paciente` y `estudio`). | Aprobada para guiar la implementación transversal de `AuditoriaService` y endpoints de consulta. |
