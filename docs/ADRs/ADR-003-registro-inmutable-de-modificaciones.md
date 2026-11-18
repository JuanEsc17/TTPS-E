# ADR-003: Registro Inmutable de Modificaciones sobre Sample Sets, Pacientes y Estudios

## Status
Accepted (2026-11-17)

## Context
El sistema requiere un registro completo de todas las modificaciones realizadas sobre tres entidades críticas: **`sample_sets`**, **`pacientes`** y **`estudios`**. Muchas mutaciones ocurren por acciones de usuarios autenticados (`Médico`, `Paciente`, `Administrativo`, `Bioinformático`, `Transportista`), pero otras ocurren mediante webhooks (`Bot de Telegram`, `FedEx`, `MercadoPago`) o procesos automáticos del sistema (cierre de `SampleSet` al llegar 10 muestras, cierre de turnos con 5ta ausencia).

Se evaluaron dos enfoques:
- **Opción A (Triggers SQL en PostgreSQL):** Capturan cualquier `INSERT`/`UPDATE`, pero carecen del contexto de negocio (no saben qué `usuario_id` ejecutó la acción ni el `motivo` ni el `origen` cuando la aplicación usa una única conexión de pool a PostgreSQL, y no funcionan de forma homogénea en SQLite durante tests unitarios).
- **Opción B (Registro transaccional en capa `service` / `repo` con tabla `registro_modificaciones`):** Un `AuditoriaService` invocado dentro de la misma transacción SQLAlchemy que muta `SampleSet`, `Paciente` o `Estudio`, persistiendo en una tabla append-only (`registro_modificaciones`) el diff estructurado en JSON (`cambios: {campo: {anterior, nuevo}}`), `accion`, `usuario_id`, `origen`, `motivo`, `ip_origen` y `fecha`.

## Decision
Se adopta la **Opción B**: tabla append-only `registro_modificaciones` alimentada dentro de la misma transacción de base de datos por `AuditoriaService` (complementada opcionalmente con un validador/hook `before_flush` de SQLAlchemy en entorno de testing/desarrollo para detectar cualquier mutación directa sobre `SampleSet`, `Paciente` o `Estudio` que omita registrar auditoría).

## Consequences
- **Positivas:** Garantiza atomicidad estricta (si la operación falla y hace `rollback()`, no queda auditoría falsa; si hace `commit()`, el registro queda garantizado); captura intención de negocio (`motivo`), actor real (`usuario_id` o `origen` automático) y funciona de forma idéntica en PostgreSQL (producción) y SQLite (tests `pytest`).
- **Negativas / Trade-offs:** Todo servicio que cree o modifique `SampleSet`, `Paciente` o `Estudio` debe invocar a `AuditoriaService.registrar_modificacion(...)` en la misma unidad de trabajo.
- **Restricciones:** Prohibido exponer operaciones `PUT`/`PATCH`/`DELETE` sobre `registro_modificaciones` (inmutabilidad estricta).
