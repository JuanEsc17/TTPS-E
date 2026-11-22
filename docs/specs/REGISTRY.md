# Workflow Specification Registry (SDD Index)

**Actualizado**: 2026-11-17
**Arquitectura de referencia**: [DER.md](../DER.md) (**43 tablas / 10 módulos**) y ADRs [ADR-001](../ADRs/ADR-001-pagos-en-cuotas-mercadopago.md), [ADR-002](../ADRs/ADR-002-multiples-medicos-y-vinculo-estudios-familiares.md), [ADR-003](../ADRs/ADR-003-registro-de-modificaciones-auditoria.md), [ADR-004](../ADRs/ADR-004-remuestreo-calidad-corea-y-seguimiento-vus.md)
**Cobertura**: Escenarios **01 al 43** de `.ai/3-Escenarios.md`

---

## View 1: By Workflow (Escenarios 01–43)

| # | Escenario | Versión | Estado | Archivo Spec |
|---|---|---|---|---|
| 01 | Dar de alta un paciente | 1.1 | Approved | [escenario-01-dar-de-alta-un-paciente.md](./escenario-01-dar-de-alta-un-paciente.md) |
| 02 | Dar de alta un estudio | 1.1 | Approved | [escenario-02-dar-de-alta-un-estudio.md](./escenario-02-dar-de-alta-un-estudio.md) |
| 03 | Emitir un presupuesto | 1.1 | Approved | [escenario-03-emitir-un-presupuesto.md](./escenario-03-emitir-un-presupuesto.md) |
| 04 | Autorizar un estudio por obra social | 1.1 | Approved | [escenario-04-autorizar-un-estudio-por-obra-social.md](./escenario-04-autorizar-un-estudio-por-obra-social.md) |
| 05 | Reautorizar un estudio rechazado | 1.1 | Approved | [escenario-05-reautorizar-un-estudio-rechazado.md](./escenario-05-reautorizar-un-estudio-rechazado.md) |
| 06 | Pagar un estudio particular *(MercadoPago + Cuotas)* | 2.0 | Approved | [escenario-06-pagar-un-estudio-particular.md](./escenario-06-pagar-un-estudio-particular.md) |
| 07 | Solicitar un turno de extracción | 1.1 | Approved | [escenario-07-solicitar-un-turno-de-extraccion.md](./escenario-07-solicitar-un-turno-de-extraccion.md) |
| 08 | Cancelar un turno de extracción | 1.1 | Approved | [escenario-08-cancelar-un-turno-de-extraccion.md](./escenario-08-cancelar-un-turno-de-extraccion.md) |
| 09 | Registrar la toma de una muestra | 1.1 | Approved | [escenario-09-registrar-la-toma-de-una-muestra.md](./escenario-09-registrar-la-toma-de-una-muestra.md) |
| 10 | Remuestrear un estudio *(Baja calidad en Corea; sin regla < 2 ml)* | 2.0 | Approved | [escenario-10-remuestrear-un-estudio.md](./escenario-10-remuestrear-un-estudio.md) |
| 11 | Transportar muestras al laboratorio central | 1.1 | Approved | [escenario-11-transportar-muestras-al-laboratorio-central.md](./escenario-11-transportar-muestras-al-laboratorio-central.md) |
| 12 | Formar un sample-set de muestras | 2.0 | Approved | [escenario-12-formar-un-sample-set-de-muestras.md](./escenario-12-formar-un-sample-set-de-muestras.md) |
| 13 | Enviar un sample-set de muestras a Corea | 1.1 | Approved | [escenario-13-enviar-un-sample-set-de-muestras-a-corea.md](./escenario-13-enviar-un-sample-set-de-muestras-a-corea.md) |
| 14 | Enviar una muestra de Pompe urgente | 1.1 | Approved | [escenario-14-enviar-una-muestra-de-pompe-urgente.md](./escenario-14-enviar-una-muestra-de-pompe-urgente.md) |
| 15 | Analizar un estudio mediante bioinformática | 1.1 | Approved | [escenario-15-analizar-un-estudio-mediante-bioinformatica.md](./escenario-15-analizar-un-estudio-mediante-bioinformatica.md) |
| 16 | Informar el resultado de un estudio *(+ fecha VUS 1 año)* | 1.1 | Approved | [escenario-16-informar-el-resultado-de-un-estudio.md](./escenario-16-informar-el-resultado-de-un-estudio.md) |
| 17 | Reanalizar un estudio | 1.1 | Approved | [escenario-17-reanalizar-un-estudio.md](./escenario-17-reanalizar-un-estudio.md) |
| 18 | Gestionar la información familiar | 1.1 | Approved | [escenario-18-gestionar-la-informacion-familiar.md](./escenario-18-gestionar-la-informacion-familiar.md) |
| 19 | Registrar un paciente sin información familiar | 1.1 | Approved | [escenario-19-registrar-un-paciente-sin-informacion-familiar.md](./escenario-19-registrar-un-paciente-sin-informacion-familiar.md) |
| 20 | Cambiar la contraseña inicial | 1.0 | Approved | [escenario-20-cambiar-la-contrasena-inicial.md](./escenario-20-cambiar-la-contrasena-inicial.md) |
| 21 | Registrar un médico | 1.0 | Approved | [escenario-21-registrar-un-medico.md](./escenario-21-registrar-un-medico.md) |
| 22 | Registrar un administrativo | 2.0 | Approved | [escenario-22-registrar-un-administrativo.md](./escenario-22-registrar-un-administrativo.md) |
| 23 | Gestionar una patología | 1.0 | Approved | [escenario-23-gestionar-una-patologia.md](./escenario-23-gestionar-una-patologia.md) |
| 24 | Consultar variantes | 1.0 | Approved | [escenario-24-consultar-variantes.md](./escenario-24-consultar-variantes.md) |
| 25 | Consultar el chatbot sobre patologías | 1.0 | Approved | [escenario-25-consultar-el-chatbot-sobre-patologias.md](./escenario-25-consultar-el-chatbot-sobre-patologias.md) |
| 26 | Verificar el ingreso desde una máquina nueva | 1.0 | Approved | [escenario-26-verificar-el-ingreso-desde-una-maquina-nueva.md](./escenario-26-verificar-el-ingreso-desde-una-maquina-nueva.md) |
| 27 | Iniciar sesión | 1.0 | Approved | [escenario-27-iniciar-sesion.md](./escenario-27-iniciar-sesion.md) |
| 28 | Cerrar sesión | 1.0 | Approved | [escenario-28-cerrar-sesion.md](./escenario-28-cerrar-sesion.md) |
| 29 | Crear un cupón | 1.0 | Approved | [escenario-29-crear-un-cupon.md](./escenario-29-crear-un-cupon.md) |
| 30 | Asignar y aplicar un cupón | 1.1 | Approved | [escenario-30-asignar-y-aplicar-un-cupon.md](./escenario-30-asignar-y-aplicar-un-cupon.md) |
| 31 | Registrar un gerente médico | 1.0 | Approved | [escenario-31-registrar-un-gerente-medico.md](./escenario-31-registrar-un-gerente-medico.md) |
| 32 | Seguir una muestra en el mapa | 1.0 | Approved | [escenario-32-seguir-una-muestra-en-el-mapa.md](./escenario-32-seguir-una-muestra-en-el-mapa.md) |
| 33 | Ausentarse a un turno de extracción *(incl. anulación de cuotas)* | 1.1 | Approved | [escenario-33-ausentarse-a-un-turno-de-extraccion.md](./escenario-33-ausentarse-a-un-turno-de-extraccion.md) |
| 34 | Cambiar la contraseña | 1.0 | Approved | [escenario-34-cambiar-la-contrasena.md](./escenario-34-cambiar-la-contrasena.md) |
| 35 | Grabar la historia clínica *(con multi-médico + auditoría)* | 1.1 | Approved | [escenario-35-grabar-la-historia-clinica.md](./escenario-35-grabar-la-historia-clinica.md) |
| 36 | Cargar los síntomas del paciente con SNOMED | 1.1 | Approved | [escenario-36-cargar-los-sintomas-del-paciente-con-snomed.md](./escenario-36-cargar-los-sintomas-del-paciente-con-snomed.md) |
| 37 | Descargar el resultado de un estudio | 1.1 | Approved | [escenario-37-descargar-el-resultado-de-un-estudio.md](./escenario-37-descargar-el-resultado-de-un-estudio.md) |
| 38 | Pagar una cuota de un estudio con MercadoPago *(Nuevo - Req. 1)* | 1.0 | Approved | [escenario-38-pagar-cuota-con-mercadopago.md](./escenario-38-pagar-cuota-con-mercadopago.md) |
| 39 | Consultar las cuotas de los pacientes *(Nuevo - Req. 3)* | 1.0 | Approved | [escenario-39-consultar-cuotas-de-pacientes.md](./escenario-39-consultar-cuotas-de-pacientes.md) |
| 40 | Autorizar médicos para ver la historia clínica *(Nuevo - Req. 2)* | 1.0 | Approved | [escenario-40-autorizar-medicos-a-ver-historia-clinica.md](./escenario-40-autorizar-medicos-a-ver-historia-clinica.md) |
| 41 | Vincular y consultar estudios de familiares del familiograma *(Nuevo - Req. 4)* | 1.0 | Approved | [escenario-41-vincular-y-consultar-estudios-de-familiares.md](./escenario-41-vincular-y-consultar-estudios-de-familiares.md) |
| 42 | Consultar el registro de modificaciones *(Nuevo - Req. 6)* | 1.0 | Approved | [escenario-42-consultar-registro-de-modificaciones.md](./escenario-42-consultar-registro-de-modificaciones.md) |
| 43 | Programar y notificar seguimiento anual por diagnóstico VUS *(Nuevo - Req. 7)* | 1.0 | Approved | [escenario-43-programar-seguimiento-anual-por-vus.md](./escenario-43-programar-seguimiento-anual-por-vus.md) |

---

## View 2: By Component (Arquitectura en Capas y Tablas de [DER.md](../DER.md))

| Módulo / Tabla o Componente | Tipo | Specs que lo utilizan | Notas SDD / Requerimientos |
|---|---|---|---|
| **1. Usuarios y Seguridad** (`usuarios`, `dispositivos_conocidos`, `codigos_verificacion`, `avisos`) | Tablas | `01`, `03`–`28`, `30`–`43` | Autenticación JWT/2FA y bandeja unificada de notificaciones (`APP` / `MAIL` / `TELEGRAM`). |
| **2. Perfiles y Autorizaciones** (`medicos`, `especialidades`, `medicos_especialidades`, `transportistas`, `pacientes`, `pacientes_medicos_autorizados`) | Tablas | `01`, `11`, `18`, `19`, `21`, `22`, `31`, `35`, `36`, `40` | `pacientes_medicos_autorizados` con `uq_paciente_medico_activo WHERE activa` (Req. 2 / ADR-002). |
| **3. Clínica** (`patologias`, `sintomas`, `patologias_sintomas`, `pacientes_sintomas`, `familiares`, `familiares_sintomas`, `genes`, `patologias_genes`, `variantes`) | Tablas | `01`, `02`, `15`–`19`, `23`–`25`, `36`, `41` | `familiares` incorpora `apellido`, `dni` e ID `paciente_vinculado_id` para matching determinístico (Req. 4). |
| **4. Estudios y Vínculos Familiares** (`estudios`, `estudios_genes`, `estudios_familiares_vinculados`) | Tablas | `02`–`17`, `32`, `33`, `37`–`43` | `estudios.fecha_reevaluacion_vus` (Req. 7) y vínculos simétricos X <-> X' en `estudios_familiares_vinculados` (Req. 4). |
| **5. Economía, MercadoPago y Cuotas** (`obras_sociales`, `cupones`, `presupuestos`, `pagos`, `cuotas`, `autorizaciones`, `demandas`) | Tablas | `03`–`08`, `29`, `30`, `33`, `38`, `39` | `pagos` soporta cuotas MP (`PARCIAL`/`PAGADO`); `cuotas` registra vencimientos y refs MP (Req. 1 y 3 / ADR-001). |
| **6. Turnos** (`centros_extraccion`, `turnos`) | Tablas | `07`–`11`, `33` | `uq_turno_activo(centro_id, inicio) WHERE activo` impide solapamientos preservando historial. |
| **7. Logística y Transporte** (`sample_sets`, `muestras`, `ordenes_del_dia`, `ordenes_del_dia_paradas`, `posiciones_transporte`) | Tablas | `09`–`14`, `32` | Eliminada regla `< 2 ml` (`VOLUMEN_INSUFICIENTE`); añadido `MotivoDescarte.BAJA_CALIDAD` y `observaciones_calidad` en `muestras` (Req. 5 / ADR-004). |
| **8. Análisis Bioinformático y Resultados** (`datos_crudos`, `analisis`, `analisis_genes`, `analisis_variantes`, `resultados`) | Tablas | `15`–`17`, `24`, `37`, `43` | `resultados` incorpora `diagnostico: ConclusionDiagnostica` (`positivo`, `negativo`, `vus`) y `fecha_proximo_estudio` (+1 año si `vus`). |
| **9. Configuración** (`configuracion`) | Tabla | `03`, `12`, `33` | Parámetros globales del laboratorio. |
| **10. Auditoría de Modificaciones** (`registro_modificaciones`) | Tabla append-only | `01`–`19`, `30`, `33`, `35`–`43` | Registra creación, modificación (`{campo: {anterior, nuevo}}`) y cambio de estado de `sample_set`, `paciente` y `estudio` (Req. 6 / ADR-003). |
| **MercadoPagoClient** (`clients/mercadopago_client.py`) | Cliente HTTP externo | `06`, `30`, `38` | `POST /checkout/preferences`, `GET /v1/payments/{id}`, validación HMAC `x-signature` (ver `.ai/APIs/API_MercadoPago.md`). |
| **AuditoriaService** (`core/services/auditoria_service.py`) | Servicio transversal | `01`–`19`, `30`, `33`, `35`–`43` | Escritura atómica en la misma transacción DB + API paginada de lectura por entidad y rol (Escenario 42). |
| **Otros Clientes Externos** (`FamiliogramaClient`, `ChatbotClient`, `ObraSocialClient`, `CuponesClient`, `SnomedClient`, `TranscriptorClient`, `OptimizacionRecorridosClient`, `MinisterioSaludClient`, `FedExClient`, `BioinformaticaClient`, `TelegramBot`, `MailClient`, `PdfGenerator`) | Clientes / Adapters | `03`–`05`, `09`, `11`, `13`, `14`, `16`, `18`, `24`, `25`, `30`, `35`, `36` | Contratos documentados en `.ai/APIs/API_*.md`. |

---

## View 3: By User Journey (Por Sujeto LEL)

| Actor (Sujeto LEL) | Jornada / Flujos End-to-End |
|---|---|
| **Médico** | Alta (`21`), login/2FA (`26`, `27`, `20`, `34`, `28`) → Consulta catálogo (`25`), da de alta `Paciente` con síntomas SNOMED (`01`, `36`), historia clínica grabada (`35`) y familiograma (`18`, `19`) → Solicita `Estudio` (`02`) → Revisa diagnóstico vinculado de familiares X <-> X' (`41`) y resultados (`16`, `37`) → Pide reanálisis (`17`) y monitorea agenda anual VUS (`43`) → Audita historial clínico autorizado (`40`, `42`). |
| **Paciente** | Recibe alta y cambia contraseña (`20`, `26`, `27`, `34`, `28`) → Paga en 1 pago o cuotas con MercadoPago (`06`, `38`) aplicando cupón (`30`), o gestiona demanda OS (`04`, `05`) → Otorga/revoca autorización de historia clínica a múltiples médicos (`40`) → Saca/cancela/reprograma turnos (`07`, `08`, `33`) → Sigue muestra (`32`) y remuestrea sin costo ante baja calidad en Corea (`10`) → Descarga resultado y recibe alerta anual VUS (`37`, `43`). |
| **Personal administrativo** | Alta por admin general (`22`) → Emite presupuesto (`03`), valida OS (`04`) y monitorea cuotas MercadoPago pendientes/vencidas (`39`) → Administra `SampleSet` y envíos a Corea (`12`, `13`, `14`) → Ejecuta rollback de remuestreo desde `EN_VIAJE_COREA` por baja calidad en Corea (`10`) → Carga datos crudos (`15`) → Consulta auditoría completa (`42`). |
| **Transportista** | Login (`27`) → Ejecuta orden diaria provincial de centros de extracción y traslada muestras al laboratorio central reportando ruta (`11`, `32`). |
| **Bioinformático** | Toma estudios priorizando `Pompe urgente` (`15`), consulta variantes (`24`), registra análisis o reanálisis (`16`, `17`) determinando diagnóstico `positivo | negativo | vus` (con fecha anual automática en `vus`). |
| **Gerente médico** | Alta (`31`) → Gestiona patologías/genes/síntomas (`23`), emite y asigna cupones (`29`, `30`) → Supervisa auditoría de modificaciones (`42`), seguimiento VUS (`43`) y estudios clínicos (`37`, `41`). |
| **Admin general** | Administra altas de personal (`21`, `22`, `31`) y audita transversalmente `registro_modificaciones` (`42`). |

---

## View 4: By State (`EstadoEstudio` — los 14 Estados LEL Invariantes)

| # | Estado (`EstadoEstudio`) | Entradas (Escenarios) | Salidas (Escenarios) | Regla clave actualizada |
|---|---|---|---|---|
| 1 | `Creado` (`"Creado"`) | `02`, `06` (pago habilitante desde `Creado`), `33` (5.ª ausencia anula pago y retorna aquí) | `03`/`04` (OS → `Pendiente de autorizacion`), `07` (si pago particular vigente en `PAGADO`/`PARCIAL` → `Turno sacado`) | Particular puede pagar en cuotas MP (`06`, `38`); cuota #1 abonada habilita `Sacar turno` (`07`). Cupones descuentan antes de dividir en cuotas (`30`). |
| 2 | `Pendiente de autorización` (`"Pendiente de autorizacion"`) | `03`/`04` (con obra social), `05` (demanda/reautorización) | `04`/`05` (`Autorizado` o `Rechazado`) | Emisión de presupuesto valida cobertura y envía orden a obra social (`03`, `04`). |
| 3 | `Autorizado` (`"Autorizado"`) | `04`, `05` | `07` (→ `Turno sacado`) | Habilita extracción sin pago particular. |
| 4 | `Rechazado` (`"Rechazado"`) | `04` | `05` (demanda/reautorización → `Autorizado` o pasaje a particular en `Creado` → `06`) | — |
| 5 | `Turno sacado` (`"Turno sacado"`) | `07` | `08` (cancelación → estado habilitado previo), `09` (toma → `Lista para retirar`), `33` (ausencias 1–4 mantienen estado; 5.ª anula `Pago`/`Cuotas` y vuelve a `Creado`) | Todas las transiciones quedan asentadas en `registro_modificaciones` (`42`). |
| 6 | `Lista para retirar` (`"Lista para retirar"`) | `09` | `11` (retiro transportista → `En camino al laboratorio central`) | Sin rechazo por volumen `< 2 ml`. |
| 7 | `En camino al laboratorio central` (`"En camino al laboratorio central"`) | `11` | `11` (arribo lab central → `En laboratorio central`) | Trazabilidad GPS en `posiciones_transporte` (`32`). |
| 8 | `En laboratorio central` (`"En laboratorio central"`) | `11` | `12`/`14` (cierre `SampleSet` → `En espera de retiro`), `10` (falla técnica no volumétrica) | `SampleSet` de 10 muestras o `Pompe urgente`; sin control `< 2 ml`. |
| 9 | `En espera de retiro` (`"En espera de retiro"`) | `12`, `14` | `13`/`14` (retiro FedEx → `En viaje a Corea`), `10` (contingencia técnica) | Bolsa sellada e inmutable hasta entrega a FedEx. |
| 10 | `En viaje a Corea` (`"En viaje a Corea"`) | `13`, `14` | `15` (datos crudos → `En análisis por bioinformática`), `10` (**baja calidad en Corea → `Remuestreo requerido`**) | El rollback de un estudio por `BAJA_CALIDAD` desde Corea preserva intacto el `SampleSet` enviado (`10`, ADR-004). |
| 11 | `En análisis por bioinformática` (`"En analisis por bioinformatica"`) | `15`, `17` | `15` (toma bioinformático → `En análisis de un bioinformático`) | Cola priorizada por `es_pompe_urgente DESC`. |
| 12 | `En análisis de un bioinformático` (`"En analisis de un bioinformatico"`) | `15`, `17` | `16` (carga variantes y resultado → `Resultado cargado`) | Evalúa `ConclusionDiagnostica` (`positivo`, `negativo`, `vus`). |
| 13 | `Resultado cargado` (`"Resultado cargado"`) | `16` | `17` (reanálisis → `En análisis por bioinformática`), `37` (descarga), `41` (vista familiar), `43` (seguimiento VUS a 1 año) | Si diagnóstico = `vus`, fija `fecha_reevaluacion_vus` (+1 año) y agenda recordatorios (`43`). |
| 14 | `Remuestreo requerido` (`"Remuestreo requerido"`) | `10` | `07` (nuevo turno sin costo → `Turno sacado`) | Disparado principalmente al llegar a Corea con baja calidad; preserva `Pago` / `Cuotas` vigentes. |

*(Los 14 valores anteriores coinciden 1 a 1 con `EstadoEstudio` en `app/src/core/models/enums.py#L15-L29` verificados por `tests/test_smoke.py`.)*

---

## Discovery Audit Summary (Código actual vs Specs v1.1/v2.0)

| Área | Estado en `app/` hoy | Brecha documentada hacia Specs actualizadas |
|---|---|---|
| `enums.py`, `reglas.py`, `logistica.py` | Implementados Escenarios 11–14 v1.0 y smoke tests (`test_escenario_11_logistica.py` con `ML_MINIMOS_TUBO = 2` y `VOLUMEN_INSUFICIENTE`). | Retirar `ML_MINIMOS_TUBO` y `VOLUMEN_INSUFICIENTE`, incorporar `MotivoDescarte.BAJA_CALIDAD` y `observaciones_calidad`, permitir rollback desde `EN_VIAJE_COREA` preservando `SampleSet` (ADR-004). |
| `economia.py` y `MercadoPagoClient` | Solo pago único sin cuotas ni cliente MercadoPago. | Extender `Pago` y agregar `Cuota` (`EstadoCuota`, `EstadoPago`, `MedioPago`), `MercadoPagoClient`, webhook HMAC e endpoints de cuotas y panel administrativo (`06`, `38`, `39`, ADR-001). |
| `perfiles.py`, `clinica.py`, `estudios.py` | `Paciente.medico_id` 1:N; `Familiar` sin `apellido`/`dni`/`paciente_vinculado_id`; sin `estudios_familiares_vinculados`. | Agregar `PacienteMedicoAutorizado`, campos en `Familiar`, `EstudioFamiliarVinculado` y matching automático por DNI (`40`, `41`, ADR-002). |
| `auditoria.py` y `AuditoriaService` | No existen en `app/src/`. | Crear modelo append-only `RegistroModificacion`, migración Alembic, `AuditoriaService` y endpoints de consulta (`42`, ADR-003). |
| `analisis.py` y seguimiento VUS | `Resultado` solo tiene `positivo: bool`; `Estudio` sin `fecha_reevaluacion_vus`. | Agregar `ConclusionDiagnostica` (`positivo`, `negativo`, `vus`), `fecha_proximo_estudio`, `fecha_reevaluacion_vus` (+1 año) y job/agenda de recordatorio (`16`, `43`, ADR-004). |
