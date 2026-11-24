FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    TZ=America/Argentina/Buenos_Aires

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "poetry>=2.0,<3.0"

WORKDIR /app

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root --no-ansi

COPY app ./app
COPY main.py ./
COPY scripts ./scripts

RUN poetry install --only main --no-ansi
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/app/storage /app/storage \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 10000

CMD ["sh", "-c", "if [ \"${SKIP_INIT_DB:-0}\" != \"1\" ]; then flask --app main init-db; fi && exec gunicorn -w ${WEB_CONCURRENCY:-2} --timeout ${GUNICORN_TIMEOUT:-120} --bind 0.0.0.0:${PORT:-10000} main:app"]
