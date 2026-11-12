# Imagen de desarrollo de la API (spec 001, T7).
#
# Las dependencias se instalan con uv desde pyproject.toml y uv.lock (--frozen:
# falla si el lock no coincide). El entorno virtual vive en /opt/venv, fuera de
# /app, para que el montaje del código en docker-compose.yml no lo tape.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Primero solo los archivos de dependencias: la capa se reutiliza mientras no cambien.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .

RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 5000

# Servidor de desarrollo con recarga; sin el depurador interactivo de Werkzeug.
CMD ["flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5000", "--reload", "--no-debugger"]
