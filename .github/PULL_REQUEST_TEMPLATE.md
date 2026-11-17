## Issue vinculado

<!-- Indicá el número del issue correspondiente. Usá "Closes #NUM" o "Fixes #NUM" para cerrarlo automáticamente al hacer merge, o "Relates to #NUM" si es un avance parcial. -->
Closes #

## Descripción de los cambios

<!-- Resumí brevemente qué se implementó o corrigió y por qué. -->

## Escenario / Spec relacionada

<!-- Ej.: docs/specs/escenario-01-dar-de-alta-un-paciente.md (o "N/A" si no aplica). -->
- Spec: 

## Tipo de cambio

- [ ] `bug`: Corrección de error
- [ ] `enhancement`: Nueva funcionalidad o mejora
- [ ] `refactor`: Refactorización sin cambio de comportamiento funcional
- [ ] `docs`: Cambios en documentación o especificaciones (`docs/specs/`)

## Checklist de calidad y reglas del proyecto

- [ ] Se vinculó el issue correspondiente en la sección superior.
- [ ] Se respetó el flujo SDD (`docs/specs/` y vocabulario oficial en `.ai/2-Glosario_LEL.md`).
- [ ] Todos los nombres de dominio (modelos, estados, servicios, variables) están en español.
- [ ] El backend respeta la separación en capas (`router` → `service` → `repo` + `clients`).
- [ ] No se modificaron migraciones de base de datos ya aplicadas ni se agregaron dependencias a `pyproject.toml` sin acuerdo previo.
- [ ] Tests backend ejecutados y pasando (`poetry run pytest`).
- [ ] Linter backend sin errores (`poetry run ruff check .`).
- [ ] Frontend verificado (`npm run lint` y `npm run build` en `frontend/`, si aplica).
