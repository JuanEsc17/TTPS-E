# ADR-004: Remuestreo por Baja Calidad en Corea (Sin Regla < 2 ml) y Seguimiento Anual VUS

## Status
Accepted (2026-11-17)

## Context
Dos cambios impactan el ciclo clínico-logístico y de resultados del `Estudio`:
1. **Remuestreo y calidad de muestra (Requerimiento 5):** Se elimina la posibilidad y regla de descarte de muestra menor a `2 ml` (`ML_MINIMOS_TUBO`, `VOLUMEN_INSUFICIENTE`). En su lugar, cuando una muestra llega a Corea (`EstadoEstudio.EN_VIAJE_COREA`) con baja calidad, el **administrativo** debe indicar que se necesita un remuestreo y retroceder el estudio.
2. **Seguimiento de diagnóstico VUS (Requerimiento 7):** Cuando el diagnóstico del estudio resulta **VUS** (variante de significado incierto), debe guardarse la fecha para realizar un nuevo estudio dentro de un año (`fecha_resultado + 1 año`), alineado además con la regla de negocio documentada en `.ai/APIs/API_APIGen.md`.

## Decision
1. **Máquina de estados y remuestreo sin `< 2 ml`:**
   - Se mantienen exactamente los **14 estados** del LEL (`EstadoEstudio`), utilizando `EstadoEstudio.REMUESTREO_REQUERIDO` como destino del retroceso desde `EN_VIAJE_COREA` (y opcionalmente desde `EN_LAB_CENTRAL`/`EN_ESPERA_RETIRO` ante desnaturalización o baja calidad, nunca por volumen `< 2 ml`).
   - En `MotivoDescarte`, se elimina `VOLUMEN_INSUFICIENTE` y se incorpora `BAJA_CALIDAD` (manteniendo `ADN_INSUFICIENTE` y `DESNATURALIZADA` como causas válidas de calidad).
   - Al marcar remuestreo desde `EN_VIAJE_COREA`, la `Muestra` vigente se marca con `motivo_descarte` y `observaciones_calidad`, pero **no se altera la composición histórica del `SampleSet` ya enviado a Corea** (ya que el paquete físico ya viajó y los resultados/fallas de Corea son individuales por estudio); únicamente ese `Estudio` retrocede a `Remuestreo requerido` y genera el registro en `registro_modificaciones` y notificaciones al `Paciente` y `Médico`.

2. **Persistencia de fecha anual por VUS:**
   - Se incorpora `ConclusionDiagnostica` (`positivo`, `negativo`, `vus`) y `fecha_proximo_estudio` (`Date`, nullable) en `resultados`, además de `fecha_reevaluacion_vus` (`Date`, nullable, indexado) en `estudios`.
   - **Criterio de clasificación del diagnóstico:**
     - `positivo`: existe al menos una variante `PATOGENICA` (`Resultado.positivo = True`).
     - `vus`: no existen variantes `PATOGENICA` y existe al menos una variante `VUS` (`Resultado.positivo = False`, `fecha_proximo_estudio = fecha_generacion + 1 año`).
     - `negativo`: no existen variantes `PATOGENICA` ni `VUS` (`Resultado.positivo = False`).
   - Se sincroniza `estudios.fecha_reevaluacion_vus = resultados.fecha_proximo_estudio` y se registra el cambio en `registro_modificaciones`, habilitando un job/bandeja de recordatorio anual (Escenario 43).

## Consequences
- **Positivas:** Preserva intacta la máquina de 14 estados del LEL y el historial de `SampleSet` ya despachados; provee una fecha indexada y consultable tanto en `resultados` como en `estudios` para alertas de seguimiento anual.
- **Negativas / Trade-offs:** Requiere actualizar `enums.py`, `reglas.py`, `logistica.py`, `estudios.py` y `analisis.py` en código en la próxima iteración SDD para retirar `ML_MINIMOS_TUBO` y `VOLUMEN_INSUFICIENTE` existentes.
