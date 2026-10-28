# Workflow Registry & Discovery Audit — Sistema de Seguimiento de Estudios de Exoma Clínico (TTPS-E)

**Versión**: 1.0  
**Fecha**: 2026-10-28  
**Autor**: Workflow Architect (`agency-workflow-architect`)  
**Fuentes de verdad**: [`.ai/1-Entrevista.md`](../../.ai/1-Entrevista.md), [`.ai/2-Glosario_LEL.md`](../../.ai/2-Glosario_LEL.md), [`.ai/3-Escenarios.md`](../../.ai/3-Escenarios.md), [`app/src/core/models/`](../../app/src/core/models/__init__.py)

---

## View 1: By Workflow (Catálogo Maestro de Escenarios)

| # | Workflow (Escenario) | Archivo de Especificación (`docs/specs/`) | Estado Spec | Trigger Principal | Actor Primario (Sujeto LEL) | Verbo LEL Asociado | Última Revisión |
| :-: | :--- | :--- | :---: | :--- | :--- | :--- | :---: |
| 01 | **Escenario 1**: Dar de alta un paciente | [`escenario-01-dar-de-alta-un-paciente.md`](./escenario-01-dar-de-alta-un-paciente.md) | `Approved` | `POST /api/v1/pacientes` | **Médico** | **Dar de alta paciente** | 2026-10-28 |
| 02 | **Escenario 2**: Dar de alta un estudio | [`escenario-02-dar-de-alta-un-estudio.md`](./escenario-02-dar-de-alta-un-estudio.md) | `Approved` | `POST /api/v1/estudios` | **Médico** | **Dar de alta estudio** | 2026-10-28 |
| 03 | **Escenario 3**: Emitir un presupuesto | [`escenario-03-emitir-un-presupuesto.md`](./escenario-03-emitir-un-presupuesto.md) | `Approved` | `POST /api/v1/estudios/{id}/presupuesto` | **Administrativo** | *(Emitir presupuesto)* | 2026-10-28 |
| 04 | **Escenario 4**: Autorizar un estudio por obra social | [`escenario-04-autorizar-un-estudio-por-obra-social.md`](./escenario-04-autorizar-un-estudio-por-obra-social.md) | `Approved` | `POST /api/v1/estudios/{id}/autorizaciones` | **Administrativo** / **Paciente** | *(Autorizar por obra social)* | 2026-10-28 |
| 05 | **Escenario 5**: Reautorizar un estudio rechazado | [`escenario-05-reautorizar-un-estudio-rechazado.md`](./escenario-05-reautorizar-un-estudio-rechazado.md) | `Approved` | `POST /api/v1/estudios/{id}/demandas` | **Paciente** / **Administrativo** | *(Reautorizar estudio)* | 2026-10-28 |
| 06 | **Escenario 6**: Pagar un estudio particular | [`escenario-06-pagar-un-estudio-particular.md`](./escenario-06-pagar-un-estudio-particular.md) | `Approved` | `POST /api/v1/presupuestos/{id}/pagos` | **Paciente** | **Pagar presupuesto** | 2026-10-28 |
| 07 | **Escenario 7**: Solicitar un turno de extracción | [`escenario-07-solicitar-un-turno-de-extraccion.md`](./escenario-07-solicitar-un-turno-de-extraccion.md) | `Approved` | `POST /api/v1/estudios/{id}/turnos` | **Paciente** | **Sacar turno** | 2026-10-28 |
| 08 | **Escenario 8**: Cancelar un turno de extracción | [`escenario-08-cancelar-un-turno-de-extraccion.md`](./escenario-08-cancelar-un-turno-de-extraccion.md) | `Approved` | `DELETE /api/v1/turnos/{id}` | **Paciente** | **Cancelar turno** | 2026-10-28 |
| 09 | **Escenario 9**: Registrar la toma de una muestra | [`escenario-09-registrar-la-toma-de-una-muestra.md`](./escenario-09-registrar-la-toma-de-una-muestra.md) | `Approved` | `POST /api/v1/webhooks/telegram/muestra-tomada` | **Centro de extracción** (`Bot de Telegram`) | *(Tomar muestra)* | 2026-10-28 |
| 10 | **Escenario 10**: Remuestrear un estudio | [`escenario-10-remuestrear-un-estudio.md`](./escenario-10-remuestrear-un-estudio.md) | `Approved` | `POST /api/v1/muestras/{id}/descartar` | **Administrativo** / **Paciente** | **Remuestrear** | 2026-10-28 |
| 11 | **Escenario 11**: Transportar muestras al laboratorio central | [`escenario-11-transportar-muestras-al-laboratorio-central.md`](./escenario-11-transportar-muestras-al-laboratorio-central.md) | `Approved` | `POST /api/v1/ordenes-del-dia/{id}/paradas/{pid}/recoger` y `/llegada-lab-central` | **Transportista** | *(Transportar muestras)* | 2026-10-28 |
| 12 | **Escenario 12**: Formar un sample-set de muestras | [`escenario-12-formar-un-sample-set-de-muestras.md`](./escenario-12-formar-un-sample-set-de-muestras.md) | `Approved` | Evento interno al validar muestra $\ge 2\text{ ml}$ en `En laboratorio central` | `Sistema` (**Administrativo** / **Transportista**) | **Armar sample set** | 2026-10-28 |
| 13 | **Escenario 13**: Enviar un sample-set de muestras a Corea | [`escenario-13-enviar-un-sample-set-de-muestras-a-corea.md`](./escenario-13-enviar-un-sample-set-de-muestras-a-corea.md) | `Approved` | Cierre de `SampleSet` + `POST /api/v1/sample-sets/{id}/retiro-fedex` | **Administrativo** / `FedEx` | **Retirar sample set** | 2026-10-28 |
| 14 | **Escenario 14**: Enviar una muestra de Pompe urgente | [`escenario-14-enviar-una-muestra-de-pompe-urgente.md`](./escenario-14-enviar-una-muestra-de-pompe-urgente.md) | `Approved` | Ingreso de muestra con `es_pompe_urgente == True` al `SampleSet` abierto | **Administrativo** / **Transportista** | **Armar sample set** / **Retirar sample set** | 2026-10-28 |
| 15 | **Escenario 15**: Analizar un estudio mediante bioinformática | [`escenario-15-analizar-un-estudio-mediante-bioinformatica.md`](./escenario-15-analizar-un-estudio-mediante-bioinformatica.md) | `Approved` | `POST /api/v1/estudios/{id}/datos-crudos`, `/tomar-analisis` y `/variantes` | **Administrativo** / **Bioinformático** | **Cargar resultado** | 2026-10-28 |
| 16 | **Escenario 16**: Informar el resultado de un estudio | [`escenario-16-informar-el-resultado-de-un-estudio.md`](./escenario-16-informar-el-resultado-de-un-estudio.md) | `Approved` | Confirmación de variantes del análisis bioinformático (`POST /api/v1/analisis/{id}/resultado`) | **Bioinformático** / **Paciente** / **Médico** | **Cargar resultado** | 2026-10-28 |
| 17 | **Escenario 17**: Reanalizar un estudio | [`escenario-17-reanalizar-un-estudio.md`](./escenario-17-reanalizar-un-estudio.md) | `Approved` | `POST /api/v1/estudios/{id}/reanalisis` | **Médico** / **Bioinformático** / **Paciente** | **Reanalizar estudio** | 2026-10-28 |
| 18 | **Escenario 18**: Gestionar la información familiar | [`escenario-18-gestionar-la-informacion-familiar.md`](./escenario-18-gestionar-la-informacion-familiar.md) | `Approved` | `POST /api/v1/pacientes/{id}/familiares` | **Médico** | *(Cargar familiares y enviar familiograma)* | 2026-10-28 |
| 19 | **Escenario 19**: Registrar un paciente sin información familiar | [`escenario-19-registrar-un-paciente-sin-informacion-familiar.md`](./escenario-19-registrar-un-paciente-sin-informacion-familiar.md) | `Approved` | `POST /api/v1/pacientes` (`familiares = []`) | **Médico** | **Dar de alta paciente** | 2026-10-28 |
| 20 | **Escenario 20**: Cambiar la contraseña inicial | [`escenario-20-cambiar-la-contrasena-inicial.md`](./escenario-20-cambiar-la-contrasena-inicial.md) | `Approved` | `POST /api/v1/auth/password-inicial` | **Paciente** | **Cambiar contraseña inicial** | 2026-10-28 |
| 21 | **Escenario 21**: Registrar un médico | [`escenario-21-registrar-un-medico.md`](./escenario-21-registrar-un-medico.md) | `Approved` | `POST /api/v1/auth/registro/medico` | **Médico** | *(Auto-alta de médico)* | 2026-10-28 |
| 22 | **Escenario 22**: Registrar un administrativo | [`escenario-22-registrar-un-administrativo.md`](./escenario-22-registrar-un-administrativo.md) | `Approved` | `POST /api/v1/auth/registro/administrativo` | **Administrativo** | *(Auto-alta de administrativo)* | 2026-10-28 |
| 23 | **Escenario 23**: Gestionar una patología | [`escenario-23-gestionar-una-patologia.md`](./escenario-23-gestionar-una-patologia.md) | `Approved` | `POST /api/v1/patologias` / `PUT /api/v1/patologias/{id}` | **Gerente médico** | *(Dar de alta / modificar patología)* | 2026-10-28 |
| 24 | **Escenario 24**: Consultar variantes | [`escenario-24-consultar-variantes.md`](./escenario-24-consultar-variantes.md) | `Approved` | `GET /api/v1/genes/{simbolo}/variantes` | **Bioinformático** | *(Consultar variantes en API de bioinformática)* | 2026-10-28 |
| 25 | **Escenario 25**: Consultar el chatbot sobre patologías | [`escenario-25-consultar-el-chatbot-sobre-patologias.md`](./escenario-25-consultar-el-chatbot-sobre-patologias.md) | `Approved` | `POST /api/v1/chatbot/consultas` | **Paciente** | *(Consultar al chatbot)* | 2026-10-28 |
| 26 | **Escenario 26**: Verificar el ingreso desde una máquina nueva | [`escenario-26-verificar-el-ingreso-desde-una-maquina-nueva.md`](./escenario-26-verificar-el-ingreso-desde-una-maquina-nueva.md) | `Approved` | `POST /api/v1/auth/verificar-dispositivo` | Todos los sujetos del LEL | **Iniciar sesión** | 2026-10-28 |
| 27 | **Escenario 27**: Iniciar sesión | [`escenario-27-iniciar-sesion.md`](./escenario-27-iniciar-sesion.md) | `Approved` | `POST /api/v1/auth/login` | Todos los sujetos del LEL | **Iniciar sesión** | 2026-10-28 |
| 28 | **Escenario 28**: Cerrar sesión | [`escenario-28-cerrar-sesion.md`](./escenario-28-cerrar-sesion.md) | `Approved` | `POST /api/v1/auth/logout` | Todos los sujetos del LEL | **Cerrar sesión** | 2026-10-28 |
| 29 | **Escenario 29**: Crear un cupón | [`escenario-29-crear-un-cupon.md`](./escenario-29-crear-un-cupon.md) | `Approved` | `POST /api/v1/cupones` | **Gerente médico** | *(Crear cupón)* | 2026-10-28 |
| 30 | **Escenario 30**: Asignar y aplicar un cupón | [`escenario-30-asignar-y-aplicar-un-cupon.md`](./escenario-30-asignar-y-aplicar-un-cupon.md) | `Approved` | `PATCH /api/v1/cupones/{id}/asignar-paciente` + `POST /api/v1/presupuestos/{id}/pagos` | **Médico** / **Paciente** | **Pagar presupuesto** | 2026-10-28 |
| 31 | **Escenario 31**: Registrar un gerente médico | [`escenario-31-registrar-un-gerente-medico.md`](./escenario-31-registrar-un-gerente-medico.md) | `Approved` | `POST /api/v1/admin/gerentes-medicos` | **Admin general** | *(Dar de alta gerente médico)* | 2026-10-28 |
| 32 | **Escenario 32**: Seguir una muestra en el mapa | [`escenario-32-seguir-una-muestra-en-el-mapa.md`](./escenario-32-seguir-una-muestra-en-el-mapa.md) | `Approved` | `GET /api/v1/estudios/{id}/mapa-seguimiento` + `POST /api/v1/ordenes-del-dia/{id}/posicion` | **Paciente** / **Transportista** | *(Mostrar posición en mapa de seguimiento)* | 2026-10-28 |
| 33 | **Escenario 33**: Ausentarse a un turno de extracción | [`escenario-33-ausentarse-a-un-turno-de-extraccion.md`](./escenario-33-ausentarse-a-un-turno-de-extraccion.md) | `Approved` | Job de cierre de turnos vencidos sin mensaje de `Bot de Telegram` / `POST /api/v1/turnos/{id}/ausencia` | **Paciente** / `Sistema` | *(Registrar ausencia y aplicar límite de 5)* | 2026-10-28 |
| 34 | **Escenario 34**: Cambiar la contraseña | [`escenario-34-cambiar-la-contrasena.md`](./escenario-34-cambiar-la-contrasena.md) | `Approved` | `POST /api/v1/auth/cambiar-password` | Todos los sujetos del LEL | **Cambiar contraseña** | 2026-10-28 |
| 35 | **Escenario 35**: Grabar la historia clínica | [`escenario-35-grabar-la-historia-clinica.md`](./escenario-35-grabar-la-historia-clinica.md) | `Approved` | `POST /api/v1/historia-clinica/transcribir` | **Médico** | **Grabar historia clínica** | 2026-10-28 |
| 36 | **Escenario 36**: Cargar los síntomas del paciente con SNOMED | [`escenario-36-cargar-los-sintomas-del-paciente-con-snomed.md`](./escenario-36-cargar-los-sintomas-del-paciente-con-snomed.md) | `Approved` | `GET /api/v1/sintomas/snomed?q=...` + validación en `POST /api/v1/pacientes` | **Médico** | **Cargar síntomas** | 2026-10-28 |
| 37 | **Escenario 37**: Descargar el resultado de un estudio | [`escenario-37-descargar-el-resultado-de-un-estudio.md`](./escenario-37-descargar-el-resultado-de-un-estudio.md) | `Approved` | `GET /api/v1/estudios/{id}/resultado/pdf` | **Paciente** / **Médico** | **Descargar resultado** | 2026-10-28 |

---

## View 2: By Component (`code` -> `workflows`)

| Componente / Módulo | Archivo(s) en `app/src/core/models/` | Workflows (Escenarios) en los que participa |
| :--- | :--- | :--- |
| **Enumeraciones del Dominio** | [`enums.py`](../../app/src/core/models/enums.py) | Todos los escenarios (01 a 37): `Rol`, `EstadoEstudio` (14 estados LEL), `TipoPago`, `ResultadoAutorizacion`, `EstadoSampleSet`, `ClasificacionVariante`, `OrigenGen`, `TipoAnalisis`, `MotivoDescarte`, `CanalAviso`. |
| **Constantes y Reglas de Negocio** | [`reglas.py`](../../app/src/core/models/reglas.py) | Esc. 03 (`calcular_precio`: 500 USD base hasta 5 genes + 30 USD/gen extra), Esc. 10 (`ML_MINIMOS_TUBO = 2`), Esc. 12 y 14 (`MUESTRAS_POR_SAMPLE_SET = 10`), Esc. 33 (`MAX_AUSENCIAS = 5`). |
| **Usuarios, Dispositivos 2FA y Avisos** | [`usuarios.py`](../../app/src/core/models/usuarios.py) | Esc. 01, 04, 07, 10, 15, 16, 20, 21, 22, 26, 27, 28, 31, 34, 37 (`Usuario`, `DispositivoConocido`, `CodigoVerificacion`, `Aviso`). |
| **Perfiles (Médico, Paciente, Transportista)** | [`perfiles.py`](../../app/src/core/models/perfiles.py) | Esc. 01, 02, 11, 18, 19, 21, 31, 32, 35, 36 (`Especialidad`, `MedicoEspecialidad`, `Medico`, `Transportista`, `Paciente`). |
| **Clínica (Patologías, Síntomas SNOMED, Familiares, Genes, Variantes)** | [`clinica.py`](../../app/src/core/models/clinica.py) | Esc. 01, 02, 15, 16, 17, 18, 19, 23, 24, 36 (`Patologia`, `Sintoma`, `PatologiaSintoma`, `PacienteSintoma`, `Familiar`, `FamiliarSintoma`, `Gen`, `PatologiaGen`, `Variante`). |
| **Estudios y Genes Evaluados** | [`estudios.py`](../../app/src/core/models/estudios.py) | Esc. 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 32, 33, 37 (`Estudio`, `EstudioGen`). |
| **Economía (Obras Sociales, Cupones, Presupuestos, Pagos, Autorizaciones, Demandas)** | [`economia.py`](../../app/src/core/models/economia.py) | Esc. 03, 04, 05, 06, 29, 30, 33 (`ObraSocial`, `Cupon`, `Presupuesto`, `Pago`, `Autorizacion`, `Demanda`). |
| **Centros de Extracción y Turnos** | [`turnos.py`](../../app/src/core/models/turnos.py) | Esc. 07, 08, 09, 10, 33 (`CentroExtraccion`, `Turno`). |
| **Logística (SampleSet, Muestra, OrdenDelDia, PosicionTransporte)** | [`logistica.py`](../../app/src/core/models/logistica.py) | Esc. 09, 10, 11, 12, 13, 14, 32 (`SampleSet`, `Muestra`, `OrdenDelDia`, `OrdenDelDiaParada`, `PosicionTransporte`). |
| **Análisis Bioinformático y Resultados** | [`analisis.py`](../../app/src/core/models/analisis.py) | Esc. 15, 16, 17, 24, 37 (`DatosCrudos`, `Analisis`, `AnalisisGen`, `AnalisisVariante`, `Resultado`, `calcular_positivo`). |
| **Configuración del Sistema** | [`configuracion.py`](../../app/src/core/models/configuracion.py) | Parámetros globales (`Configuracion`). |
| **Clientes de APIs Externas (`app/clients/`)** | *(Por implementar según SDD)* | `API de bioinformática` (Esc. 02, 15, 17, 24), `API de familiograma` (Esc. 01, 18), `API de obras sociales` (Esc. 04), `API de cupones` (Esc. 06, 29, 30), `API del Ministerio de Salud` (Esc. 13, 14), `API de optimización de recorridos` (Esc. 11), `Bot de Telegram` (Esc. 09), `Chatbot` (Esc. 25), `SNOMED` (Esc. 01, 18, 23, 36), `Transcriptor de audio` (Esc. 35), `FedEx` (Esc. 13, 14). |

---

## View 3: By User Journey (Recorridos por Sujeto del LEL)

### 3.1. Recorridos del Paciente (`Rol.PACIENTE`)
| Qué experimenta el Paciente | Workflows (Escenarios) subyacentes | Punto de entrada |
| :--- | :--- | :--- |
| Ingresa por primera vez con las credenciales enviadas por mail | Esc. 27 (`Iniciar sesión`) -> Esc. 20 (`Cambiar la contraseña inicial`) | `/login` -> `/cambiar-password-inicial` |
| Ingresa desde una computadora o IP no registrada | Esc. 27 (`Iniciar sesión`) -> Esc. 26 (`Verificar el ingreso desde una máquina nueva`) | `/login` -> `/verificar-dispositivo` |
| Paga su presupuesto de forma particular (con o sin cupón) | Esc. 06 (`Pagar un estudio particular`) / Esc. 30 (`Asignar y aplicar un cupón`) | `/estudios/:id/presupuesto/pagar` |
| Solicita cobertura por obra social y sube demanda judicial ante rechazo | Esc. 04 (`Autorizar un estudio por obra social`) -> Esc. 05 (`Reautorizar un estudio rechazado`) | `/estudios/:id/cobertura` -> `/estudios/:id/demanda` |
| Reserva, cancela o se ausenta a un turno de extracción | Esc. 07 (`Solicitar un turno de extracción`), Esc. 08 (`Cancelar un turno de extracción`), Esc. 33 (`Ausentarse a un turno de extracción`) | `/estudios/:id/turnos` |
| Saca un nuevo turno sin cargo tras notificación de remuestreo | Esc. 10 (`Remuestrear un estudio`) -> Esc. 07 (`Solicitar un turno de extracción`) | `/estudios/:id/turnos` |
| Sigue el traslado de su muestra hacia el laboratorio central | Esc. 32 (`Seguir una muestra en el mapa`) | `/estudios/:id/seguimiento` |
| Consulta dudas sobre las 5 patologías lisosomales | Esc. 25 (`Consultar el chatbot sobre patologías`) | `/chatbot` |
| Visualiza y descarga el PDF del resultado de su estudio | Esc. 16 (`Informar el resultado de un estudio`) -> Esc. 37 (`Descargar el resultado de un estudio`) | `/estudios/:id/resultado` |

### 3.2. Recorridos del Médico Tratante (`Rol.MEDICO`) y Gerente Médico (`Rol.GERENTE_MEDICO`)
| Qué hace el Profesional Médico | Workflows (Escenarios) subyacentes | Punto de entrada |
| :--- | :--- | :--- |
| Se registra en el sistema con matrícula y especialidades | Esc. 21 (`Registrar un médico`) | `/registro/medico` |
| Da de alta un paciente (con dictado de historia clínica, síntomas SNOMED y familiares/familiograma o sin familiares) | Esc. 01 (`Dar de alta un paciente`), Esc. 35 (`Grabar la historia clínica`), Esc. 36 (`Cargar los síntomas del paciente con SNOMED`), Esc. 18 (`Gestionar la información familiar`), Esc. 19 (`Registrar un paciente sin información familiar`) | `/pacientes/nuevo` |
| Solicita un estudio de exoma clínico o un reanálisis | Esc. 02 (`Dar de alta un estudio`), Esc. 17 (`Reanalizar un estudio`) | `/estudios/nuevo`, `/estudios/:id/reanalisis` |
| Crea cupones (Gerente médico) y los asigna a médicos/pacientes | Esc. 29 (`Crear un cupón`), Esc. 30 (`Asignar y aplicar un cupón`) | `/gerencia/cupones`, `/medicos/cupones` |
| Administra las patologías y sus síntomas cardinales y secundarios (Gerente médico) | Esc. 23 (`Gestionar una patología`) | `/gerencia/patologias` |
| Recibe notificación y consulta el resultado de su paciente | Esc. 16 (`Informar el resultado de un estudio`), Esc. 37 (`Descargar el resultado de un estudio`) | `/estudios/:id/resultado` |

### 3.3. Recorridos de Operadores del Laboratorio (`ADMINISTRATIVO`, `BIOINFORMATICO`, `TRANSPORTISTA`, `ADMIN_GENERAL`)
| Qué hace el Operador | Workflows (Escenarios) subyacentes | Punto de entrada |
| :--- | :--- | :--- |
| **Admin general**: Da de alta a un gerente médico | Esc. 31 (`Registrar un gerente médico`) | `/admin/gerentes-medicos/nuevo` |
| **Administrativo**: Se registra, emite presupuestos y registra autorizaciones/rechazos de obra social | Esc. 22 (`Registrar un administrativo`), Esc. 03 (`Emitir un presupuesto`), Esc. 04 (`Autorizar un estudio por obra social`), Esc. 05 (`Reautorizar un estudio rechazado`) | `/registro/administrativo`, `/administracion/estudios` |
| **Administrativo**: Controla muestras en laboratorio central, programa retiro de FedEx y carga datos crudos de Corea | Esc. 10 (`Remuestrear un estudio`), Esc. 12 (`Formar un sample-set de muestras`), Esc. 13 (`Enviar un sample-set de muestras a Corea`), Esc. 14 (`Enviar una muestra de Pompe urgente`), Esc. 15 (`Analizar un estudio mediante bioinformática`) | `/administracion/muestras`, `/administracion/sample-sets` |
| **Transportista**: Recorre su orden del día provincial, marca recogidas, reporta GPS y entrega en laboratorio central | Esc. 11 (`Transportar muestras al laboratorio central`), Esc. 32 (`Seguir una muestra en el mapa`) | `/transporte/orden-del-dia` |
| **Bioinformático**: Toma un estudio priorizando Pompe urgente, consulta variantes por gen y carga el resultado | Esc. 15 (`Analizar un estudio mediante bioinformática`), Esc. 24 (`Consultar variantes`), Esc. 16 (`Informar el resultado de un estudio`) | `/bioinformatica/cola` |

### 3.4. Recorridos Sistema-a-Sistema (Automatizados)
| Qué ocurre automáticamente | Workflows (Escenarios) subyacentes | Disparador (Trigger) |
| :--- | :--- | :--- |
| Centro de extracción notifica toma de muestra por Telegram | Esc. 09 (`Registrar la toma de una muestra`) | Webhook de `Bot de Telegram` |
| Generación matutina de la orden del día por provincia (lunes a viernes hábiles) | Esc. 11 (`Transportar muestras al laboratorio central`) | Cron matutino + `API de optimización de recorridos` |
| Cierre automático de `SampleSet` (10 muestras o Pompe urgente) y autorización ministerial | Esc. 12 (`Formar un sample-set`), Esc. 13 (`Enviar sample-set a Corea`), Esc. 14 (`Enviar muestra de Pompe urgente`) | Llegada de muestra válida al laboratorio central + `API del Ministerio de Salud` |
| Retiro efectivo de paquete por FedEx en la fecha/hora programada | Esc. 13 y Esc. 14 | Webhook callback de `FedEx` |
| Detección de inasistencia al turno y penalidad a la 5.ª ausencia | Esc. 33 (`Ausentarse a un turno de extracción`) | Job de cierre de turnos vencidos |

---

## View 4: By State (Mapa de los 14 Estados del Estudio en el LEL)

| # | Estado en LEL (`EstadoEstudio`) | Ingresa desde (Entered by) | Sale hacia (Exited by) | Workflows (Escenarios) que disparan la transición |
| :-: | :--- | :--- | :--- | :--- |
| 1 | **Creado** | *(Alta inicial)* o desde `Turno sacado` (5.ª ausencia) | `-> Pendiente de autorización`, `-> Turno sacado` (previo pago particular) | Esc. 02 (creación), Esc. 33 (vuelta a `Creado` por 5 ausencias), Esc. 04 (solicita OS), Esc. 06 + Esc. 07 (paga particular y saca turno). |
| 2 | **Pendiente de autorización** | `Creado` (elige obra social) o `Rechazado` (carga demanda judicial) | `-> Autorizado`, `-> Rechazado` | Esc. 04 (solicitud inicial y resolución de OS), Esc. 05 (reautorización con demanda PDF). |
| 3 | **Autorizado** | `Pendiente de autorización` (aprobación de obra social) | `-> Turno sacado` (o `-> En análisis por bioinformática` en reanálisis) | Esc. 04, Esc. 05, Esc. 07, Esc. 17. |
| 4 | **Rechazado** | `Pendiente de autorización` (rechazo de obra social) | `-> Pendiente de autorización` (carga demanda) o pago particular | Esc. 04 (rechazo), Esc. 05 (presentación de demanda judicial). |
| 5 | **Turno sacado** | `Creado` (pagado), `Autorizado`, `Remuestreo requerido`, `Turno sacado` (re-reserva tras cancelar o faltar 1..4 veces) | `-> Lista para retirar`, `-> Creado` (5.ª ausencia), `-> Turno sacado` (cancelación/ausencia 1..4) | Esc. 07, Esc. 08, Esc. 09, Esc. 10, Esc. 33. |
| 6 | **Lista para retirar** | `Turno sacado` (mensaje al `Bot de Telegram`) | `-> En camino al laboratorio central` | Esc. 09 (ingreso), Esc. 11 y Esc. 32 (recogida por transportista). |
| 7 | **En camino al laboratorio central** | `Lista para retirar` (transportista marca recogida) | `-> En laboratorio central` | Esc. 11 y Esc. 32. |
| 8 | **En laboratorio central** | `En camino al laboratorio central` (transportista marca llegada) | `-> En espera de retiro`, `-> Remuestreo requerido` ($< 2\text{ ml}$ o muestra degradada) | Esc. 11 (ingreso), Esc. 10 (descarte), Esc. 12, 13 y 14 (cierre de `SampleSet`). |
| 9 | **Remuestreo requerido** | `En laboratorio central` o `En viaje a Corea` (menos de 2 ml o ADN insuficiente/desnaturalizado) | `-> Turno sacado` (sin nuevo pago) | Esc. 10 (ingreso y nuevo turno) + Esc. 07. |
| 10 | **En espera de retiro** | `En laboratorio central` (cierre de `SampleSet` por 10 muestras o **Pompe urgente** + CSV/PDF Ministerio) | `-> En viaje a Corea` | Esc. 12, Esc. 13, Esc. 14. |
| 11 | **En viaje a Corea** | `En espera de retiro` (retiro de **FedEx** en hora programada) | `-> En análisis por bioinformática`, `-> Remuestreo requerido` | Esc. 13, Esc. 14, Esc. 15 (carga de datos crudos), Esc. 10. |
| 12 | **En análisis por bioinformática** | `En viaje a Corea` (administrativo carga **datos crudos**) o solicitud de **reanálisis** | `-> En análisis de un bioinformático` | Esc. 15, Esc. 17. |
| 13 | **En análisis de un bioinformático** | `En análisis por bioinformática` (bioinformático toma el estudio) | `-> Resultado cargado` | Esc. 15, Esc. 24, Esc. 16. |
| 14 | **Resultado cargado** | `En análisis de un bioinformático` (bioinformático carga las variantes y cierra el análisis) | *(Estado terminal del análisis; admite posterior `Reanalizar estudio` en Esc. 17)* | Esc. 15, Esc. 16, Esc. 37, Esc. 17. |

---

## Discovery Audit Summary

- [x] **Data Layer Scanned**: Se auditaron los 10 módulos de modelos SQLAlchemy en `app/src/core/models/` (39 tablas y 10 enumeraciones).
- [x] **LEL Compliance Scanned**: Se verificaron los 7 Sujetos, 38 Objetos, 17 Verbos y 14 Estados de `.ai/2-Glosario_LEL.md` contra los 37 escenarios de `.ai/3-Escenarios.md`.
- [x] **Implicit Workflows Identified & Documented**:
  1. **Generación automática de la Orden del día** (cubierta en `escenario-11-transportar-muestras-al-laboratorio-central.md`).
  2. **Cierre automático de SampleSet y solicitud de Autorización del Ministerio sin intervención administrativa** (cubierta en `escenario-12`, `escenario-13` y `escenario-14`).
  3. **Callback asíncrono de FedEx en el horario de retiro programado** (cubierto en `escenario-13` y `escenario-14`).
  4. **Priorización de cola de bioinformática para Pompe urgente** (cubierta en `escenario-14` y `escenario-15`).

