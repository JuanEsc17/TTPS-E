# Proyecto: Sistema de Seguimiento de Estudios de Exoma Clínico (TTPS-E)

## Stack Tecnológico
- **Lenguaje y Gestor:** Python >= 3.14, Poetry (`pyproject.toml`)
- **Backend:** Flask, SQLAlchemy + Alembic/Flask-Migrate
- **Frontend** React
- **Base de Datos:** PostgreSQL
- **Clientes HTTP (APIs externas):** `httpx` / `requests`

## Comandos
- Ejecutar app: `poetry run flask run`
- Ejecutar tests: `poetry run pytest` 
- Linter: `poetry run ruff check .`

## Estructura del Proyecto
- `.ai/`         Requerimientos base: `1-Entrevista.md`, `2-Glosario_LEL.md`, `3-Escenarios.md`, `Prototipo.pdf`
- `docs/specs/`  Especificaciones técnicas SDD (modelo de datos, contratos API, specs por escenario)
- `app/`         Código fuente en capas estrictas (`router` → `service` → `repo` + `clients` para APIs externas)
- `tests/`       Tests con `pytest` (al menos un test por criterio de aceptación de la spec)

## Flujo Spec-Driven Development (SDD)
1. Antes de implementar cualquier funcionalidad en `app/`, debe existir su especificación en `docs/specs/` basada en `.ai/3-Escenarios.md`.
2. Usar estrictamente el vocabulario, sujetos, objetos y los 14 estados de estudio definidos en `.ai/2-Glosario_LEL.md`.

## Reglas Estrictas (NO hacer)
- No agregar dependencias a `pyproject.toml` sin preguntar primero.
- No alterar migraciones de base de datos ya aplicadas.
- No poner lógica de negocio en `router` ni consultas SQL/ORM directas fuera de `repo`.
- Todos los nombres de dominio (modelos, estados, servicios, variables de negocio) deben estar en **español**.