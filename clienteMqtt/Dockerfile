# ========================
# Etapa 1: Builder (instalación de dependencias)
# ========================
FROM python:3.11-slim AS builder

WORKDIR /app

# Instalar uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copiar requirements.txt y el código fuente
COPY requirements.txt ./
COPY . .

# Instalar las dependencias en un directorio específico (--target)
# Esto evita crear un entorno virtual y sus enlaces simbólicos.
RUN uv pip install \
    --target /app/deps \
    --no-cache-dir \
    -r requirements.txt

# ========================
# Etapa 2: Runtime (Distroless)
# ========================
FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app

# Copiar las dependencias instaladas (solo los paquetes)
COPY --from=builder /app/deps /app/deps

# Copiar el código de la aplicación
COPY --from=builder /app /app

# Configurar Python para que encuentre los paquetes en /app/deps
ENV PYTHONPATH="/app/deps"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ="America/Argentina/Buenos_Aires"

# El intérprete de Python es el propio de Distroless (sin necesidad de venv)
ENTRYPOINT []
CMD ["python", "/app/clienteMqtt.py"]