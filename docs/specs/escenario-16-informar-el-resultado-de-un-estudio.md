# WORKFLOW: Escenario 16 – Informar el resultado de un estudio
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-16-Informar-el-resultado-de-un-estudio`

## Símbolos LEL utilizados

| Categoría | Símbolo LEL | Modelo / Tabla en `app/src/core/models/` |
|---|---|---|
| **Sujeto** | `Bioinformático` | `Usuario` (`Rol.BIOINFORMATICO`) en `usuarios` (`Analisis.bioinformatico_id`) |
| **Sujeto** | `Paciente` | `Paciente` en `pacientes` / `Usuario` (`Rol.PACIENTE`) |
| **Sujeto** | `Médico` | `Medico` en `medicos` / `Usuario` (`Rol.MEDICO`, `Rol.GERENTE_MEDICO`) |
| **Objeto** | `Estudio` | `Estudio` en `estudios` |
| **Objeto** | `Resultado` | `Resultado` en `resultados` (`positivo`, `pdf_path`, `generado_en`, `calcular_positivo`) |
| **Objeto** | `Variante` | `Variante` en `variantes` y `AnalisisVariante` en `analisis_variantes` |
| **Objeto** | `VUS` | `ClasificacionVariante.VUS` (`"vus"`) |
| **Objeto** | `Aviso` | `Aviso` en `avisos` (`CanalAviso.APP`, `CanalAviso.MAIL`) |
| **Verbo** | `Cargar resultado` | Servicio `cargar_resultado_estudio` |
| **Verbo** | `Descargar resultado` | Endpoint `GET /api/estudios/{estudio_id}/resultado/pdf` |
| **Estado** | `En análisis de un bioinformático` | `EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` (`"En analisis de un bioinformatico"`) |
| **Estado** | `Resultado cargado` | `EstadoEstudio.RESULTADO_CARGADO` (`"Resultado cargado"`) |

---

## Overview

- **Objetivo**: Registrar el `Resultado` de un `Analisis` bioinformático determinando su positividad o negatividad (`calcular_positivo`), generar el informe en formato PDF, cambiar el `Estudio` a estado `Resultado cargado`, notificar por correo electrónico y mediante `Aviso` tanto al `Paciente` como al `Médico` tratante, y habilitar la descarga del PDF del `Resultado`.
- **Contexto**: El `Bioinformático` finalizó el análisis de los `Datos crudos` y cargó las `Variante`s encontradas en los `Gen`es estudiados (Escenario 15 o Escenario 17). El diagnóstico es positivo si y solo si al menos una de las `Variante`s registradas en el análisis tiene `ClasificacionVariante.PATOGENICA`.
- **Recursos**: `Resultado` del exoma (`resultados`), `Variante` genética (`variantes`, `analisis_variantes`), archivo PDF del resultado (`pdf_path`), notificaciones (`avisos` y correo electrónico).
- **Episodios**:
  1. El sistema calcula la positividad/negatividad y registra el `Resultado` del `Estudio` en la tabla `resultados`.
  2. El sistema genera el `Resultado` en formato PDF con la positividad/negatividad y el detalle de las `Variante`s encontradas.
  3. El sistema notifica al `Paciente` (por correo electrónico y `Aviso` en el sistema).
  4. El sistema notifica al `Médico` tratante (por correo electrónico y `Aviso` en el sistema).
  5. El `Paciente` (y el `Médico` tratante) pueden consultar y descargar el PDF del `Resultado`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| `Bioinformático` | Confirma la carga de las `Variante`s del `Analisis`, disparando la generación y publicación del `Resultado`. |
| `Paciente` | Recibe el correo y el `Aviso` en plataforma, consulta el detalle del `Resultado` y descarga el archivo PDF. |
| `Médico` | Recibe el correo y el `Aviso` en plataforma, y accede al `Resultado` y su PDF de su paciente derivado. |
| Capa `router` (`Flask Blueprint`) | Expone la finalización del análisis (`POST /api/bioinformatica/estudios/{estudio_id}/analisis`) y la consulta/descarga del resultado (`GET /api/estudios/{estudio_id}/resultado`, `GET /api/estudios/{estudio_id}/resultado/pdf`). |
| Capa `service` (`ResultadoService` / `BioinformaticaService`) | Evalúa `calcular_positivo(variantes)`, compila el PDF del `Resultado`, actualiza `Estudio.estado = EstadoEstudio.RESULTADO_CARGADO` y emite las notificaciones a `Paciente` y `Médico`. |
| Capa `repo` (`ResultadoRepo`, `AnalisisRepo`, `EstudioRepo`, `AvisoRepo`) | Persiste `Resultado`, `Estudio` y `Aviso` en `PostgreSQL`. |
| Capa `clients` (`PdfGenerator`, `MailClient`) | Genera el documento PDF del `Resultado` y envía los correos electrónicos a `Paciente` y `Médico`. |

---

## Prerequisites

- Existe un `Estudio` en `estudios` con `estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO`.
- Existe un `Analisis` activo en `analisis` para ese `Estudio` (`bioinformatico_id IS NOT NULL` y `resultado IS NULL`), con sus `AnalisisGen` en `analisis_genes` y sus `AnalisisVariante` recién seleccionadas en `analisis_variantes`.
- El `Paciente` (`estudio.paciente.usuario`) y el `Médico` (`estudio.medico.usuario` o `analisis.solicitado_por.usuario`) existen y tienen dirección de correo electrónico registrada en `usuarios.email`.

---

## Trigger

1. **Generación y notificación del resultado (Episodios 1–4)**: Se dispara al completar la carga de variantes del `Bioinformático` en `POST /api/bioinformatica/estudios/{estudio_id}/analisis` (STEP 4 del Escenario 15 o STEP 4 del Escenario 17).
2. **Descarga del resultado (Episodio 5)**: El `Paciente` o el `Médico` tratante invoca `GET /api/estudios/{estudio_id}/resultado/pdf`.

---

## Workflow Tree

### STEP 1: Cálculo de positividad y compilación del PDF del Resultado
**Actor**: `service` (`ResultadoService.generar_resultado`) -> `clients` (`PdfGenerator`)
**Action**:
1. Obtiene la lista de objetos `Variante` asociados al `Analisis` (`[av.variante for av in analisis.variantes]`).
2. Evalúa la función de dominio `calcular_positivo(variantes)` (`app/src/core/models/analisis.py#L81-L82`):
   - `positivo = True` si `any(v.clasificacion == ClasificacionVariante.PATOGENICA for v in variantes)`.
   - `positivo = False` si no hay variantes o todas las variantes encontradas son `BENIGNA`, `INOCUA` o `VUS`.
3. Compila el documento PDF del `Resultado` incluyendo:
   - Datos del `Paciente` (`nombre`, `apellido`, `dni`, `fecha_nacimiento`), del `Médico` derivante (`nombre`, `apellido`, `matricula`) y `Patología` sospechada.
   - Tipo de análisis (`inicial` o `reanalisis`) y lista de `Gen`es analizados (`simbolo`, `nombre`).
   - Conclusión diagnóstica destacada: **POSITIVO** o **NEGATIVO**.
   - Tabla de `Variante`s encontradas (`gen.simbolo`, `notacion`, `clinvar_id`, `clasificacion`: `patogenica`, `benigna`, `inocua`, `vus`).
4. Guarda el PDF en `storage/resultados/resultado_analisis_{analisis.id}.pdf`.
**Timeout**: 8s
**Input**: `{ estudio, analisis, variantes }`
**Output on SUCCESS**: `{ positivo: true, pdf_path: "storage/resultados/resultado_analisis_25.pdf" }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(pdf_generation_error)`: Error de renderizado o de escritura en disco -> eliminar archivo PDF parcial (`ABORT_CLEANUP`) y abortar la transacción retornando HTTP `500 Internal Server Error` (`code: "ERROR_GENERACION_PDF_RESULTADO"`, `retryable: true`).

**Observable states during this step**:
  - Customer/Actor (`Bioinformático`) sees: `"Generando informe PDF del resultado..."`.
  - Operator sees: `Estudio` aún en `En análisis de un bioinformático`.
  - Database: Sin commit aún en `resultados`.
  - Logs: `[resultado_service] pdf_generado estudio_id=42 analisis_id=25 positivo=True path="storage/resultados/resultado_analisis_25.pdf"`

---

### STEP 2: Registro transaccional del Resultado y paso a `Resultado cargado`
**Actor**: `service` -> `repo` (`ResultadoRepo`, `EstudioRepo`, `AvisoRepo`) -> `PostgreSQL`
**Action**: En una única transacción atómica:
1. Inserta el registro `Resultado` en la tabla `resultados`: `analisis_id = analisis.id`, `positivo = positivo`, `pdf_path = pdf_path`, `generado_en = now()`.
2. Actualiza `estudio.estado = EstadoEstudio.RESULTADO_CARGADO` en la tabla `estudios`.
3. Inserta los registros de `Aviso` en la tabla `avisos` (`leido = False`, `CanalAviso.APP` y `CanalAviso.MAIL`):
   - Para el `Paciente` (`usuario_id = estudio.paciente.usuario_id`).
   - Para el `Médico` tratante (`usuario_id = estudio.medico.usuario_id`).
**Timeout**: 5s
**Input**: `{ analisis_id: 25, estudio_id: 42, positivo: true, pdf_path: "storage/resultados/resultado_analisis_25.pdf" }`
**Output on SUCCESS**: `{ resultado_id: 18, estado_estudio: "Resultado cargado", avisos_ids: [501, 502] }` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(conflict)`: Ya existe un `Resultado` para ese `analisis_id` (`UniqueConstraint` en `resultados.analisis_id`) -> `ABORT_CLEANUP` y retornar HTTP `409 Conflict` (`code: "RESULTADO_YA_EXISTE_PARA_ANALISIS"`).
  - `FAILURE(database_error)`: Error al persistir en `PostgreSQL` -> `ABORT_CLEANUP` (rollback + borrar PDF creado en STEP 1).

**Observable states during this step**:
  - Customer/Actor (`Paciente` y `Médico`) sees: `Estudio` en estado `Resultado cargado` y nuevo `Aviso` en su bandeja de notificaciones de la aplicación.
  - Operator (`Bioinformático` / `Administrativo`) sees: `Estudio #42` completado en `Resultado cargado`.
  - Database:
    - Tabla `resultados`: 1 fila `(id=18, analisis_id=25, positivo=True, pdf_path='storage/resultados/resultado_analisis_25.pdf')`.
    - Tabla `estudios`: `estado = 'Resultado cargado'`.
    - Tabla `avisos`: 2 filas para `Paciente` y `Médico`.
  - Logs: `[resultado_service] resultado_persistido estudio_id=42 resultado_id=18 estado="Resultado cargado"`

---

### STEP 3: Envío de notificaciones por correo electrónico al Paciente y al Médico tratante
**Actor**: `service` -> `clients` (`MailClient`) -> `repo` (`AvisoRepo`)
**Action**:
1. Envía correo electrónico al `Paciente` (`estudio.paciente.usuario.email`) avisando que el `Resultado` de su estudio de exoma clínico ya está disponible para consultar y descargar en la plataforma.
2. Envía correo electrónico al `Médico` tratante (`estudio.medico.usuario.email`) avisando que se cargó el `Resultado` del estudio de su paciente.
3. Actualiza `aviso.enviado = True` y `aviso.enviado_en = now()` en la tabla `avisos`.
**Timeout**: 10s
**Input**: `{ estudio_id: 42, resultado_id: 18, paciente_email, medico_email, avisos_ids: [501, 502] }`
**Output on SUCCESS**: `{ mails_enviados: true }` -> Retorna HTTP `200 OK` al `Bioinformático`; el `Resultado` queda disponible para STEP 4.
**Output on FAILURE**:
  - `FAILURE(smtp_error)`: Si el servidor SMTP da timeout o error 5xx tras 3 reintentos con backoff exponencial (1s, 2s, 4s), **no se revierte** el `Resultado` ni el estado `Resultado cargado` (el PDF ya está generado y accesible desde la web mediante el `Aviso` en `CanalAviso.APP`); se deja `aviso.enviado = False` para reintento en background y se registra warning en logs.

**Observable states during this step**:
  - Customer/Actor (`Paciente` y `Médico`) sees: Correo electrónico recibido en sus respectivas casillas con enlace al estudio.
  - Operator sees: Notificaciones marcadas como enviadas (`enviado = True`).
  - Database: Tabla `avisos` con `enviado = True`, `enviado_en = <timestamp>`.
  - Logs: `[mail_client] resultado_notificado estudio_id=42 paciente_email="..." medico_email="..."`

---

### STEP 4: Consulta y descarga del PDF del Resultado por el Paciente o el Médico
**Actor**: `Paciente` o `Médico` -> `router` (`GET /api/estudios/{estudio_id}/resultado` y `GET /api/estudios/{estudio_id}/resultado/pdf`) -> `service` -> `repo`
**Action**:
1. Verifica que el usuario autenticado esté autorizado a ver el resultado de ese `Estudio`:
   - Si tiene `Rol.PACIENTE`, debe cumplirse `estudio.paciente.usuario_id == usuario.id`.
   - Si tiene `Rol.MEDICO` o `Rol.GERENTE_MEDICO`, debe cumplirse `estudio.medico.usuario_id == usuario.id` (o haber solicitado un reanálisis en `estudio.analisis`).
   - Si tiene `Rol.BIOINFORMATICO`, puede consultarlo por auditoría técnica.
   - Otros roles o terceros reciben HTTP `403 Forbidden` (protección estricta de datos genéticos sensibles).
2. Verifica que `estudio.estado == EstadoEstudio.RESULTADO_CARGADO` y obtiene el último `Resultado` (o el historial completo de `Analisis` y sus respectivos `Resultado`s si hubo reanálisis).
3. Devuelve el detalle JSON (positividad, variantes y clasificaciones) o transmite el archivo binario PDF (`Content-Type: application/pdf`, `Content-Disposition: attachment; filename="resultado_estudio_{estudio_id}.pdf"`).
**Timeout**: 5s
**Input**: `{ estudio_id: 42, usuario_actual }`
**Output on SUCCESS**: Stream binario `application/pdf` o JSON del resultado -> FIN DEL WORKFLOW.
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Un `Paciente` o `Médico` intenta acceder al resultado de otro paciente ajeno -> retornar HTTP `403 Forbidden` y auditar intento de acceso no autorizado en logs de seguridad.
  - `FAILURE(invalid_state)`: El `Estudio` aún no tiene `Resultado` cargado -> retornar HTTP `409 Conflict` (`code: "RESULTADO_AUN_NO_DISPONIBLE"`).
  - `FAILURE(file_missing)`: El archivo en `resultado.pdf_path` no se encuentra en disco -> regenerar el PDF al vuelo desde los datos inmutables de `analisis` + `analisis_variantes` + `resultados` y entregarlo al usuario.

**Observable states during this step**:
  - Customer/Actor (`Paciente` / `Médico`) sees: Visualización en pantalla de si el resultado fue positivo o negativo junto con las variantes, y descarga del archivo PDF.
  - Operator sees: Registro de auditoría de descarga en logs.
  - Database: Lectura de `estudios`, `analisis`, `analisis_variantes`, `variantes`, `resultados`.
  - Logs: `[resultado_service] resultado_descargado estudio_id=42 resultado_id=18 usuario_id=15 rol="paciente"`

---

### ABORT_CLEANUP: Limpieza de PDF huérfano y reversión transaccional
**Triggered by**: Fallo en STEP 1 o STEP 2 antes del commit en `PostgreSQL`.
**Actions** (in order):
  1. Ejecutar `session.rollback()` en SQLAlchemy.
  2. Si se escribió `storage/resultados/resultado_analisis_{id}.pdf` en STEP 1 pero falló STEP 2, eliminar el archivo PDF del disco con `os.remove()`.
  3. Mantener `estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICO`.
**What customer sees**: El `Paciente` y el `Médico` no reciben notificaciones falsas de un resultado fallido.
**What operator sees**: El `Bioinformático` recibe mensaje de error y puede reenviar la confirmación del análisis.

---

## State Transitions

```
Estudio (EstadoEstudio):
[En analisis de un bioinformatico]
  -- (STEP 1-2: cálculo de positividad, generación de PDF y commit de Resultado) --> [Resultado cargado]

Resultado (resultados):
(inexistente)
  -- (STEP 2: al menos 1 variante PATOGENICA) -----> [positivo = True, pdf_path = "..."]
  -- (STEP 2: 0 variantes PATOGENICA) -------------> [positivo = False, pdf_path = "..."]
```

---

## Handoff Contracts

### 1. `Paciente / Médico (UI)` -> `Backend (router -> service)` (Consultar detalle del Resultado)
**Endpoint**: `GET /api/estudios/{estudio_id}/resultado`
**Payload**: Ninguno.
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "estudio_id": 42,
  "estado_estudio": "Resultado cargado",
  "resultado_actual": {
    "resultado_id": 18,
    "analisis_id": 25,
    "tipo_analisis": "inicial",
    "positivo": true,
    "generado_en": "2026-10-28T17:05:00",
    "pdf_url": "/api/estudios/42/resultado/pdf",
    "variantes": [
      {
        "variante_id": 101,
        "gen_simbolo": "GAA",
        "notacion": "c.1935C>A",
        "clinvar_id": "VCV000004025",
        "clasificacion": "patogenica"
      },
      {
        "variante_id": 104,
        "gen_simbolo": "GAA",
        "notacion": "c.1194+5G>A",
        "clinvar_id": "VCV000551203",
        "clasificacion": "vus"
      }
    ]
  }
}
```
**Failure response** (`403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "No tiene permisos para acceder al resultado genético de este estudio.",
  "code": "FORBIDDEN_RESULTADO_GENETICO",
  "retryable": false
}
```
**Timeout**: 3s
**ON FAILURE**: Retornar código de error HTTP y registrar evento de seguridad si es `403`.

---

### 2. `Paciente / Médico (UI)` -> `Backend (router -> service)` (Descargar PDF del Resultado)
**Endpoint**: `GET /api/estudios/{estudio_id}/resultado/pdf`
**Payload**: Ninguno.
**Success response** (`200 OK`):
- Headers: `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="resultado_estudio_42.pdf"`
- Body: Bytes del documento PDF.
**Failure response** (`403` / `404` / `409`): JSON con `{ "ok": false, "error": "...", "code": "...", "retryable": false }`.
**Timeout**: 5s
**ON FAILURE**: Si el PDF en disco no existe pero el registro en `resultados` sí existe, regenerar el PDF automáticamente antes de responder.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Archivo `storage/resultados/resultado_analisis_{id}.pdf` | Step 1 | `ABORT_CLEANUP` | `os.remove()` |
| Fila en tabla `resultados`, actualización de `estudios.estado` y filas en `avisos` | Step 2 | `ABORT_CLEANUP` | `session.rollback()` en SQLAlchemy |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/analisis.py` (líneas 68-82), el modelo `Resultado` y la función `calcular_positivo(variantes: list[Variante]) -> bool` ya están implementados y determinan que el estudio es positivo si alguna variante tiene `ClasificacionVariante.PATOGENICA`. | Low | STEP 1 | Se utiliza directamente `calcular_positivo(variantes)` del modelo de dominio. |
| RC-2 | En `.ai/1-Entrevista.md` (línea 315), se enfatiza que la confidencialidad de los datos genéticos y variantes del paciente es crítica (`"si se filtran los datos genéticos de un paciente de una variante, le podría afectar al paciente. Nos podría hacer un juicio"`). | High | STEP 4 / Test Cases | Se incluyó control estricto de autorización por titularidad (`estudio.paciente.usuario_id` o `estudio.medico.usuario_id`) en la consulta y descarga del `Resultado`. |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Resultado **positivo** cuando existe al menos una variante `patogenica` | El `Bioinformático` registra 1 variante `PATOGENICA` y 1 `VUS` | `calcular_positivo` devuelve `True`; se crea `Resultado(positivo=True)`, se genera el PDF, `estudio.estado == EstadoEstudio.RESULTADO_CARGADO` y se crean avisos para `Paciente` y `Médico`. |
| `TC-02`: Resultado **negativo** cuando solo hay variantes `benigna`, `inocua` o `vus` (o ninguna) | El `Bioinformático` registra 1 variante `BENIGNA` y 1 `VUS` (sin variantes patogénicas) | `calcular_positivo` devuelve `False`; se crea `Resultado(positivo=False)` y `estudio.estado == EstadoEstudio.RESULTADO_CARGADO`. |
| `TC-03`: Notificación dual al `Paciente` y al `Médico` tratante | Finaliza la carga del `Resultado` | Se crean registros en `avisos` tanto para `estudio.paciente.usuario_id` como para `estudio.medico.usuario_id` y se despachan ambos correos electrónicos. |
| `TC-04`: Descarga exitosa del PDF por el `Paciente` titular | `GET /api/estudios/42/resultado/pdf` autenticado como el `Paciente` dueño del estudio | HTTP `200 OK` con `Content-Type: application/pdf` y bytes válidos (`%PDF-`). |
| `TC-05`: Descarga exitosa del PDF por el `Médico` tratante | `GET /api/estudios/42/resultado/pdf` autenticado como el `Médico` derivante del estudio | HTTP `200 OK` con `Content-Type: application/pdf`. |
| `TC-06`: Bloqueo de seguridad ante acceso de otro `Paciente` o `Médico` no vinculado | `GET /api/estudios/42/resultado` o `/pdf` invocado por otro paciente distinto al titular | HTTP `403 Forbidden` (`FORBIDDEN_RESULTADO_GENETICO`). |
| `TC-07`: Fallo en generación de PDF revierte el cambio de estado | Error simulado de I/O al escribir el PDF en STEP 1 | No se crea fila en `resultados` y `estudio.estado` permanece en `EstadoEstudio.EN_ANALISIS_BIOINFORMATICO`. |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El resultado de un análisis con variantes únicamente de tipo `VUS`, `BENIGNA` o `INOCUA` se informa como `positivo = False`, listando igualmente las variantes halladas en el PDF. | `.ai/2-Glosario_LEL.md` (`Variante`: `"El diagnóstico es positivo si la variante es patogénica"`) y `analisis.py#L81-L82` | Low |

## Open Questions

- Ninguna pregunta abierta bloqueante.

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada y verificada contra `app/src/core/models/analisis.py`, `estudios.py`, `usuarios.py` y `enums.py`. | Estado marcado como `Approved`. |
