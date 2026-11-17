# WORKFLOW: Escenario 41 – Vincular y consultar estudios de familiares del familiograma
**Versión**: 1.0
**Fecha**: 2026-11-17
**Autor**: Workflow Architect & Software Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-41`

---

## Símbolos LEL utilizados

| Categoría LEL | Símbolos utilizados |
|---|---|
| **Sujetos** | `Médico`, `Paciente` |
| **Objetos** | `Estudio`, `Familiar`, `Familiograma`, `Vínculo de estudios familiares`, `Registro de modificaciones`, `Resultado`, `Aviso` |
| **Verbos** | `Vincular estudios familiares`, `Dar de alta estudio`, `Dar de alta paciente`, `Descargar resultado`, `Registrar modificación` |
| **Estados** | *(No altera `EstadoEstudio`; crea relaciones persistentes en `estudios_familiares_vinculados`)* |

---

## Overview

- **Objetivo**: Vincular automáticamente en la tabla de estudios vinculados cualquier `Estudio` de un `Familiar` declarado en el **familiograma** de un paciente original con los `Estudios` de dicho paciente original (bidireccionalmente), y permitir al `Médico` navegar directamente desde el estudio de un paciente `X` hacia el estudio y resultado del familiar `X'`.
- **Contexto**: En enfermedades genéticas hereditarias (Fabry, Pompe, MPS1, Gaucher, ASMD), un paciente índice (`X`) registra familiares en su familiograma (Escenario 18). Si tiempo después o previamente uno de esos familiares (`X'`) se realiza un estudio genético en el sistema, el médico que evalúa el estudio de `X` necesita visualizar el estudio vinculado de `X'` (y viceversa) sin búsquedas manuales repetidas. Según ADR-002, el matching determinístico opera por `Familiar.paciente_vinculado_id` o coincidencia exacta de `Familiar.dni == Paciente.dni`.
- **Recursos**: `Familiar` (`familiares`), `Paciente` (`pacientes`), `Estudio` (`estudios`), `Vínculo de estudios familiares` (`estudios_familiares_vinculados`), `Registro de modificaciones` (`registro_modificaciones`), `Resultado` (`resultados`).
- **Episodios**:
  1. Al darse de alta un `Estudio` (Escenario 01), darse de alta un `Paciente` (Escenarios 18/19) o actualizarse un `Familiar` con `dni`, el sistema detecta coincidencias entre `familiares` (`dni` o `paciente_vinculado_id`) y `pacientes`.
  2. El sistema actualiza `familiar.paciente_vinculado_id` cuando corresponde e inserta pares bidireccionales en `estudios_familiares_vinculados` entre los estudios del paciente original y los estudios del familiar.
  3. El sistema registra los nuevos vínculos en `registro_modificaciones` (`entidad_tipo = 'estudio'`).
  4. El `Médico` abre el detalle del estudio de `X`, visualiza la tabla/sección `"Estudios familiares vinculados"` y navega al detalle y resultado del estudio de `X'`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Médico` | Consulta el estudio de un paciente `X` y navega hacia el estudio vinculado del familiar `X'`. |
| `Sistema (EstudioService / PacienteService)` | Ejecuta la detección determinística por DNI / ID vinculado y materializa vínculos simétricos en `estudios_familiares_vinculados`. |
| `router` (`estudios_router`, `pacientes_router`) | Expone `GET /api/v1/estudios/{estudio_id}/familiares-vinculados` y `GET /api/v1/estudios/{estudio_id}/familiares-vinculados/{estudio_relacionado_id}`. |
| `service` (`estudio_service`, `auditoria_service`) | Orquesta la vinculación automática transaccional, auditoría y validación de acceso médico entre estudios vinculados. |
| `repo` (`estudio_repo`, `clinica_repo`, `paciente_repo`, `auditoria_repo`, `usuario_repo`) | Consulta `familiares`, `pacientes`, `estudios` y persiste `estudios_familiares_vinculados`, `registro_modificaciones` y `avisos`. |

---

## Prerequisites

- Para **Rama A (Vinculación automática)**:
  - Existencia de un registro en `familiares` con `dni` normalizado (o `paciente_vinculado_id`) perteneciente al familiograma de un `Paciente` `P_orig`.
  - Existencia de al menos un `Estudio` asociado al paciente original `P_orig` y al menos un `Estudio` asociado al familiar-paciente `P_fam`.
- Para **Rama B (Consulta médica desde estudio X)**:
  - Usuario autenticado con `Rol.MEDICO` (o `Rol.GERENTE_MEDICO`) autorizado sobre el estudio origen `X` (`estudio_x.medico_id == medico.id` O autorización activa en `pacientes_medicos_autorizados` para `estudio_x.paciente_id`).
  - Existencia del registro `(estudio_x.id, estudio_x_prima.id)` en `estudios_familiares_vinculados`.

---

## Trigger

1. **Trigger automático A1 (Alta de estudio)**: Ejecutado dentro de la transacción de `POST /api/v1/estudios` (Escenario 01).
2. **Trigger automático A2 (Alta/actualización de paciente o familiar)**: Ejecutado dentro de la transacción de `POST /api/v1/pacientes` (Escenarios 18 y 19) o `PATCH /api/v1/pacientes/{id}/familiares` cuando se incorpora o completa `dni`.
3. **Trigger manual / consulta B1 (Listado vinculado en estudio X)**: `GET /api/v1/estudios/{estudio_id}/familiares-vinculados`.
4. **Trigger manual / consulta B2 (Navegación desde estudio X a estudio X')**: `GET /api/v1/estudios/{estudio_id}/familiares-vinculados/{estudio_relacionado_id}`.

---

## Workflow Tree

### STEP 1 (Rama A): Resolución de identidad entre `Familiar` y `Paciente`
**Actor**: `service` (`estudio_service` / `paciente_service`) -> `repo` (`clinica_repo`, `paciente_repo`)
**Action**:
1. **Dirección 1 (El paciente del estudio/alta aparece como `Familiar` en familiogramas ajenos)**:
   - Normaliza `paciente.dni` (trim, solo dígitos).
   - Busca filas en `familiares` donde `(familiar.paciente_vinculado_id == paciente.id OR familiar.dni == paciente.dni)` AND `familiar.paciente_id != paciente.id`.
   - Para cada fila con `familiar.paciente_vinculado_id IS NULL`, actualiza `familiar.paciente_vinculado_id = paciente.id`.
2. **Dirección 2 (El paciente tiene `Familiares` en su propio familiograma que corresponden a otros `Pacientes`)**:
   - Recorre las filas en `familiares` donde `familiar.paciente_id == paciente.id`.
   - Si `familiar.paciente_vinculado_id IS NULL` y `familiar.dni IS NOT NULL`, busca en `pacientes` por `pacientes.dni == familiar.dni` (y distinto de `paciente.id`). Si encuentra coincidencia, asigna `familiar.paciente_vinculado_id = paciente_encontrado.id`.
3. Recolecta la lista de tuplas `(familiar_row, paciente_original, paciente_familiar)`.
**Timeout**: `2s`
**Input**: `paciente_id`, `estudio_id` (opcional si es alta de paciente aún sin estudio).
**Output on SUCCESS**: Lista de coincidencias familiares -> Si vacía: no crea vínculos; Si no vacía: `GO TO STEP 2`
**Output on FAILURE**:
  - `FAILURE(self_link_ignored)`: Si por error de carga `familiar.dni == paciente.dni` del mismo paciente dueño del familiograma, ignora la auto-vinculación respetando `CHECK(estudio_origen_id <> estudio_relacionado_id)`.

**Observable states during this step**:
  - **Paciente / Médico sees**: Operación transparente dentro del alta del estudio o paciente.
  - **Database**: Actualización eventual de `familiares.paciente_vinculado_id`.
  - **Logs**: `[estudio_service] STEP 1 matching_familiar paciente_id=<pid> coincidencias=<n>`

---

### STEP 2 (Rama A): Creación bidireccional en `estudios_familiares_vinculados` y auditoría
**Actor**: `service` (`estudio_service`, `auditoria_service`) -> `repo` (`estudio_repo`, `auditoria_repo`, `usuario_repo`)
**Action**:
1. Para cada coincidencia `(familiar_row, p_orig, p_fam)`:
   - Obtiene todos los `Estudio` de `p_orig` y todos los `Estudio` de `p_fam`.
   - Si existe filtro en el trigger de alta de un estudio específico `E_nuevo`, igual garantiza la creación de todos los pares faltantes `(E_a, E_b)` y `(E_b, E_a)` con `E_a.id != E_b.id`.
2. Para cada par `(e_orig, e_rel)`:
   - Determina la etiqueta de `parentesco` relativa para ambas direcciones (ej. desde `p_orig` hacia `p_fam` usa `familiar_row.parentesco`; en la dirección inversa usa etiqueta normalizada o `"Familiar vinculado ({familiar_row.parentesco})"` cuando no haya tabla simétrica).
   - Ejecuta inserción idempotente (`ON CONFLICT (estudio_origen_id, estudio_relacionado_id) DO NOTHING`) en `estudios_familiares_vinculados` con `familiar_id = familiar_row.id`.
3. Por cada nuevo vínculo efectivamente insertado en ambos sentidos:
   - Invoca `AuditoriaService.registrar_modificacion(...)` sobre `e_orig` y `e_rel`:
     - `entidad_tipo = EntidadAuditable.ESTUDIO`, `entidad_id = e.id`, `accion = TipoAccionAuditoria.MODIFICACION`
     - `cambios = {"vinculo_familiar_agregado": {"anterior": None, "nuevo": {"estudio_relacionado_id": otro_id, "parentesco": parentesco, "familiar_id": familiar_row.id}}}`
     - `motivo = "Vinculación automática por familiograma (Escenario 41)"`
   - Inserta un `Aviso` para los médicos tratantes responsables de `e_orig` y `e_rel`: `"Se vinculó automáticamente el estudio #<id_otro> de un familiar registrado en el familiograma del estudio #<id_propio>."`
4. Consolida dentro de la misma transacción (`COMMIT` del workflow padre).
**Timeout**: `3s`
**Input**: Lista de coincidencias y sus estudios.
**Output on SUCCESS**: Vínculos bidireccionales persistidos y auditados -> END RAMA A.
**Output on FAILURE**:
  - `FAILURE(db_error)`: Error de persistencia -> `ROLLBACK` completo de la transacción padre, manteniendo integridad atómica.

**Observable states during this step**:
  - **Médico sees**: `Aviso` de nuevo estudio familiar vinculado; la pestaña/tabla `"Estudios familiares vinculados"` del estudio se actualiza automáticamente.
  - **Database**: Dos filas por par en `estudios_familiares_vinculados` (`(A, B)` y `(B, A)`), entradas en `registro_modificaciones` y `avisos`.
  - **Logs**: `[estudio_service] STEP 2 vinculos_familiares_creados pares=<k>`

---

### STEP 3 (Rama B): Consulta de la tabla de `Estudios` familiares vinculados desde el estudio de `X`
**Actor**: `Médico` -> `router` -> `service` (`estudio_service`) -> `repo` (`estudio_repo`, `paciente_repo`)
**Action**:
1. Verifica `Rol.MEDICO` (o `Rol.GERENTE_MEDICO`).
2. Verifica que el `Médico` tiene permiso de acceso al estudio origen `X` (`estudio.medico_id == medico.id` O autorización activa en `pacientes_medicos_autorizados` para `estudio.paciente_id`).
3. Consulta `estudios_familiares_vinculados WHERE estudio_origen_id == estudio_id` haciendo `JOIN` con `estudios`, `pacientes`, `usuarios`, `patologias` y el último `analisis -> resultado` si existiera.
4. Retorna la lista estructurada para renderizar en la vista del estudio `X`.
**Timeout**: `2s`
**Input**: `estudio_id` (`X`), `usuario_actual`.
**Output on SUCCESS**: `200 OK` con `{ estudio_origen_id: X, familiares_vinculados: [{ estudio_relacionado_id, paciente_nombre_completo, parentesco, patologia_sospechada, estado_estudio, tiene_resultado, conclusion_diagnostica, fecha_reevaluacion_vus, created_at }] }`.
**Output on FAILURE**:
  - `FAILURE(not_found)`: `estudio_id` inexistente -> `return 404 Not Found`.
  - `FAILURE(forbidden)`: El médico no atiende ni está autorizado sobre el paciente de `X` -> `return 403 Forbidden`.

**Observable states during this step**:
  - **Médico sees**: Dentro del estudio de `X`, una tabla `"Estudios de familiares vinculados"` con cada estudio `X'`, parentesco, patología, estado actual y enlace `"Ver estudio vinculado"`.
  - **Database**: Lectura `JOIN` sobre `estudios_familiares_vinculados`, `estudios`, `pacientes`, `patologias`, `resultados`.
  - **Logs**: `[estudio_service] STEP 3 vinculos_consultados estudio_id=<eid> medico_id=<mid>`

---

### STEP 4 (Rama B): Navegación y visualización desde el estudio de `X` hacia el estudio del familiar `X'`
**Actor**: `Médico` -> `router` -> `service` (`estudio_service`) -> `repo` (`estudio_repo`, `analisis_repo`)
**Action**:
1. Verifica que el `Médico` tenga acceso al estudio origen `X` (mismas reglas del STEP 3).
2. Verifica que exista la fila `(estudio_origen_id = X, estudio_relacionado_id = X')` en `estudios_familiares_vinculados`. *(Sin esta relación verificada y sin autorización directa sobre `X'`, deniega el acceso con `403 Forbidden`.)*
3. Carga el detalle clínico autorizado del estudio `X'`:
   - Datos del `Estudio` (`id`, `patologia_sospechada`, `estado`, `genes` evaluados, `es_pompe_urgente`, `fecha_reevaluacion_vus`, `created_at`).
   - Datos mínimos de contexto del familiar (`parentesco` declarado, nombre y apellido; **excluye** datos de facturación/MercadoPago/cuotas o historia clínica completa privada de `X'` si el médico no está autorizado explícitamente sobre el perfil del paciente `X'`).
   - Análisis bioinformático, variantes detectadas y estado del `Resultado` (incluyendo diagnóstico `positivo | negativo | vus`, `fecha_proximo_estudio` y URL de descarga segura del PDF conforme al Escenario 37 cuando el acceso se realiza a través de este vínculo verificado).
**Timeout**: `2s`
**Input**: `estudio_id` (`X`), `estudio_relacionado_id` (`X'`), `usuario_actual`.
**Output on SUCCESS**: `200 OK` con ficha clínica comparativa del estudio `X'` y enlace para descargar PDF / volver al estudio `X` -> END RAMA B.
**Output on FAILURE**:
  - `FAILURE(not_found)`: No existe vínculo entre `X` y `X'` -> `return 404 Not Found` (`VINCULO_FAMILIAR_NO_ENCONTRADO`).
  - `FAILURE(forbidden)`: El médico no posee acceso válido al estudio origen `X` -> `return 403 Forbidden`.

**Observable states during this step**:
  - **Médico sees**: Vista de detalle del estudio de `X'` navegada desde `X`, mostrando variantes halladas, diagnóstico, enlace a resultado PDF (si existe) y botón `"Volver al estudio #<X>"`.
  - **Database**: Lectura de solo lectura validada contra `estudios_familiares_vinculados`.
  - **Logs**: `[estudio_service] STEP 4 estudio_familiar_abierto origen=<X> relacionado=<X'> medico_id=<mid>`

---

## State Transitions

*(Este workflow no altera `EstadoEstudio`; gestiona el poblamiento de la relación simétrica `EstudioFamiliarVinculado`)*

| Evento Trigger | Acción sobre `estudios_familiares_vinculados` | Efecto secundario |
|---|---|---|
| Alta de paciente `P` con familiograma con `dni` que coincide con paciente existente `Q` | Si `P` o `Q` ya tienen estudios, vincula ambos conjuntos bidireccionalmente | Completa `familiar.paciente_vinculado_id = Q.id` + `registro_modificaciones` |
| Alta de paciente `Q` cuyo `dni` coincide con `Familiar` existente en familiograma de `P` | Completa `familiar.paciente_vinculado_id = Q.id`; listo para cuando `Q` cree un estudio | Notificación diferida cuando exista estudio |
| Alta de estudio `E` para paciente `P` | Vincula `E` con todos los estudios de cualquier paciente vinculado vía `familiares` (ambas direcciones) | `Aviso` a médicos tratantes + `registro_modificaciones` (`estudio`) |

---

## Handoff Contracts

| Origen | Destino | Payload / Garantía |
|---|---|---|
| Escenario 18 / 19 (Alta de paciente) | Escenario 41 (Rama A) | Invoca `EstudioService.sincronizar_vinculos_familiares_por_paciente(paciente.id)` dentro de la misma transacción. |
| Escenario 01 (Crear estudio) | Escenario 41 (Rama A) | Invoca `EstudioService.vincular_estudios_familiares(estudio.id)` tras persistir `estudio` y antes de hacer `COMMIT`. |
| Escenario 41 (Rama B) | Escenario 37 (`Descargar resultado`) | Habilita al `Médico` de `X` a consultar/descargar el resultado del estudio `X'` mediante la ruta autorizada por vínculo familiar. |
| Escenario 41 | Escenario 42 (`Registro de modificaciones`) | Todo vínculo creado se asienta como modificación sobre ambos `estudios`. |

---

## Cleanup Inventory

- `CHECK(estudio_origen_id <> estudio_relacionado_id)` impide auto-vínculos circulares de un estudio consigo mismo.
- `UNIQUE(estudio_origen_id, estudio_relacionado_id)` + inserción `ON CONFLICT DO NOTHING` garantiza idempotencia total frente a reintentos o cargas múltiples en familiogramas.

---

## Reality Checker Findings

- **Existente en código (`app/src/core/models/clinica.py`)**: El modelo `Familiar` actual solo posee `id`, `paciente_id`, `parentesco`, `nombre` y `diagnostico_previo`; **faltan** `apellido`, `dni` y `paciente_vinculado_id`.
- **Existente en código (`app/src/core/models/estudios.py`)**: No existe aún el modelo `EstudioFamiliarVinculado` (`estudios_familiares_vinculados`).
- **Existente en código (`app/src/core/services/estudio_service.py`)**: Si existe lógica parcial de creación de estudios, actualmente no ejecuta detección de familiares ni vínculos automáticos.

---

## Test Cases

1. **TC-01 (Familiar con DNI crea estudio después que el paciente índice)**: Paciente `P1` tiene en su familiograma a su hermano `F` con `dni = "30111222"` y posee estudio `E1`. Luego se da de alta `P2` con `dni = "30111222"` y se crea `E2`. Automáticamente `F.paciente_vinculado_id = P2.id`, existen `(E1, E2)` y `(E2, E1)` en `estudios_familiares_vinculados` y ambos quedan en `registro_modificaciones`.
2. **TC-02 (Paciente índice ya tenía familiar registrado sin estudio previo)**: `P2` ya existía en el sistema y su familiar `F` en el familiograma de `P1` es actualizado agregándole el `dni` de `P2`; al confirmar actualización del familiar, se vinculan automáticamente sus estudios existentes.
3. **TC-03 (Navegación del médico desde estudio X hacia estudio X')**: El médico tratante de `E1` llama a `GET /api/v1/estudios/{E1}/familiares-vinculados` y ve `E2`; luego consulta `GET /api/v1/estudios/{E1}/familiares-vinculados/{E2}` y recibe detalle de `E2`, variantes y resultado sin ver datos de pago de `P2`.
4. **TC-04 (Aislamiento de acceso sin vínculo)**: Un médico que atiende un estudio `E3` no vinculado con `E2` recibe `404`/`403` al intentar acceder vía `/estudios/{E3}/familiares-vinculados/{E2}`.
5. **TC-05 (No duplicación en múltiples estudios)**: Si `P1` crea un segundo estudio `E1_b`, se vinculan `(E1_b, E2)` y `(E2, E1_b)` sin duplicar ni fallar sobre `(E1, E2)`.

---

## Assumptions

- El identificador determinístico para vinculación automática cuando ambos pacientes fueron cargados en momentos distintos es el **DNI** exacto normalizado (sin puntos ni espacios) del familiar en el familiograma y del paciente registrado.
- Por defecto, el médico tratante del estudio `X` puede consultar la ficha genética/resultado de `X'` mediante el vínculo familiar sin exponer cuotas, pagos ni texto libre de historia clínica ajena a ese estudio (salvo que además esté autorizado por el Escenario 40).

---

## Open Questions

- ¿Al cargar el familiograma (Escenario 18), el campo `dni` del familiar debe pasar a ser obligatorio o permanecer opcional (permitiendo solo vinculación automática cuando el médico ingresa el DNI)? *(Recomendado: opcional al cargar el familiar, habilitando la vinculación automática cuando esté presente o cuando el médico seleccione un paciente existente).*
- ¿El `Paciente` también debe ver algún resumen de estudios vinculados o esta navegación aplica exclusivamente al `Médico` tratante (según Requerimiento 4)? *(Spec acotada al `Médico` como solicita el requerimiento).*

---

## Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-11-17 | Especificación creada para el Requerimiento 4 y ADR-002 (vinculación automática por familiograma y navegación entre estudios X <-> X'). | Aprobada para implementación posterior sobre modelos `Familiar` y `EstudioFamiliarVinculado`. |
