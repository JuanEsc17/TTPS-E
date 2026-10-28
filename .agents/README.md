# Guía de Uso de Skills — Proyecto TTPS-E (Exoma Clínico)

Este documento describe **cuándo y cómo utilizar cada una de las 14 skills** instaladas en `.agents/skills/` (provenientes de [`msitarzewski/agency-agents`](https://github.com/msitarzewski/agency-agents)), adaptadas al flujo **Spec-Driven Development (SDD)**, las reglas de [`AGENTS.md`](../AGENTS.md), el vocabulario de [`.ai/2-Glosario_LEL.md`](../.ai/2-Glosario_LEL.md) y los 37 escenarios de [`.ai/3-Escenarios.md`](../.ai/3-Escenarios.md).

---

## 1. ¿En qué orden usarlas según el flujo SDD del proyecto?

Para cada historia o escenario que vayas a desarrollar, seguí este orden:

```
1. Especificar (docs/specs/)  ──► agency-workflow-architect + agency-software-architect
2. Modelar DB y Permisos      ──► agency-database-optimizer + agency-identity-access-engineer
3. Implementar Backend (app/) ──► agency-backend-architect (+ skills de PDF / Audio / Privacidad)
4. Implementar Frontend       ──► agency-frontend-developer (+ agency-web-gis-developer para mapas)
5. Testear y Revisar (tests/) ──► agency-api-tester + agency-appsec-engineer + agency-code-reviewer
```

---

## 2. Detalle de cada Skill: Cuándo conviene usarla

### A. Arquitectura y Especificación (Fase SDD)

#### 1. `agency-workflow-architect`
- **Ubicación:** [`.agents/skills/agency-workflow-architect/SKILL.md`](./skills/agency-workflow-architect/SKILL.md)
- **Cuándo conviene usarla:**
  - **Antes de escribir código**, cuando necesites redactar una especificación en `docs/specs/` a partir de [`.ai/3-Escenarios.md`](../.ai/3-Escenarios.md).
  - Cuando debas definir transiciones entre los **14 estados del Estudio**, condiciones de guarda, casos de error y qué ocurre si falla una API externa.
  - Para modelar flujos con bifurcaciones complejas: rechazo de obra social y demanda judicial, límite de 5 ausencias a turnos, remuestreo sin cargo, cierre anticipado de *sample set* por **Pompe urgente** o reanálisis de exoma.
- **Cuándo NO hace falta:** Cuando la spec ya está escrita y aprobada, y solo estás programando un endpoint puntual.
- **Ejemplo de prompt:**
  > *"Usá `agency-workflow-architect` para armar en `docs/specs/` la especificación completa de la máquina de estados del Estudio y los Escenarios 11, 12, 13 y 14 (armado de sample set y Pompe urgente) respetando el LEL."*

#### 2. `agency-software-architect`
- **Ubicación:** [`.agents/skills/agency-software-architect/SKILL.md`](./skills/agency-software-architect/SKILL.md)
- **Cuándo conviene usarla:**
  - Al definir la estructura de módulos y paquetes dentro de `app/` respetando la arquitectura en capas estrictas (`router` → `service` → `repo` + `clients`).
  - Para mapear los **Sujetos, Objetos y Verbos** de [`.ai/2-Glosario_LEL.md`](../.ai/2-Glosario_LEL.md) a entidades de dominio, DTOs/esquemas y servicios con nombres 100 % en español.
  - Cuando tengas dudas de diseño sobre dónde ubicar una regla de negocio o cómo desacoplar los clientes de las 8 APIs externas.
- **Ejemplo de prompt:**
  > *"Usá `agency-software-architect` para diseñar las capas `router`, `service`, `repo` y `clients` del módulo de estudios y presupuestos sin acoplar el ORM a los servicios."*

---

### B. Desarrollo Backend, Base de Datos y Frontend

#### 3. `agency-backend-architect`
- **Ubicación:** [`.agents/skills/agency-backend-architect/SKILL.md`](./skills/agency-backend-architect/SKILL.md)
- **Cuándo conviene usarla:**
  - Al implementar endpoints en Flask, validaciones con Marshmallow, servicios de negocio y repositorios SQLAlchemy en `app/`.
  - Al construir los clientes HTTP (`httpx` / `requests`) en `app/clients/` para comunicarse con las APIs externas: **API de bioinformática**, **SNOMED**, **API de familiograma**, **API de obras sociales**, **API de cupones**, **API del Ministerio de Salud**, **API de optimización de recorridos**, **FedEx** y **Chatbot**.
  - Al diseñar el webhook/receptor del **Bot de Telegram** (Escenario 9) y el callback de retiro de **FedEx** (Escenario 13).
- **Ejemplo de prompt:**
  > *"Usá `agency-backend-architect` para implementar el servicio y cliente HTTP de la API de cupones (Escenarios 29 y 30) manejando timeouts y errores de red."*

#### 4. `agency-database-optimizer`
- **Ubicación:** [`.agents/skills/agency-database-optimizer/SKILL.md`](./skills/agency-database-optimizer/SKILL.md)
- **Cuándo conviene usarla:**
  - Al diseñar el modelo de datos relacional en PostgreSQL y crear nuevas migraciones con Alembic / Flask-Migrate (recordando la regla de **no alterar migraciones ya aplicadas**).
  - Al definir claves foráneas, restricciones `UNIQUE` / `CHECK` (por ejemplo, validar que un *sample set* tenga máximo 10 muestras o que un turno sea único por centro y bloque de 15 minutos) e índices.
  - Para optimizar consultas de historial de estudios, búsqueda de síntomas SNOMED y registros financieros para el futuro tablero de control.
- **Ejemplo de prompt:**
  > *"Usá `agency-database-optimizer` para diseñar las tablas de `estudio`, `muestra`, `sample_set` y `turno` en SQLAlchemy/PostgreSQL con sus índices y constraints."*

#### 5. `agency-frontend-developer`
- **Ubicación:** [`.agents/skills/agency-frontend-developer/SKILL.md`](./skills/agency-frontend-developer/SKILL.md)
- **Cuándo conviene usarla:**
  - Al construir las vistas y componentes en **React** para cada uno de los 7 roles del sistema.
  - Para garantizar que la interfaz sea **responsiva** (escritorio para médicos, administrativos y bioinformáticos; celular para pacientes y transportistas).
  - Al implementar formularios dinámicos complejos: autocompletado de síntomas SNOMED al tipear 3 letras (Escenario 36), carga dinámica de familiares para el familiograma (Escenarios 18 y 19), selector de genes y variantes (Escenarios 2 y 15) y bandeja de **Avisos** internos.
- **Ejemplo de prompt:**
  > *"Usá `agency-frontend-developer` para crear en React el formulario de alta de paciente (Escenarios 1, 18, 19 y 36) con buscador asíncrono de síntomas SNOMED."*

---

### C. Seguridad, Identidad y Privacidad Clínica

#### 6. `agency-identity-access-engineer`
- **Ubicación:** [`.agents/skills/agency-identity-access-engineer/SKILL.md`](./skills/agency-identity-access-engineer/SKILL.md)
- **Cuándo conviene usarla:**
  - Al diseñar e implementar la autenticación y manejo de sesiones (Escenarios 27, 28 y 34).
  - Al implementar el flujo de **cambio obligatorio de contraseña inicial** en el primer ingreso del paciente (Escenario 20).
  - Al implementar la **verificación de segundo factor por correo electrónico (`Código de verificación`)** cuando un usuario inicia sesión desde un dispositivo o IP no reconocida (Escenario 26).
  - Al definir la matriz de autorización por roles (**RBAC**) para los 7 sujetos: `Admin general`, `Gerente médico`, `Médico`, `Administrativo`, `Bioinformático`, `Transportista` y `Paciente`.
- **Ejemplo de prompt:**
  > *"Usá `agency-identity-access-engineer` para especificar e implementar los Escenarios 20, 26, 27 y 28 (login, detección de máquina nueva con código por mail y cambio de contraseña inicial)."*

#### 7. `agency-privacy-engineer`
- **Ubicación:** [`.agents/skills/agency-privacy-engineer/SKILL.md`](./skills/agency-privacy-engineer/SKILL.md)
- **Cuándo conviene usarla:**
  - Al manipular datos altamente sensibles: secuencias de **datos crudos** (ACTG), **variantes** patogénicas/VUS, **historia clínica**, **diagnóstico presuntivo** y **familiograma**.
  - Para asegurar que un paciente o médico solo pueda acceder a los estudios que le corresponden y que los logs del servidor o respuestas de error nunca filtren información genética ni PII.
- **Ejemplo de prompt:**
  > *"Usá `agency-privacy-engineer` para revisar que los endpoints de estudios, datos crudos y resultados en PDF no expongan datos genéticos entre distintos pacientes o roles no autorizados."*

#### 8. `agency-appsec-engineer`
- **Ubicación:** [`.agents/skills/agency-appsec-engineer/SKILL.md`](./skills/agency-appsec-engineer/SKILL.md)
- **Cuándo conviene usarla:**
  - Al implementar subida y descarga de archivos: PDF de fallo judicial en una **Demanda** (Escenario 5), PDF con QR de **Cupón** (Escenario 30), archivo de **Datos crudos** (Escenario 15) y descarga de **Resultado** (Escenario 37).
  - Para asegurar endpoints públicos o callbacks externos como el webhook de **FedEx** y las notificaciones del **Bot de Telegram**.
- **Ejemplo de prompt:**
  > *"Usá `agency-appsec-engineer` para validar de forma segura la subida del PDF de decisión judicial (Escenario 5) y proteger el webhook de retiro de FedEx (Escenario 13)."*

---

### D. Funcionalidades Especializadas del Dominio

#### 9. `agency-web-gis-developer`
- **Ubicación:** [`.agents/skills/agency-web-gis-developer/SKILL.md`](./skills/agency-web-gis-developer/SKILL.md)
- **Cuándo conviene usarla:**
  - **Mapa de Centros de Extracción (Escenario 7):** Para mostrar en un mapa interactivo los 100 centros de extracción distribuidos en el país y permitir que el paciente elija el más cercano y vea sus turnos libres.
  - **Recorrido del Transportista (Escenario 11):** Para visualizar la **Orden del día** ordenada por provincia según la **API de optimización de recorridos**.
  - **Mapa de Seguimiento en vivo (Escenario 32):** Para mostrar por dónde viaja la muestra del paciente rumbo al laboratorio central.
- **Ejemplo de prompt:**
  > *"Usá `agency-web-gis-developer` para diseñar el componente de mapa interactivo de centros de extracción (Escenario 7) y el mapa de seguimiento de muestras (Escenario 32)."*

#### 10. `agency-document-generator`
- **Ubicación:** [`.agents/skills/agency-document-generator/SKILL.md`](./skills/agency-document-generator/SKILL.md)
- **Cuándo conviene usarla:**
  - Para generar el archivo **CSV** automático con la nómina de pacientes del *sample set* que se envía a la **API del Ministerio de Salud** (Escenario 13).
  - Para estructurar la creación programática de reportes y documentos descargables del sistema.
- **Ejemplo de prompt:**
  > *"Usá `agency-document-generator` para implementar la generación automática del CSV del sample set y su envío a la API del Ministerio de Salud (Escenario 13)."*

#### 11. `agency-pdf-engine-architect`
- **Ubicación:** [`.agents/skills/agency-pdf-engine-architect/SKILL.md`](./skills/agency-pdf-engine-architect/SKILL.md)
- **Cuándo conviene usarla:**
  - Cuando necesites compilar plantillas con formato clínico prolijo y determinista a **PDF**:
    - El **Resultado** del exoma clínico con positividad/negatividad y variantes detectadas (Escenarios 16 y 37).
    - La **Orden de extracción** y el **Consentimiento informado** que se envían al paciente al sacar turno (Escenario 7).
- **Ejemplo de prompt:**
  > *"Usá `agency-pdf-engine-architect` para armar la plantilla y generación del PDF de Resultado del estudio (Escenarios 16 y 37) y de la Orden de extracción."*

#### 12. `agency-voice-ai-integration-engineer`
- **Ubicación:** [`.agents/skills/agency-voice-ai-integration-engineer/SKILL.md`](./skills/agency-voice-ai-integration-engineer/SKILL.md)
- **Cuándo conviene usarla:**
  - Exclusivamente para el **Escenario 35 (Grabar la historia clínica)**: captura de audio desde el navegador del médico tratante, envío al **Transcriptor de audio** y limpieza/inserción del texto resultante en el resumen de la historia clínica del paciente.
- **Ejemplo de prompt:**
  > *"Usá `agency-voice-ai-integration-engineer` para diseñar e implementar la grabación de voz en el frontend y la integración con el transcriptor de audio en el backend (Escenario 35)."*

---

### E. Testing y Calidad de Código

#### 13. `agency-api-tester`
- **Ubicación:** [`.agents/skills/agency-api-tester/SKILL.md`](./skills/agency-api-tester/SKILL.md)
- **Cuándo conviene usarla:**
  - Al escribir los tests en `tests/` con `poetry run pytest`, asegurando **al menos un test por criterio de aceptación de la spec**.
  - Para crear mocks de las APIs externas (`httpx`/`requests`) y probar respuestas exitosas, errores de validación (ej. síntomas que no cumplen 1 síntoma cardinal o 2 secundarios en Escenario 36) y transiciones inválidas de estado.
- **Ejemplo de prompt:**
  > *"Usá `agency-api-tester` para generar los tests en `pytest` de todos los criterios de aceptación de la spec de alta de paciente y validación de síntomas SNOMED."*

#### 14. `agency-code-reviewer`
- **Ubicación:** [`.agents/skills/agency-code-reviewer/SKILL.md`](./skills/agency-code-reviewer/SKILL.md)
- **Cuándo conviene usarla:**
  - Antes de abrir un Pull Request o dar por terminada una funcionalidad.
  - Para verificar el cumplimiento estricto de [`AGENTS.md`](../AGENTS.md):
    1. Sin lógica de negocio en `router`.
    2. Sin consultas SQL/ORM fuera de `repo`.
    3. Todos los nombres de dominio en **español** y fieles a [`.ai/2-Glosario_LEL.md`](../.ai/2-Glosario_LEL.md).
    4. Migraciones previas intactas y código limpio para `poetry run ruff check .`.
- **Ejemplo de prompt:**
  > *"Usá `agency-code-reviewer` para auditar mis cambios en `app/` y `tests/` contra las reglas estrictas de `AGENTS.md` y el Glosario LEL."*

---

## 3. Mapa Rápido: ¿Qué Skills usar según el Escenario (`.ai/3-Escenarios.md`)?

| Escenarios | Tema | Skills recomendadas |
| :--- | :--- | :--- |
| **1, 18, 19, 36** | Alta de paciente, síntomas SNOMED y familiograma | `agency-workflow-architect` → `agency-backend-architect` + `agency-frontend-developer` + `agency-privacy-engineer` |
| **35** | Grabar historia clínica por voz | `agency-voice-ai-integration-engineer` + `agency-frontend-developer` |
| **2, 17, 23** | Alta de estudio, reanálisis y gestión de patologías | `agency-workflow-architect` + `agency-backend-architect` + `agency-database-optimizer` |
| **3, 4, 5, 6, 29, 30** | Presupuesto, obra social, demanda judicial, pago y cupones | `agency-workflow-architect` + `agency-backend-architect` + `agency-appsec-engineer` |
| **7, 8, 33** | Solicitar/cancelar turno, mapa de centros y límite de 5 ausencias | `agency-web-gis-developer` + `agency-backend-architect` + `agency-pdf-engine-architect` |
| **9, 10** | Toma de muestra (Bot de Telegram) y remuestreo (< 2 ml o ADN insuficiente) | `agency-backend-architect` + `agency-workflow-architect` + `agency-appsec-engineer` |
| **11, 32** | Transporte de muestras, orden del día y seguimiento en mapa | `agency-web-gis-developer` + `agency-backend-architect` + `agency-frontend-developer` |
| **12, 13, 14** | Armado de *sample set* (lote de 10), CSV Ministerio, FedEx y **Pompe urgente** | `agency-workflow-architect` + `agency-document-generator` + `agency-backend-architect` |
| **15, 16, 24, 37** | Análisis bioinformático, variantes/VUS y descarga de resultado PDF | `agency-backend-architect` + `agency-pdf-engine-architect` + `agency-privacy-engineer` |
| **20, 21, 22, 26, 27, 28, 31, 34** | Registro de usuarios, login, cierre de sesión, 2FA máquina nueva y contraseñas | `agency-identity-access-engineer` + `agency-appsec-engineer` + `agency-backend-architect` |
| **25** | Consulta de pacientes al Chatbot sobre las 5 patologías | `agency-backend-architect` + `agency-frontend-developer` |

