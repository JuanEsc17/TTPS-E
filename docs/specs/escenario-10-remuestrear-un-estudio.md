# WORKFLOW: Escenario 10 – Remuestrear un estudio
**Versión**: 2.0
**Fecha**: 2026-11-17
**Autor**: Workflow Architect & Software Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-10`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Administrativo`, `Paciente`, `Médico` |
| **Objetos** | `Muestra`, `Estudio`, `Sample set`, `Turno`, `Registro de modificaciones`, `Aviso` |
| **Verbos** | `Remuestrear`, `Sacar turno`, `Registrar modificación` |
| **Estados** | `En viaje a Corea`, `En laboratorio central`, `En espera de retiro`, `Remuestreo requerido`, `Turno sacado` |

---

## Overview

- **Objetivo**: Permitir al `Administrativo` indicar que una `Muestra` llegada a Corea presenta **baja calidad** (u otra falla técnica no volumétrica) y retroceder individualmente el `Estudio` al estado `Remuestreo requerido` (`EstadoEstudio.REMUESTREO_REQUERIDO`), habilitando al `Paciente` a solicitar un nuevo `Turno` de extracción sin costo adicional.
- **Contexto**: Conforme al Requerimiento 5 y **ADR-004**, **se elimina por completo la regla y posibilidad de descarte por muestra menor a `2 ml`** (`ML_MINIMOS_TUBO` / `VOLUMEN_INSUFICIENTE` deprecados). El desencadenante principal ocurre cuando una muestra enviada en un `Sample set` arriba al laboratorio de Corea (`EstadoEstudio.EN_VIAJE_COREA`) y Corea reporta que no es apta por baja calidad (`MotivoDescarte.BAJA_CALIDAD`, o eventualmente `ADN_INSUFICIENTE` / `DESNATURALIZADA`). El `Administrativo` declara el remuestreo y retrocede el `Estudio` sin alterar la composición histórica del `Sample set` ya despachado.
- **Recursos**: `Estudio` (`estudios`), `Muestra` (`muestras`), `SampleSet` (`sample_sets`, solo lectura para preservar envío histórico), `Registro de modificaciones` (`registro_modificaciones`), `Aviso` (`avisos`).
- **Episodios**:
  1. El laboratorio recibe el reporte desde Corea indicando que la muestra llegó con **baja calidad** y no puede ser secuenciada.
  2. El `Administrativo` selecciona el `Estudio` en estado `En viaje a Corea` (o `En laboratorio central` / `En espera de retiro` ante desnaturalización/ADN insuficiente), registra el motivo de descarte (`BAJA_CALIDAD`, `ADN_INSUFICIENTE` o `DESNATURALIZADA`) y el motivo del retroceso.
  3. El sistema descarta la `Muestra` vigente (`motivo_descarte`, `observaciones_calidad`) manteniendo inalterado el `SampleSet` ya enviado, retrocede `Estudio.estado` a `EstadoEstudio.REMUESTREO_REQUERIDO` y asienta el evento en `registro_modificaciones`.
  4. El sistema notifica por `Aviso` al `Paciente` (para que saque nuevo turno sin costo en Escenario 07) y al `Médico` tratante.
  5. El `Paciente` saca un nuevo `Turno` (Escenario 07) pasando el estudio de `Remuestreo requerido` -> `Turno sacado` -> nueva `Muestra` en Escenario 09.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Administrativo` | Registra la novedad de baja calidad reportada por Corea (o lab central), indica que se necesita remuestreo y retrocede el `Estudio`. |
| `Paciente` | Recibe la notificación urgente de remuestreo y agenda un nuevo `Turno` de extracción sin volver a abonar ni reautorizar. |
| `Médico` | Recibe el `Aviso` informando el retroceso a `Remuestreo requerido` y la demora clínica asociada. |
| `router` (`estudios_router` / `logistica_router`) | Expone `POST /api/v1/estudios/{estudio_id}/remuestreo`. |
| `service` (`logistica_service` / `estudio_service`, `auditoria_service`) | Valida el rol, bloquea el estudio y su muestra vigente, aplica el rollback atómico de estado y registra en `registro_modificaciones`. |
| `repo` (`estudio_repo`, `logistica_repo`, `auditoria_repo`, `usuario_repo`) | Opera sobre `muestras`, `estudios`, `registro_modificaciones` y `avisos`. |

---

## Prerequisites

- Usuario autenticado con `Rol.ADMINISTRATIVO` (o `Rol.ADMIN_GENERAL` / `Rol.GERENTE_MEDICO` si opera como administrativo supervisor).
- El `Estudio` (`estudios.id == estudio_id`) se encuentra en `EstadoEstudio.EN_VIAJE_COREA` (caso principal al arribar a Corea), o en `EstadoEstudio.EN_LAB_CENTRAL` / `EstadoEstudio.EN_ESPERA_RETIRO` ante contingencia técnica no volumétrica (desnaturalización o ADN insuficiente).
- Existe una `Muestra` vigente (`muestras.estudio_id == estudio.id AND motivo_descarte IS NULL`).
- El motivo indicado pertenece a `{BAJA_CALIDAD, ADN_INSUFICIENTE, DESNATURALIZADA}`; está **explícitamente prohibido** descartar por volumen `< 2 ml`.

---

## Trigger

El `Administrativo` solicita el remuestreo y rollback del estudio mediante:
- **Endpoint HTTP**: `POST /api/v1/estudios/{estudio_id}/remuestreo` (autenticado como `Administrativo`).
- **Payload**: `{ "motivo_descarte": "baja_calidad", "observaciones_calidad": "Muestra hemolizada al arribo en Corea según reporte lote #12", "motivo": "Reporte de baja calidad recibido desde Corea; requiere nueva extracción" }`.

---

## Workflow Tree

### STEP 1: Validación de rol administrativo, estudio, muestra vigente y motivo de calidad
**Actor**: `Administrativo` -> `router` -> `service` (`logistica_service`) -> `repo` (`estudio_repo`, `logistica_repo`)
**Action**:
1. Verifica que `usuario_actual.rol == Rol.ADMINISTRATIVO` (o superior administrativo habilitado); si es `Paciente`, `Médico`, `Bioinformático` o `Transportista`, rechaza con `403 Forbidden`.
2. Valida que `motivo_descarte` pertenezca a `MotivoDescarte = {BAJA_CALIDAD, ADN_INSUFICIENTE, DESNATURALIZADA}` y que `motivo` no esté vacío. *(Si llega `"volumen_insuficiente"` o referencia a `< 2 ml`, rechaza con `422 Unprocessable Entity`.)*
3. Carga y bloquea el `Estudio` (`SELECT ... FOR UPDATE`) y localiza `estudio.muestra_vigente` (`motivo_descarte IS NULL`).
4. Verifica que `estudio.estado in (EstadoEstudio.EN_VIAJE_COREA, EstadoEstudio.EN_LAB_CENTRAL, EstadoEstudio.EN_ESPERA_RETIRO)`.
   - Rechaza estados donde ya se subieron datos crudos o aún no se tomó muestra (`RESULTADO_CARGADO`, `EN_ANALISIS_BIOINFORMATICA`, `EN_ANALISIS_BIOINFORMATICO`, `CREADO`, `PENDIENTE_AUTORIZACION`, `RECHAZADO`, `TURNO_SACADO`, `REMUESTREO_REQUERIDO`).
**Timeout**: `2s`
**Input**: `estudio_id`, `motivo_descarte`, `observaciones_calidad`, `motivo`, `usuario_actual`.
**Output on SUCCESS**: `Estudio` y `Muestra` bloqueados -> `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Usuario sin rol administrativo -> `return 403 Forbidden` (`ROL_NO_AUTORIZADO`).
  - `FAILURE(not_found)`: `estudio_id` inexistente -> `return 404 Not Found`.
  - `FAILURE(no_valid_sample)`: El estudio no tiene muestra vigente sin descartar -> `return 409 Conflict` (`SIN_MUESTRA_VIGENTE`).
  - `FAILURE(invalid_state)`: El estudio no está en estado apto para rollback por calidad -> `return 409 Conflict` (`ESTADO_ESTUDIO_INVALIDO_PARA_REMUESTREO`).
  - `FAILURE(deprecated_reason)`: Intento de descartar por `< 2 ml` / `volumen_insuficiente` -> `return 422 Unprocessable Entity` (`MOTIVO_DESCARTE_OBSOLETO`).

**Observable states during this step**:
  - **Administrativo sees**: Spinner `"Registrando solicitud de remuestreo..."`.
  - **Database**: Bloqueo `FOR UPDATE` sobre `estudios` y `muestras`.
  - **Logs**: `[logistica_service] STEP 1 remuestreo_validado estudio_id=<eid> estado=<est> muestra_id=<mid>`

---

### STEP 2: Descarte de la `Muestra` vigente, rollback de `Estudio` y preservación histórica del `SampleSet`
**Actor**: `service` (`logistica_service`, `auditoria_service`) -> `repo` (`logistica_repo`, `estudio_repo`, `auditoria_repo`)
**Action**:
1. Marca únicamente la `Muestra` vigente con falla de calidad:
   - `muestra_vigente.motivo_descarte = input.motivo_descarte` (típicamente `MotivoDescarte.BAJA_CALIDAD`)
   - `muestra_vigente.observaciones_calidad = input.observaciones_calidad`
   - Conserva intacta la referencia histórica `muestra_vigente.sample_set_id` (en caso de haber viajado en un `SampleSet` enviado a Corea) para que el envío histórico permanezca fiel a lo despachado en FedEx y los demás estudios del mismo `SampleSet` continúen su curso normal.
2. Conserva `estado_anterior = estudio.estado` y retrocede el estado del `Estudio`:
   - `estudio.estado = EstadoEstudio.REMUESTREO_REQUERIDO` (`"Remuestreo requerido"`).
   - No modifica `estudio.ausencias`, `presupuesto`, `pagos`, `cuotas` ni `autorizaciones` (el remuestreo nunca cobra cargo extra ni anula el pago vigente).
3. Registra la modificación de forma atómica en `registro_modificaciones` (`AuditoriaService.registrar_modificacion`):
   - `entidad_tipo = EntidadAuditable.ESTUDIO`
   - `entidad_id = estudio.id`
   - `accion = TipoAccionAuditoria.CAMBIO_ESTADO`
   - `usuario_id = usuario_actual.id`
   - `origen = 'usuario'`
   - `cambios = { "estado": {"anterior": estado_anterior.value, "nuevo": EstadoEstudio.REMUESTREO_REQUERIDO.value}, "muestra_descartada_id": {"anterior": None, "nuevo": muestra_vigente.id}, "motivo_descarte": {"anterior": None, "nuevo": input.motivo_descarte.value} }`
   - `motivo = input.motivo`
**Timeout**: `2s`
**Input**: `Estudio`, `Muestra`, `motivo_descarte`, `observaciones_calidad`, `motivo`.
**Output on SUCCESS**: `Estudio` retrocedido a `REMUESTREO_REQUERIDO` y evento auditado -> `GO TO STEP 3`
**Output on FAILURE**:
  - `FAILURE(db_error)`: Error de base de datos -> `ROLLBACK` total; nada cambia.

**Observable states during this step**:
  - **Administrativo sees**: Estado del estudio actualizado a `"Remuestreo requerido"`. El `SampleSet` del envío conserva su listado original para trazabilidad aduanera/FedEx.
  - **Database**: `muestras.motivo_descarte != NULL`, `estudios.estado = 'Remuestreo requerido'`, nueva fila en `registro_modificaciones`.
  - **Logs**: `[logistica_service] STEP 2 rollback_remuestreo estudio_id=<eid> de=<estado_ant> a=REMUESTREO_REQUERIDO muestra_id=<mid>`

---

### STEP 3: Notificaciones urgentes a `Paciente` y `Médico` y habilitación de nuevo `Turno`
**Actor**: `service` (`logistica_service`) -> `repo` (`usuario_repo`)
**Action**:
1. Inserta `Aviso` para `estudio.paciente.usuario_id`:
   - Mensaje: `"Su muestra enviada para análisis no alcanzó la calidad técnica requerida (${motivo_descarte}). El estudio #${estudio.id} volvió a Remuestreo requerido. Por favor solicite un nuevo turno de extracción sin costo adicional."`
2. Inserta `Aviso` para `estudio.medico.usuario_id` (y médicos autorizados si aplica):
   - Mensaje: `"La muestra del paciente ${paciente_nombre} (Estudio #${estudio.id}) presentó ${motivo_descarte} y fue retrocedida a Remuestreo requerido."`
3. Ejecuta `COMMIT` único transaccional.
**Timeout**: `2s`
**Input**: `Estudio`, `Muestra`, usuarios destinatarios.
**Output on SUCCESS**: `200 OK` con `{ estudio_id, estado_anterior, estado_nuevo: "Remuestreo requerido", muestra_descartada_id, motivo_descarte, aviso_paciente_id, aviso_medico_id }` -> END WORKFLOW *(el `Paciente` continúa en Escenario 07 -> Escenario 09)*.
**Output on FAILURE**:
  - `FAILURE(notification_error)`: Si falla la inserción del `Aviso` dentro de la transacción -> `ROLLBACK` para garantizar consistencia entre cambio de estado, auditoría y notificación al paciente.

**Observable states during this step**:
  - **Paciente sees**: `Aviso` urgente en su bandeja y botón habilitado `"Sacar nuevo turno (Remuestreo sin costo)"` en Escenario 07.
  - **Médico sees**: `Aviso` clínico y estado del estudio reflejado como `"Remuestreo requerido"`.
  - **Administrativo sees**: Confirmación de rollback ejecutado y estudio excluido de recepción de datos crudos hasta recibir la nueva muestra.
  - **Logs**: `[logistica_service] STEP 3 remuestreo_notificado estudio_id=<eid>`

---

## State Transitions

| Estado Origen (`EstadoEstudio`) | Condición / Motivo | Estado Destino (`EstadoEstudio`) | Impacto en `SampleSet` y `Pago` |
|---|---|---|---|
| `En viaje a Corea` (`EN_VIAJE_COREA`) | Falla de calidad reportada desde Corea (`MotivoDescarte.BAJA_CALIDAD` / `ADN_INSUFICIENTE` / `DESNATURALIZADA`) | `Remuestreo requerido` (`REMUESTREO_REQUERIDO`) | **No altera `SampleSet` ni anula `Pago` / `Cuotas`**. |
| `En laboratorio central` (`EN_LAB_CENTRAL`) o `En espera de retiro` (`EN_ESPERA_RETIRO`) | Contingencia técnica no volumétrica (`DESNATURALIZADA` / `ADN_INSUFICIENTE` / `BAJA_CALIDAD`) | `Remuestreo requerido` (`REMUESTREO_REQUERIDO`) | La muestra no ingresa a nuevo `SampleSet` (si no tenía `sample_set_id`). |
| `Remuestreo requerido` (`REMUESTREO_REQUERIDO`) | `Paciente` agenda nuevo turno en Escenario 07 | `Turno sacado` (`TURNO_SACADO`) | Crea nuevo `Turno`; `muestra_vigente` sigue siendo `None` hasta Escenario 09. |

---

## Handoff Contracts

| Origen | Destino | Payload / Garantía |
|---|---|---|
| Reporte de laboratorio en Corea | `POST /api/v1/estudios/{estudio_id}/remuestreo` | El `Administrativo` ingresa `motivo_descarte`, `observaciones_calidad` y `motivo`. |
| Escenario 10 | Escenario 07 (`Sacar turno`) | `estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO` habilita de inmediato solicitar un nuevo turno sin pagar de nuevo ni alterar cuotas vigentes. |
| Escenario 09 (`Toma de nueva muestra`) | `Estudio.muestra_vigente` | La 2.ª fila en `muestras` (`motivo_descarte = None`) pasa a ser `estudio.muestra_vigente`, permitiendo reiniciar el circuito logístico desde `Lista para retirar`. |
| Escenario 10 | Escenario 42 (`Registro de modificaciones`) | Deja trazabilidad completa de estado anterior/nuevo, muestra descartada, administrativo responsable y motivo. |

---

## Cleanup Inventory

- Ningún `Pago` ni `Cuota` se anula durante un remuestreo (a diferencia de las 5 ausencias del Escenario 33).
- Si la muestra había integrado un `SampleSet` enviado a Corea, **no se borra ni desvincula** `muestra.sample_set_id` ni se modifica `sample_sets.csv_path` ni los demás estudios que viajaron en esa caja.
- Si luego de tomarse la 2.ª muestra el estudio vuelve a viajar en un futuro `SampleSet`, solo se incluirá la 2.ª muestra vigente (`sample_set_id IS NULL AND motivo_descarte IS NULL`).

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | **[BRECHA DETECTADA]** `app/src/core/models/reglas.py` todavía define `ML_MINIMOS_TUBO = 2` y `app/src/core/models/enums.py` aún define `MotivoDescarte.VOLUMEN_INSUFICIENTE = "volumen_insuficiente"` (sin `MotivoDescarte.BAJA_CALIDAD`). | High | Prerequisites, STEP 1, STEP 2 | Eliminar `ML_MINIMOS_TUBO` y `VOLUMEN_INSUFICIENTE`, agregando `MotivoDescarte.BAJA_CALIDAD = "baja_calidad"` en la próxima actualización SDD del modelo. |
| RC-2 | **[BRECHA DETECTADA]** `app/src/core/models/logistica.py` aún contiene `Muestra.mililitros` y carece de `Muestra.observaciones_calidad`; `tests/test_escenario_11_logistica.py` prueba `ML_MINIMOS_TUBO` / rechazo `< 2 ml`. | High | STEP 1, STEP 2 | Remover la lógica de `< 2 ml` en `logistica_service.py` y adaptar tests al remuestreo desde `EN_VIAJE_COREA` por `BAJA_CALIDAD`. |
| RC-3 | **[BRECHA DETECTADA]** No existe aún el endpoint `POST /api/v1/estudios/{estudio_id}/remuestreo` ni la llamada a `AuditoriaService` en `logistica_service.py`. | Medium | Trigger, STEP 2 | Implementar router, método de servicio y auditoría antes de cerrar SDD del Escenario 10. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| **TC-01: Remuestreo desde Corea por baja calidad (`BAJA_CALIDAD`)** | `Administrativo` llama `POST /api/v1/estudios/{id}/remuestreo` con `motivo_descarte = "baja_calidad"` para un estudio en `EstadoEstudio.EN_VIAJE_COREA` perteneciente al `SampleSet #7`. | Retorna `200 OK`; `muestra_1.motivo_descarte = BAJA_CALIDAD` (conservando `sample_set_id = 7`); `SampleSet #7` y los otros 9 estudios del lote no cambian; `estudio.estado = REMUESTREO_REQUERIDO`; se registra en `registro_modificaciones`; se notifican `Paciente` y `Médico`. |
| **TC-02: Rechazo explícito de regla obsoleta `< 2 ml` / `volumen_insuficiente`** | Se intenta enviar `motivo_descarte = "volumen_insuficiente"`. | Retorna `422 Unprocessable Entity` (`MOTIVO_DESCARTE_OBSOLETO`); no se descarta la muestra ni retrocede el estudio. |
| **TC-03: Ciclo completo de 2.ª muestra tras rollback desde Corea** | Tras TC-01, el paciente saca un 2.º turno (Esc. 07), el centro informa toma por Telegram (Esc. 09) y el transportista la lleva al lab central (Esc. 11). | `Estudio` transiciona `REMUESTREO_REQUERIDO -> TURNO_SACADO -> LISTA_PARA_RETIRAR -> EN_ESPERA_RETIRO -> EN_LAB_CENTRAL`; `estudio.muestra_vigente` es la 2.ª muestra (`sample_set_id = None`), apta para integrarse a un nuevo `SampleSet`. |
| **TC-04: Bloqueo de permiso para rol no administrativo** | Un `Paciente`, `Médico` o `Transportista` intenta invocar `POST /api/v1/estudios/{id}/remuestreo`. | Retorna `403 Forbidden` sin alterar DB. |
| **TC-05: Rechazo por estado inválido (ej. ya en bioinformática o resultado cargado)** | Se intenta remuestrear un estudio en `EstadoEstudio.EN_ANALISIS_BIOINFORMATICA` o `RESULTADO_CARGADO`. | Retorna `409 Conflict` (`ESTADO_ESTUDIO_INVALIDO_PARA_REMUESTREO`). |
| **TC-06: Remuestreo preserva Pago/Cuotas vigentes y contador de ausencias** | Estudio con plan de 3 cuotas (`Pago.estado == PARCIAL`, cuota #1 pagada) retrocede a `REMUESTREO_REQUERIDO`. | `Pago` sigue `anulado = False`; el paciente puede sacar nuevo turno sin recargos. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El reporte de falla de calidad en Corea llega al laboratorio central fuera de banda (correo/portal de Corea) y el `Administrativo` lo carga en el sistema sobre el `Estudio` afectado. | Requerimiento 5 del usuario + `.ai/3-Escenarios.md#Escenario-10`. | Bajo (si en el futuro hubiera webhook de Corea, reutilizaría el mismo servicio). |
| A2 | El remuestreo nunca genera un nuevo cobro ni reinicia cuotas ya emitidas; solo reabre el ciclo de extracción. | `.ai/1-Entrevista.md` + ADR-004. | Bajo. |

---

## Open Questions

- Si un estudio falla dos veces por `BAJA_CALIDAD` al llegar a Corea, ¿existe algún límite máximo de remuestreos antes de requerir revisión del `Gerente médico`, o siempre vuelve a `Remuestreo requerido` mientras el `Administrativo` lo autorice? *(Por defecto, sin tope automático; toda reiteración queda visible en `muestras` y `registro_modificaciones`).*

---

## Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial v1.0 creada alrededor de `ML_MINIMOS_TUBO = 2` y `MotivoDescarte.VOLUMEN_INSUFICIENTE`. | Aprobada inicialmente en v1.0. |
| 2026-11-17 | Reescritura mayor a v2.0 por Requerimientos 5 y 6 (ADR-003 y ADR-004): eliminada por completo la regla de muestra `< 2 ml`; flujo centrado en reporte de `BAJA_CALIDAD` al arribar a Corea y rollback por `Administrativo` desde `EN_VIAJE_COREA` hacia `REMUESTREO_REQUERIDO` sin alterar `SampleSet` histórico y con auditoría obligatoria. | Actualizada a v2.0; documentadas brechas explícitas contra `reglas.py`, `enums.py` y `logistica.py` en Reality Checker Findings. |
