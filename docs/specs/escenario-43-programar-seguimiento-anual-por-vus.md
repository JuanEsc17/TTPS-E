# WORKFLOW: Escenario 43 – Programar y notificar seguimiento anual por diagnóstico VUS
**Versión**: 1.0
**Fecha**: 2026-11-17
**Autor**: Workflow Architect & Software Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-43`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Médico`, `Paciente`, `Bioinformático` *(origina el resultado VUS en Escenario 16)* |
| **Objetos** | `Resultado`, `Estudio`, `VUS`, `Registro de modificaciones`, `Aviso` |
| **Verbos** | `Cargar resultado`, `Registrar modificación`, *(consulta de agenda de reevaluaciones VUS y recordatorio anual)* |
| **Estados** | `Resultado cargado` |

---

## Overview

- **Objetivo**: Cuando el diagnóstico de un `Resultado` es **VUS** (`ConclusionDiagnostica.VUS`), calcular y guardar automáticamente la fecha programada para realizar un nuevo estudio dentro de un año (`fecha_proximo_estudio` / `fecha_reevaluacion_vus = fecha_resultado + 1 año`), exponerla al `Médico` y al `Paciente`, y notificar el recordatorio al aproximarse/cumplirse dicho plazo.
- **Contexto**: Las variantes de significado incierto (`ClasificacionVariante.VUS`) pueden reclasificarse como patogénicas o benignas al ampliarse las bases clínicas internacionales en los meses posteriores. Conforme al Requerimiento 7, **ADR-004** y `.ai/APIs/API_APIGen.md`, al informarse un diagnóstico VUS en el Escenario 16 (o reanálisis en Escenario 17), debe persistirse explícitamente la fecha a un año y dispararse avisos de seguimiento para que médico y paciente realicen el nuevo estudio o reevaluación anual.
- **Recursos**: `Resultado` (`resultados.diagnostico`, `resultados.fecha_proximo_estudio`), `Estudio` (`estudios.fecha_reevaluacion_vus`), `Registro de modificaciones` (`registro_modificaciones`), `Aviso` (`avisos`).
- **Episodios**:
  1. Al cerrarse un análisis con diagnóstico `ConclusionDiagnostica.VUS`, el sistema calcula `fecha_resultado + 1 año` y guarda dicha fecha tanto en `resultados.fecha_proximo_estudio` como en `estudios.fecha_reevaluacion_vus`.
  2. El sistema registra la asignación de `fecha_reevaluacion_vus` en `registro_modificaciones` (`entidad_tipo = 'estudio'`).
  3. El `Médico` y el `Paciente` visualizan la fecha programada en el detalle del estudio, en el PDF del resultado (Escenario 16/37) y en el endpoint de agenda VUS.
  4. Un cron diario detecta los estudios con `fecha_reevaluacion_vus` próxima (`<= hoy + 30 días`) o cumplida (`<= hoy`) y emite un `Aviso` (app y email) para el `Médico` y el `Paciente` de forma idempotente.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Sistema (ResultadoService)` | Calcula y persiste la fecha anual `+ 1 año` al momento de generar el `Resultado` VUS (Escenario 16 / 17). |
| `Sistema (Job diario VUS)` | Recorre estudios con `fecha_reevaluacion_vus` pendiente de recordatorio y emite notificaciones preventivas (`30d`) y de cumplimiento (`hoy`). |
| `Médico` | Visualiza su listado de pacientes con seguimiento anual VUS y recibe recordatorios para indicar nuevo estudio o reanálisis. |
| `Paciente` | Visualiza la fecha de nuevo estudio en su resultado y recibe el recordatorio anual. |
| `router` (`estudios_router`) | Expone `GET /api/v1/estudios/seguimiento-vus`. |
| `service` (`resultado_service`, `estudio_service`, `aviso_service`, `auditoria_service`) | Calcula `fecha_proximo_estudio`, sincroniza `Estudio.fecha_reevaluacion_vus`, registra auditoría y gestiona avisos idempotentes. |
| `repo` (`estudio_repo`, `analisis_repo`, `auditoria_repo`, `usuario_repo`) | Consulta y persiste `resultados`, `estudios`, `registro_modificaciones` y `avisos`. |

---

## Prerequisites

- Para **Rama A (Guardado al emitir diagnóstico)**: Un `Analisis` tiene variantes registradas sin ninguna `ClasificacionVariante.PATOGENICA` y con al menos una `ClasificacionVariante.VUS`.
- Para **Rama B (Consulta de agenda VUS)**: Usuario autenticado como `Rol.MEDICO`, `Rol.GERENTE_MEDICO`, `Rol.ADMINISTRATIVO` o `Rol.PACIENTE`.
- Para **Rama C (Recordatorio anual)**: Estudio con `estado == EstadoEstudio.RESULTADO_CARGADO` y `fecha_reevaluacion_vus IS NOT NULL`, sin un `Estudio` posterior o `Reanálisis` ya iniciado posteriormente con diagnóstico definitivo (`positivo` o `negativo`).

---

## Trigger

1. **Trigger automático A (Emisión de resultado VUS)**: Fin de cálculo en STEP 1–2 del Escenario 16 o STEP 4 del Escenario 17.
2. **Trigger manual B (Consulta de próximos estudios por VUS)**: `GET /api/v1/estudios/seguimiento-vus?desde=&hasta=&estado_plazo=`.
3. **Trigger programado C (Job diario VUS)**: Cron diario ejecutado a las `08:00` ART.

---

## Workflow Tree

### STEP 1 (Rama A): Cálculo y persistencia de la fecha a un año para diagnóstico `VUS`
**Actor**: `service` (`ResultadoService`) -> `repo` (`AnalisisRepo`, `EstudioRepo`, `AuditoriaRepo`)
**Action**:
1. Dentro de la transacción de guardado del `Resultado`:
   - Evalua `ConclusionDiagnostica`: si `not any(PATOGENICA)` y `any(VUS)` -> `diagnostico = ConclusionDiagnostica.VUS`.
2. Calcula `fecha_base = generado_en.date()` y suma exactamente 1 año calendario manejando años bisiestos (ej. `2024-02-29 + 1 año -> 2025-02-28` con `dateutil.relativedelta` o reemplazo seguro de año):
   - `resultado.diagnostico = ConclusionDiagnostica.VUS`
   - `resultado.fecha_proximo_estudio = fecha_anual`
   - `estudio.fecha_reevaluacion_vus = fecha_anual`
3. Registra la modificación en `registro_modificaciones`:
   - `entidad_tipo = EntidadAuditable.ESTUDIO`, `entidad_id = estudio.id`, `accion = TipoAccionAuditoria.MODIFICACION`
   - `cambios = {"fecha_reevaluacion_vus": {"anterior": valor_anterior, "nuevo": str(fecha_anual)}}`
   - `motivo = "Programación automática de nuevo estudio en 1 año por diagnóstico VUS"`
4. *(Caso de resolución posterior: si en un reanálisis futuro el `Estudio` pasa a `ConclusionDiagnostica.POSITIVO` o `NEGATIVO`, limpia `estudio.fecha_reevaluacion_vus = None` auditándolo en `registro_modificaciones`.)*
**Timeout**: `2s`
**Input**: `Estudio`, `Resultado`, `generado_en`, `variantes`.
**Output on SUCCESS**: Fechas sincronizadas en `resultados` y `estudios`, auditable y renderizable en PDF -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(db_error)`: Error de escritura -> `ROLLBACK` total junto con el guardado del resultado.

**Observable states during this step**:
  - **Paciente / Médico sees**: Badge `"Diagnóstico: VUS – Nuevo estudio sugerido el <DD/MM/AAAA>"` en pantalla y PDF del resultado.
  - **Database**: `resultados.diagnostico = 'vus'`, `resultados.fecha_proximo_estudio = '<YYYY-MM-DD>'`, `estudios.fecha_reevaluacion_vus = '<YYYY-MM-DD>'`; fila en `registro_modificaciones`.
  - **Logs**: `[resultado_service] STEP 1 vus_fecha_anual_guardada estudio_id=<eid> fecha=<fecha_anual>`

---

### STEP 2 (Rama B): Consulta de agenda de estudios con seguimiento `VUS`
**Actor**: `Médico` o `Paciente` -> `router` -> `service` (`estudio_service`) -> `repo` (`estudio_repo`)
**Action**:
1. Aplica filtro obligatorio según rol autenticado:
   - Si `Rol.PACIENTE`: solo estudios donde `estudios.paciente_id == paciente.id`.
   - Si `Rol.MEDICO` / `GERENTE_MEDICO`: solo estudios donde `estudio.medico_id == medico.id` O existe autorización activa en `pacientes_medicos_autorizados` para `estudio.paciente_id`.
   - Si `Rol.ADMINISTRATIVO` / `ADMIN_GENERAL`: visión general institucional.
2. Filtra `estudios` donde `estudios.fecha_reevaluacion_vus IS NOT NULL` (usando el índice parcial `idx_estudios_reevaluacion_vus`), opcionalmente acotado por rango `[desde, hasta]` o `estado_plazo` (`proximo_30d`, `vencido`, `vigente`).
3. Calcula `dias_restantes = (estudio.fecha_reevaluacion_vus - hoy).days` y ordena ascendentemente por `fecha_reevaluacion_vus ASC`.
**Timeout**: `2s`
**Input**: `usuario_actual`, filtros opcionales.
**Output on SUCCESS**: `200 OK` con `{ total, items: [{ estudio_id, paciente_nombre, medico_nombre, patologia, resultado_fecha, fecha_reevaluacion_vus, dias_restantes, estado_plazo }] }`.
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Rol no clínico ni paciente (ej. `Transportista`) -> `return 403 Forbidden`.

**Observable states during this step**:
  - **Médico sees**: Lista ordenada de pacientes VUS con indicador `"En X días"` o `"Corresponde reevaluación anual"` y enlace directo a iniciar nuevo estudio/reanálisis.
  - **Paciente sees**: Recordatorio en su panel con la fecha pautada a 1 año.
  - **Database**: Lectura indexada sobre `idx_estudios_reevaluacion_vus`.
  - **Logs**: `[estudio_service] STEP 2 agenda_vus_consultada rol=<rol> total=<n>`

---

### STEP 3 (Rama C - Cron diario): Notificación preventiva (`30 días`) y cumplimiento anual (`hoy`)
**Actor**: `Sistema (Cron diario 08:00 ART)` -> `service` (`estudio_service`, `aviso_service`, `auditoria_service`) -> `repo` & `MailClient`
**Action**:
1. Consulta todos los `Estudio`s con `fecha_reevaluacion_vus IS NOT NULL` y `estado == EstadoEstudio.RESULTADO_CARGADO` donde `fecha_reevaluacion_vus <= hoy + 30 días`.
2. Por cada estudio elegible:
   - Verifica que el `Paciente` no tenga ya un nuevo `Estudio` para la misma patología creado después del `Resultado` VUS actual ni un `Reanálisis` posterior en curso (`estado in {EN_ANALISIS_BIOINFORMATICA, EN_ANALISIS_BIOINFORMATICO}`). Si ya inició nuevo estudio/reanálisis, omite notificaciones adicionales (opcionalmente conserva histórico).
   - Evalúa los dos hitos idempotentes buscando en `avisos` si ya se notificó el marcador de ese estudio:
     - **Hito `30 días previos`** (`hoy >= fecha_reevaluacion_vus - 30 días` y aún `< fecha_reevaluacion_vus`): si no se envió recordatorio preventivo, crea `Aviso` (`CanalAviso.APP` + `CanalAviso.MAIL`) para `Paciente` y `Médico`: `"Recordatorio: el <fecha> se cumple 1 año del resultado VUS de su estudio #<id>. Corresponde coordinar nuevo estudio / reevaluación."`
     - **Hito `Cumplimiento del año`** (`hoy >= fecha_reevaluacion_vus`): si no se envió aviso de cumplimiento, crea `Aviso` (`CanalAviso.APP` + `CanalAviso.MAIL`) para `Paciente` y `Médico`: `"Se cumplió 1 año desde su diagnóstico VUS (Estudio #<id>). Ya corresponde realizar el nuevo estudio de reevaluación."`
3. Ejecuta `COMMIT` por estudio/lote garantizando que un error puntual en un envío SMTP no detenga los demás recordatorios ni duplique avisos `APP`.
**Timeout**: `30s`
**Input**: `fecha_actual` (`hoy`).
**Output on SUCCESS**: Cantidad de avisos emitidos (`preaviso_30d`, `cumplimiento_anual`) -> END WORKFLOW.
**Output on FAILURE**:
  - `FAILURE(smtp_error)`: Mantiene `Aviso(CanalAviso.MAIL, enviado=False)` para reintento posterior sin impedir `CanalAviso.APP`.

**Observable states during this step**:
  - **Paciente & Médico see**: Notificación en campana de la app y correo electrónico recordando realizar el nuevo estudio dentro del año pautado.
  - **Database**: Nuevas filas en `avisos`.
  - **Logs**: `[cron_vus] STEP 3 recordatorios_vus procesados=<p> avisos_emitidos=<e>`

---

## State Transitions

*(Este workflow no altera `EstadoEstudio`, ya que opera sobre estudios ya en `RESULTADO_CARGADO`)*

| Evento | `resultados.diagnostico` | `resultados.fecha_proximo_estudio` | `estudios.fecha_reevaluacion_vus` |
|---|---|---|---|
| Resultado generado con >= 1 `VUS` y 0 `PATOGENICA` | `vus` | `fecha_generacion + 1 año` | `fecha_generacion + 1 año` |
| Resultado generado `positivo` o `negativo` sin VUS definitivo | `positivo` / `negativo` | `NULL` | `NULL` |
| Reanálisis futuro pasa el estudio a `positivo` o `negativo` | `positivo` / `negativo` *(en nuevo `Resultado`)* | `NULL` *(en nuevo `Resultado`)* | `NULL` *(auditado en `registro_modificaciones`)* |

---

## Handoff Contracts

| Origen | Destino | Payload / Garantía |
|---|---|---|
| Escenario 16 / 17 (`Cargar resultado`) | Escenario 43 (Rama A) | Persiste `diagnostico = 'vus'`, `fecha_proximo_estudio` y `Estudio.fecha_reevaluacion_vus` en la misma transacción. |
| Escenario 43 (Rama C - Aviso anual) | Escenario 01 (`Dar de alta estudio`) / Escenario 17 (`Reanalizar`) | El `Médico` y el `Paciente` cuentan con la información exacta para iniciar un nuevo estudio al año siguiente o reevaluación. |
| Escenario 43 | Escenario 42 (`Registro de modificaciones`) | Deja asentada la fecha de reevaluación asignada y eventuales actualizaciones. |

---

## Cleanup Inventory

- Si el cálculo o escritura en STEP 1 falla durante la carga del resultado (Escenario 16), el `ROLLBACK` transaccional evita que exista un `Resultado` VUS sin su `fecha_proximo_estudio` ni `fecha_reevaluacion_vus`.
- Idempotencia en el cron diario mediante clave/referencia del hito en `avisos` evita spam de correos diarios una vez alcanzado el año.

---

## Reality Checker Findings

- **Existente en `.ai/APIs/API_APIGen.md` (líneas 273-274, 488)**: Ya establecía como regla de negocio que ante un VUS `"El sistema del grupo programa una reevaluación al año"`, aunque esto no estaba modelado ni en `DER.md` ni en las tablas Python actuales.
- **Existente en código (`app/src/core/models/analisis.py` y `estudios.py`)**: Actualmente `Resultado` solo tiene `positivo: Mapped[bool]` (sin `diagnostico` ni `fecha_proximo_estudio`) y `Estudio` carece de `fecha_reevaluacion_vus`.
- **Pendiente de implementación**: Migración Alembic para columnas VUS, enum `ConclusionDiagnostica`, helper seguro `+ 1 año` en años bisiestos, endpoint `/seguimiento-vus` y cron diario.

---

## Test Cases

1. **TC-01 (Cálculo de +1 año ante diagnóstico VUS en Escenario 16)**: Al cargar variantes `[VUS]` el `2026-11-17`, `resultado.diagnostico == ConclusionDiagnostica.VUS`, `resultado.positivo == False`, `resultado.fecha_proximo_estudio == date(2027, 11, 17)` y `estudio.fecha_reevaluacion_vus == date(2027, 11, 17)`, quedando ambos en `registro_modificaciones` y PDF.
2. **TC-02 (Año bisiesto 29 de febrero)**: Resultado VUS emitido el `2024-02-29` calcula `fecha_proximo_estudio == date(2025, 2, 28)` sin lanzar `ValueError`.
3. **TC-03 (VUS + Patogénica simultáneas prevalece Positivo)**: Si existen una variante `PATOGENICA` y una `VUS`, `diagnostico == ConclusionDiagnostica.POSITIVO` y `fecha_proximo_estudio is None`.
4. **TC-04 (Recordatorios de 30 días y cumplimiento al año sin duplicación)**: Ejecutando el job diario 2 veces en la fecha de cumplimiento (`hoy == fecha_reevaluacion_vus`), emite exactamente 1 set de avisos (`Paciente` y `Médico`) y no duplica en la segunda ejecución.
5. **TC-05 (Visibilidad en agenda `/estudios/seguimiento-vus`)**: Un médico autorizado ve el estudio VUS en su agenda; un médico sin relación ve lista vacía / no ve pacientes ajenos.
6. **TC-06 (Supresión cuando ya se inició nuevo estudio/reanálisis)**: Si el paciente ya tiene un nuevo `Estudio` para la misma patología posterior al `Resultado` VUS, el cron no emite recordatorio redundante.

---

## Assumptions

- "Dentro de un año" equivale a **+1 año calendario** desde la fecha de emisión del resultado (`generado_en.date()`), disparando una alerta anticipada a los 30 días previos y un aviso el día exacto del vencimiento anual para dar margen de programación médica/turnos.
- La existencia de una variante `PATOGENICA` prevalece clínicamente sobre una variante `VUS` coexistente (`diagnostico = 'positivo'`).

---

## Open Questions

- Cuando el paciente vuelve al año tras un diagnóstico **VUS**, ¿el seguimiento se canaliza principalmente creando un nuevo `Estudio` (Escenario 01, tomando nueva muestra o presupuesto según cobertura) o como `Reanálisis` gratuito sobre `Datos crudos` existentes (Escenario 17)? *(El diseño actual soporta ambas vías y deja de notificar si detecta cualquiera de los dos iniciado después del resultado VUS).*

---

## Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-11-17 | Especificación creada para el Requerimiento 7 y ADR-004 (guardado de fecha a 1 año por diagnóstico VUS y recordatorio de seguimiento). | Aprobada; alineada con `.ai/APIs/API_APIGen.md` e incorporada a `Escenario 16`, `17` y `37`. |
