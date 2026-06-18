FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY app ./app

# Commit deployado, injetado no build via:
#   fly deploy --build-arg GIT_SHA=$(git rev-parse HEAD)
# e exposto em /version.json para o painel-projetos confirmar o que está no ar.
ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA

# The persistent volume is mounted here on Fly.io (see fly.toml).
ENV DATA_DIR=/data
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
