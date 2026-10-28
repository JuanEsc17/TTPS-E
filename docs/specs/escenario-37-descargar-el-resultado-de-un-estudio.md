# WORKFLOW: Escenario 37 – Descargar el resultado de un estudio
**Versión**: 1.0
**Fecha**: 2026-10-28
**Autor**: Workflow Architect
**Estado**: Approved
**Implementa**: `.ai/3-Escenarios.md#Escenario-37`

### Símbolos LEL utilizados

| Categoría LEL | Símbolo LEL | Correspondencia en Modelo / Sistema (`app/src/core/models/`) |
|---|---|---|
| **Sujetos** | **Paciente** | `Usuario` (`rol = Rol.PACIENTE`) + `Paciente` (`pacientes.id`, titular del `Estudio`) |
| **Sujetos** | **Médico** | `Usuario` (`rol = Rol.MEDICO` o `Rol.GERENTE_MEDICO`) + `Medico` (`medicos.id`, médico tratante del `Estudio`) |
| **Sujetos** | **Bioinformático** | `Usuario` (`rol = Rol.BIOINFORMATICO`, quien cargó previamente las **variantes** generando el **resultado**) |
| **Objetos** | **Resultado** | Modelo `Resultado` (`resultados`: `id`, `analisis_id`, `positivo`, `pdf_path`, `generado_en`) y función `calcular_positivo(variantes)` en `app/src/core/models/analisis.py` |
| **Objetos** | **Estudio** | Modelo `Estudio` (`estudios`: `id`, `paciente_id`, `medico_id`, `estado`, relación `analisis`) |
| **Objetos** | **Variante** | Modelo `Variante` (`variantes`: `id`, `gen_id`, `notacion`, `clinvar_id`, `clasificacion: ClasificacionVariante`) y `AnalisisVariante` (`analisis_variantes`) |
| **Objetos** | **Gen** | Modelo `Gen` (`genes`: `id`, `simbolo`, `nombre`, `es_hallazgo_secundario`) y `AnalisisGen` (`analisis_genes`) |
| **Objetos** | **VUS** | `ClasificacionVariante.VUS` (`"vus"`) en `app/src/core/models/enums.py` |
| **Objetos** | **Aviso** | Modelo `Aviso` (`avisos`: notificaciones por `CanalAviso.MAIL` y `CanalAviso.APP` al **paciente** y al **médico**) |
| **Verbos** | **Descargar resultado** | Consultar el detalle del **resultado** (positividad/negatividad y **variantes**) y bajar el archivo PDF desde el sistema |
| **Verbos** | **Cargar resultado** | Paso inmediatamente anterior que dejó al **estudio** en **Resultado cargado** y disparó los avisos |
| **Verbos** | **Iniciar sesión** | El **paciente** (o **médico**) ingresa al sistema para acceder al **resultado** |
| **Estados** | **Resultado cargado** | `EstadoEstudio.RESULTADO_CARGADO` (`"Resultado cargado"`) |

---

## Overview

- **Objetivo:** Permitir que el **paciente** consulte y descargue el PDF con el **resultado** de su **estudio** y que el **médico** tratante lo reciba y pueda consultarlo/descargarlo.
- **Contexto:** El **bioinformático** ya cargó las **variantes** encontradas en el análisis (`Analisis`, `AnalisisVariante`), se generó el registro `Resultado` con su PDF (`Resultado.pdf_path` y `Resultado.positivo = calcular_positivo(variantes)`), y el **estudio** se encuentra en estado **Resultado cargado** (`EstadoEstudio.RESULTADO_CARGADO`).
- **Recursos:** **Resultado** en PDF (`resultados.pdf_path`), **estudio** (`estudios`), **variantes** del **paciente** (`analisis_variantes` -> `variantes`), mail de aviso y **avisos** en el sistema (`avisos`).
- **Episodios:**
  1. El sistema envía un mail (y registra un **aviso** en la aplicación) al **paciente** y al **médico** avisando que el **resultado** está disponible.
  2. El **paciente** ingresa al sistema (**iniciar sesión**).
  3. El **paciente** selecciona el **estudio**.
  4. El sistema muestra el **resultado**, que informa si fue positivo o negativo (`Resultado.positivo`, positivo si existe al menos una **variante** con `ClasificacionVariante.PATOGENICA`) y las **variantes** encontradas del **paciente**.
  5. El **paciente** descarga el **resultado** en PDF.
  6. El **médico** recibe el **resultado** (y puede visualizarlo y descargar el mismo PDF desde su panel).

**Resumen del flujo:**
1. **Notificación de disponibilidad (`STEP 1`):** Al quedar el `Estudio` en `EstadoEstudio.RESULTADO_CARGADO` con su fila en `resultados`, el servicio de avisos registra y envía las notificaciones por `CanalAviso.MAIL` y `CanalAviso.APP` tanto a `estudio.paciente.usuario_id` como a `estudio.medico.usuario_id`.
2. **Consulta del detalle del resultado (`STEP 2`):** El **paciente** (o el **médico** tratante) autenticado selecciona el **estudio** (`GET /api/estudios/{estudio_id}/resultado`). El backend verifica estrictamente la pertenencia (`estudio.paciente.usuario_id == usuario.id` o `estudio.medico.usuario_id == usuario.id`), comprueba que `estudio.estado == EstadoEstudio.RESULTADO_CARGADO` y devuelve el último `Analisis` con su `Resultado` (`positivo: bool`, `generado_en`) y el listado detallado de **variantes** (`notacion`, `clasificacion`, `clinvar_id`, `gen.simbolo`).
3. **Descarga del PDF (`STEP 3`):** El **paciente** (o el **médico**) solicita `GET /api/estudios/{estudio_id}/resultado/pdf`. El servicio verifica los permisos, comprueba la existencia física del archivo en `Resultado.pdf_path` (regenerándolo de forma determinística a partir de los datos de `Analisis`, `Resultado` y `Variante` si el archivo no se encontrara en disco) y transmite el binario con `Content-Type: application/pdf` y `Content-Disposition: attachment`.

---

## Actors

| Actor | Rol en este workflow |
|---|---|
| **Paciente** (Sujeto LEL) | Recibe el aviso por mail/app, inicia sesión, selecciona su **estudio**, visualiza el **resultado** y descarga el archivo PDF. |
| **Médico** (Sujeto LEL) | Recibe el aviso por mail/app y el **resultado** del **estudio** de su **paciente** (pudiendo consultarlo y descargar el PDF). |
| **Router de Estudios / Resultados** (`app/src/routers/resultados.py`) | Autentica al usuario, valida acceso al recurso y sirve tanto el JSON del **resultado** como el stream `application/pdf`. |
| **Servicio de Resultados y Avisos** (`app/src/services/resultado_service.py`, `aviso_service.py`) | Despacha los avisos al **paciente** y al **médico**, aplica el control de acceso sobre datos genéticos sensibles, obtiene el `Resultado` vigente y gestiona la lectura/regeneración del PDF. |
| **Repositorio de Análisis y Estudios** (`app/src/repos/analisis_repo.py`, `estudio_repo.py`) | Consulta `estudios`, `analisis`, `analisis_genes`, `analisis_variantes`, `variantes`, `genes`, `resultados` y `avisos`. |
| **PostgreSQL** (`db`) | Almacena la trazabilidad de `Analisis`, `Resultado`, `AnalisisVariante` y el estado de entrega en `avisos`. |

---

## Prerequisites

- **Sesión y Rol:**
  - Para consultar o descargar el **resultado**: sesión activa válida con `Rol.PACIENTE` (titular del `Estudio`) o `Rol.MEDICO` / `Rol.GERENTE_MEDICO` (médico tratante del `Estudio`), con `Usuario.debe_cambiar_password == False`.
- **Datos existentes en `app/src/core/models/`:**
  - Existe el `Estudio` en la tabla `estudios` con `estado == EstadoEstudio.RESULTADO_CARGADO`.
  - Existe al menos una fila en `analisis` (`estudio_id == estudio.id`) con su fila asociada en `resultados` (`analisis_id == analisis.id`, `positivo`, `pdf_path`, `generado_en`) y sus filas en `analisis_variantes`.
- **Estado previo del `Estudio`:** `EstadoEstudio.RESULTADO_CARGADO`.

---

## Trigger

1. **Aviso de disponibilidad (Episodio 1):** Transición del `Estudio` a `EstadoEstudio.RESULTADO_CARGADO` al finalizar **Cargar resultado**.
2. **Visualización del resultado en pantalla (Episodios 2-4 y 6):** El **paciente** o el **médico** selecciona el **estudio** -> `GET /api/estudios/{estudio_id}/resultado`.
3. **Descarga del PDF del resultado (Episodios 5 y 6):** El **paciente** o el **médico** presiona "Descargar resultado en PDF" -> `GET /api/estudios/{estudio_id}/resultado/pdf`.

---

## Workflow Tree

### STEP 1: Notificación por mail y aviso interno al paciente y al médico (Episodio 1)
**Actor**: Servicio de Resultados (`resultado_service.py`) -> Servicio de Avisos (`aviso_service.py`) -> Repositorio (`usuario_repo.py`)
**Action**:
  1. Crea en la tabla `avisos` cuatro registros (dos para `estudio.paciente.usuario_id` y dos para `estudio.medico.usuario_id` en canales `CanalAviso.APP` y `CanalAviso.MAIL`) informando que el **resultado** del **estudio** `#{estudio.id}` ya se encuentra disponible.
  2. Envía los correos electrónicos al mail del **paciente** (`estudio.paciente.usuario.email`) y al mail del **médico** (`estudio.medico.usuario.email`).
  3. Marca `aviso.enviado = True` y `aviso.enviado_en = now()` al confirmarse el despacho.
**Timeout**: `5s` (con hasta 2 reintentos de envío SMTP/mail).
**Input**: `{ estudio_id: 88, resultado_id: 19, paciente_usuario_id: 52, medico_usuario_id: 11 }`
**Output on SUCCESS**: `{ avisos_creados_ids: list[int], mails_enviados: True }` -> GO TO STEP 2
**Output on FAILURE**:
  - `FAILURE(transient_mail_error)`: El servidor de correo falla temporalmente -> los registros en `avisos` con `CanalAviso.APP` quedan igualmente disponibles (`enviado = True`) y los de `CanalAviso.MAIL` quedan con `enviado = False` para reintento asíncrono sin revertir el `EstadoEstudio.RESULTADO_CARGADO`.

**Observable states during this step**:
  - Customer/Actor (**Paciente** y **Médico**) sees: Mail recibido en su casilla ("El resultado de su estudio de exoma clínico ya está disponible") y notificación en la campana de **avisos** del sistema.
  - Operator sees: Filas en `avisos` con `enviado = True` y `enviado_en` completado.
  - Database:
    - Tabla `avisos`: nuevas filas para `paciente.usuario_id` y `medico.usuario_id`.
  - Logs: `[aviso_service] step=1_notificacion_resultado estudio_id=88 paciente_uid=52 medico_uid=11`

---

### STEP 2: Consulta del resultado y variantes del estudio (Episodios 2, 3, 4 y 6)
**Actor**: **Paciente** / **Médico** -> Router (`resultados.py`) -> Servicio (`resultado_service.py`) -> Repositorio (`analisis_repo.py`)
**Action**:
  1. Verifica la sesión activa y comprueba el control de acceso estricto sobre datos genéticos:
     - Si `usuario.rol == Rol.PACIENTE`: debe cumplirse `estudio.paciente.usuario_id == usuario.id`.
     - Si `usuario.rol in (Rol.MEDICO, Rol.GERENTE_MEDICO)`: debe cumplirse `estudio.medico.usuario_id == usuario.id`.
     - Cualquier otro usuario o rol recibe `403 Forbidden`.
  2. Verifica que `estudio.estado == EstadoEstudio.RESULTADO_CARGADO` y que exista un `Analisis` con `Resultado` asociado (tomando el último elemento de `estudio.analisis` que posea `resultado is not None`, contemplando también el historial en caso de reanálisis).
  3. Marca como leídos (`Aviso.leido = True`) los avisos pendientes de ese estudio para el usuario que consulta.
  4. Devuelve la estructura del `Resultado` (`positivo`, `generado_en`, `tipo_analisis`) junto con las **variantes** asociadas (`Variante.notacion`, `Variante.clasificacion`, `Variante.clinvar_id`, `Gen.simbolo`, `Gen.nombre`, `Gen.es_hallazgo_secundario`).
**Timeout**: `2s`
**Input**: `{ estudio_id: 88, usuario_autenticado_id: 52, rol: "Rol.PACIENTE" }`
**Output on SUCCESS**: Datos estructurados del `Resultado` y lista de `Variante` -> GO TO STEP 3
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Usuario sin sesión activa -> retornar `401 Unauthorized`.
  - `FAILURE(forbidden)`: El **paciente** o **médico** autenticado no es el titular/tratante del `Estudio` -> retornar `403 Forbidden` (`ACCESO_RESULTADO_DENEGADO`) y registrar intento de acceso en logs de auditoría de seguridad.
  - `FAILURE(invalid_state)`: El `Estudio` no se encuentra en `EstadoEstudio.RESULTADO_CARGADO` (por ejemplo, sigue en `EstadoEstudio.EN_ANALISIS_BIOINFORMATICO`) -> retornar `409 Conflict` (`RESULTADO_AUN_NO_DISPONIBLE`).
  - `FAILURE(not_found)`: `estudio_id` inexistente -> retornar `404 Not Found`.

**Observable states during this step**:
  - Customer/Actor (**Paciente** / **Médico**) sees: Pantalla de detalle del **resultado** mostrando claramente si el diagnóstico fue **Positivo** (`positivo == True`, cuando alguna variante es `patogenica`) o **Negativo** (`positivo == False`), la tabla de **variantes** encontradas en cada **gen** con su clasificación (`patogenica`, `benigna`, `inocua`, `vus`) y el botón "Descargar PDF".
  - Operator sees: Acceso auditado a `GET /api/estudios/88/resultado`.
  - Database:
    - Lectura (`SELECT`) sobre `estudios`, `analisis`, `resultados`, `analisis_variantes`, `variantes` y `genes`.
    - Actualización `avisos.leido = True` para el usuario autenticado.
  - Logs: `[resultado_service] step=2_consulta_resultado estudio_id=88 usuario_id=52 rol=paciente positivo=true`

---

### STEP 3: Descarga del archivo PDF del resultado (Episodios 5 y 6)
**Actor**: **Paciente** / **Médico** -> Router (`resultados.py`) -> Servicio (`resultado_service.py`) -> Sistema de Archivos / Generador PDF
**Action**:
  1. Revalida la autorización de acceso del **paciente** titular o **médico** tratante sobre `estudio_id` y que `estudio.estado == EstadoEstudio.RESULTADO_CARGADO`.
  2. Obtiene `resultado.pdf_path` del último `Analisis` completado del `Estudio`.
  3. Verifica que la ruta `pdf_path` esté dentro del directorio permitido de almacenamiento de resultados (protección contra Path Traversal) y que el archivo exista en disco.
  4. Si el archivo PDF no se encontrara en disco por una contingencia de almacenamiento efímero, el servicio lo regenera en el acto a partir de los registros inmutables de `Estudio`, `Analisis`, `Resultado` y `Variante` en PostgreSQL y lo guarda en `resultado.pdf_path`.
  5. Envía el archivo binario con cabeceras `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="resultado_estudio_{estudio.id}.pdf"` y `Cache-Control: private, no-store`.
**Timeout**: `5s`
**Input**: `{ estudio_id: 88, resultado_id: 19, pdf_path: "storage/resultados/estudio_88_analisis_12.pdf" }`
**Output on SUCCESS**: Stream binario `application/pdf` (`200 OK`) -> FIN DEL WORKFLOW.
**Output on FAILURE**:
  - `FAILURE(forbidden)`: Usuario distinto del **paciente** titular o **médico** tratante -> retornar `403 Forbidden` (`ACCESO_RESULTADO_DENEGADO`).
  - `FAILURE(invalid_state)`: `estudio.estado != EstadoEstudio.RESULTADO_CARGADO` -> retornar `409 Conflict` (`RESULTADO_AUN_NO_DISPONIBLE`).
  - `FAILURE(file_and_regeneration_error)`: El archivo no está en disco y falla su regeneración -> ejecutar `ABORT_CLEANUP` -> retornar `500 Internal Server Error` (`PDF_NO_DISPONIBLE`, `retryable=True`).

**Observable states during this step**:
  - Customer/Actor (**Paciente** / **Médico**) sees: Descarga inmediata del archivo `resultado_estudio_88.pdf` en su dispositivo.
  - Operator sees: Respuesta `200 OK` (`application/pdf`) en logs de auditoría.
  - Database: Sin cambios de estado (`Estudio.estado` permanece en `EstadoEstudio.RESULTADO_CARGADO`).
  - Logs: `[resultado_service] step=3_descarga_pdf_ok estudio_id=88 resultado_id=19 usuario_id=52`

---

### ABORT_CLEANUP: Limpieza ante fallo de lectura o regeneración de PDF
**Triggered by**: Error de E/S al escribir o leer el archivo en `STEP 3`.
**Actions** (in order):
  1. Si durante un intento de regeneración del PDF en `STEP 3` se creó un archivo temporal incompleto (`.tmp`), eliminarlo del sistema de archivos (`Path.unlink(missing_ok=True)`).
  2. Registrar alerta `ERROR` con `estudio_id`, `resultado_id` y `pdf_path`.
**What customer/actor (**Paciente** / **Médico**) sees**: Mensaje de error indicando que no se pudo descargar el PDF en este momento y que puede reintentar en unos segundos, manteniendo visible en pantalla toda la información del resultado.
**What operator sees**: Log `ERROR` detallando el fallo de sistema de archivos.

---

## State Transitions

```
Estudio (estudios.estado):
  [EstadoEstudio.EN_ANALISIS_BIOINFORMATICO]
    -- (Verbo previo: Cargar resultado por el Bioinformático) -->
  [EstadoEstudio.RESULTADO_CARGADO]
    -- (STEP 1: Envío de mail y Aviso al Paciente y al Médico) -->
  [EstadoEstudio.RESULTADO_CARGADO]
    -- (STEP 2 y STEP 3: Paciente y Médico consultan y descargan el Resultado en PDF N veces) -->
  [EstadoEstudio.RESULTADO_CARGADO]

Aviso (avisos):
  [Creado (enviado=False, leido=False)]
    -- (STEP 1: Despacho de notificación) --> [Entregado (enviado=True, enviado_en=now(), leido=False)]
    -- (STEP 2: Paciente/Médico abre el resultado) --> [Leído (enviado=True, leido=True)]
```

---

## Handoff Contracts

### 1. Frontend (Paciente / Médico) -> Backend: Consultar detalle del resultado
**Endpoint**: `GET /api/estudios/{estudio_id}/resultado`
**Success response** (`200 OK`):
```json
{
  "ok": true,
  "data": {
    "estudio_id": 88,
    "estado_estudio": "Resultado cargado",
    "analisis_id": 12,
    "tipo_analisis": "inicial",
    "resultado_id": 19,
    "positivo": true,
    "generado_en": "2026-10-28T18:40:00Z",
    "patologia_sospechada": {
      "id": 1,
      "nombre": "Fabry"
    },
    "variantes": [
      {
        "id": 304,
        "gen": {
          "id": 2,
          "simbolo": "GLA",
          "nombre": "Galactosidasa alfa",
          "es_hallazgo_secundario": false
        },
        "notacion": "c.644A>G",
        "clinvar_id": "VCV000010730",
        "clasificacion": "patogenica"
      },
      {
        "id": 309,
        "gen": {
          "id": 2,
          "simbolo": "GLA",
          "nombre": "Galactosidasa alfa",
          "es_hallazgo_secundario": false
        },
        "notacion": "c.937G>T",
        "clinvar_id": "VCV000010765",
        "clasificacion": "benigna"
      }
    ],
    "pdf_download_url": "/api/estudios/88/resultado/pdf"
  }
}
```
**Failure response** (`401` / `403` / `404` / `409`):
```json
{
  "ok": false,
  "error": "No tiene permisos para acceder al resultado de este estudio.",
  "code": "ACCESO_RESULTADO_DENEGADO",
  "retryable": false
}
```
**Timeout**: `5s`
**ON FAILURE**: Redirigir a la vista de estudios propios o mostrar aviso de acceso restringido.

---

### 2. Frontend (Paciente / Médico) -> Backend: Descargar PDF del resultado
**Endpoint**: `GET /api/estudios/{estudio_id}/resultado/pdf`
**Success response** (`200 OK`):
- **Headers**:
  - `Content-Type: application/pdf`
  - `Content-Disposition: attachment; filename="resultado_estudio_88.pdf"`
  - `Cache-Control: private, no-store`
- **Body**: Stream binario PDF (`%PDF-1.7 ...`) con el encabezado del laboratorio, datos del **paciente** y **médico** tratante, conclusión de positividad/negatividad (`positivo: true/false`) y tabla de **variantes** encontradas con su clasificación.

**Failure response** (`401` / `403` / `404` / `409` / `500`):
```json
{
  "ok": false,
  "error": "El resultado de este estudio aún no se encuentra cargado.",
  "code": "RESULTADO_AUN_NO_DISPONIBLE",
  "retryable": false
}
```
**Timeout**: `10s`
**ON FAILURE**: Mostrar notificación de error al usuario sin abandonar la pantalla de detalle del estudio.

---

## Cleanup Inventory

| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Archivo temporal `.tmp` durante regeneración de contingencia del PDF | Step 3 | `ABORT_CLEANUP` | `Path.unlink(missing_ok=True)` |

---

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | En `app/src/core/models/analisis.py` existen los modelos `Analisis`, `AnalisisGen`, `AnalisisVariante`, `Resultado` (`id`, `analisis_id`, `positivo`, `pdf_path`, `generado_en`) y la función `calcular_positivo(variantes)` que devuelve `True` si alguna variante tiene `ClasificacionVariante.PATOGENICA`. | Low | Overview, STEP 2 | La respuesta del endpoint expone exactamente `Resultado.positivo`, `Resultado.pdf_path` y las filas vinculadas en `AnalisisVariante` -> `Variante` -> `Gen`. |
| RC-2 | En `.ai/1-Entrevista.md` (línea 315) se remarca que la filtración de datos genéticos de una variante de un paciente es un riesgo crítico legal y de privacidad. | Critical | STEP 2, STEP 3 | El control de acceso valida explícitamente la propiedad del recurso (`estudio.paciente.usuario_id == usuario.id` o `estudio.medico.usuario_id == usuario.id`) en ambos endpoints y agrega `Cache-Control: private, no-store`. |
| RC-3 | `Estudio.analisis` es una lista ordenada por `Analisis.id` (`order_by="Analisis.id"`) porque un estudio puede tener un análisis `INICIAL` y posteriores `REANALISIS`. | Medium | STEP 2, STEP 3 | El servicio devuelve por defecto el último `Analisis` que cuente con `Resultado` cargado (y permite consultar resultados de análisis anteriores si hubo reanálisis). |

---

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| `TC-01`: Happy path – Notificación por mail y aviso al paciente y al médico | El estudio pasa a `EstadoEstudio.RESULTADO_CARGADO` | Se crean los registros en `avisos` (`CanalAviso.APP` y `CanalAviso.MAIL`) para `paciente.usuario_id` y `medico.usuario_id` con `enviado=True`. |
| `TC-02`: Happy path – El paciente consulta y descarga el PDF de su resultado positivo | `GET /api/estudios/{id}/resultado` y `GET /api/estudios/{id}/resultado/pdf` por el paciente titular | El primer endpoint retorna `200 OK` con `positivo=True` (cuando hay variante `PATOGENICA`) y la lista de variantes; el segundo retorna `200 OK` con `Content-Type: application/pdf` y bytes `%PDF-`. |
| `TC-03`: Happy path – El médico tratante consulta y descarga el resultado de su paciente | `GET /api/estudios/{id}/resultado` y `GET /api/estudios/{id}/resultado/pdf` por el médico de `estudio.medico_id` | Ambos endpoints retornan `200 OK` con el detalle de variantes y el PDF. |
| `TC-04`: Resultado negativo cuando las variantes son benignas, inocuas o VUS | Estudio en `RESULTADO_CARGADO` con variantes de clasificación `BENIGNA` y `VUS` (sin ninguna `PATOGENICA`) | `calcular_positivo` es `False`; `GET /api/estudios/{id}/resultado` retorna `positivo=False` junto con las variantes halladas. |
| `TC-05`: Rechazo de seguridad cuando otro paciente intenta acceder o descargar el resultado | `GET /api/estudios/{id}/resultado` o `/pdf` autenticado como un paciente distinto de `estudio.paciente_id` | Retorna `403 Forbidden` (`ACCESO_RESULTADO_DENEGADO`). |
| `TC-06`: Rechazo cuando otro médico que no es el médico tratante intenta descargar el resultado | `GET /api/estudios/{id}/resultado/pdf` autenticado como un médico distinto de `estudio.medico_id` | Retorna `403 Forbidden` (`ACCESO_RESULTADO_DENEGADO`). |
| `TC-07`: Rechazo cuando el estudio aún no tiene resultado cargado | `GET /api/estudios/{id}/resultado` sobre un estudio en `EstadoEstudio.EN_ANALISIS_BIOINFORMATICO` o `EN_VIAJE_COREA` | Retorna `409 Conflict` (`RESULTADO_AUN_NO_DISPONIBLE`). |

---

## Assumptions

| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | El diagnóstico en el **resultado** se informa como positivo (`Resultado.positivo == True`) si y solo si al menos una de las **variantes** seleccionadas en el análisis tiene `ClasificacionVariante.PATOGENICA`. | Verificado en `.ai/2-Glosario_LEL.md` (`Objeto: Variante`: "El diagnóstico es positivo si la variante es patogénica") y `app/src/core/models/analisis.py` (`calcular_positivo`). | Bajo; ya está codificado en `analisis.py`. |
| A2 | Tanto el **paciente** como el **médico** tratante acceden al mismo documento PDF generado en `Resultado.pdf_path`, además de recibir el aviso por correo electrónico. | Verificado en `.ai/1-Entrevista.md` (líneas 49-52 y 156-157) y `.ai/3-Escenarios.md#Escenario-37`. | Bajo. |

## Open Questions

- En el caso de que un **estudio** haya tenido un **reanálisis** (`TipoAnalisis.REANALISIS`) posterior al análisis inicial (`TipoAnalisis.INICIAL`), ¿el paciente debe poder descargar desde la misma vista tanto el PDF del último resultado como el PDF histórico del primer análisis? *(El modelo `Estudio.analisis` como lista ordenada ya soporta conservar y descargar ambos).*

## Spec vs Reality Audit Log

| Date | Finding | Action taken |
|---|---|---|
| 2026-10-28 | Especificación inicial creada verificando `Estudio`, `Analisis`, `AnalisisVariante`, `Variante`, `Resultado`, `calcular_positivo` y `Aviso` en `app/src/core/models/`. | Aprobada. |
