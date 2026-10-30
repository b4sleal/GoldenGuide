# One Dockerfile builds every Python image: backend, provision, and both embedding services.
#
#   python       shared settings for every image: env vars, non-root `app` user, model cache dirs
#   toolchain    python + compilers and uv, everything needed to install dependencies
#   development  toolchain as `app`; deps sync at container start (docker-compose.dev.yml)
#   builder      toolchain that installs one dependency group and the project into /venv
#   runtime      python + the finished /venv; no compilers, no uv (docker-compose.yml)
#
# The DEPENDENCY_GROUP build arg picks the pyproject.toml group: backend, embedding-gpu, embedding-cpu.

FROM python:3.14-slim AS python
# Unbuffered output: log lines reach `docker logs`/Alloy immediately.
# No .pyc files: the bind-mounted source tree stays clean in development.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH" \
    CONFIG_PATH=/app/configs \
    HF_HOME=/models/huggingface \
    FASTEMBED_CACHE_PATH=/models/fastembed
WORKDIR /app
# Named volumes inherit these owners when first created, so services never run as root.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /models/huggingface /models/fastembed \
    && chown -R app:app /app /models

FROM python AS toolchain
ENV UV_PROJECT_ENVIRONMENT=/venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
# Compilers for packages without prebuilt wheels; curl for container health checks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
# uv pinned to the version that wrote uv.lock (uv's documented Docker install method).
COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/
RUN mkdir -p /venv /home/app/.cache/uv \
    && chown -R app:app /venv /home/app/.cache
COPY --chmod=755 docker/start-python-service.sh /usr/local/bin/start-python-service.sh

FROM toolchain AS development
# The uv cache and the venv share one volume at ~/.cache (docker-compose.dev.yml), so uv can
# hardlink packages from the cache instead of storing a second copy in the venv.
ENV UV_PROJECT_ENVIRONMENT=/home/app/.cache/venv \
    UV_LINK_MODE=hardlink \
    PATH="/home/app/.cache/venv/bin:$PATH"
USER app

FROM toolchain AS builder
ARG DEPENDENCY_GROUP=backend
ENV UV_CONCURRENT_DOWNLOADS=2 UV_CONCURRENT_INSTALLS=1 UV_CONCURRENT_BUILDS=1
# Dependencies first, so code changes reuse this cached layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --group ${DEPENDENCY_GROUP} --no-install-project
COPY src/goldenguide_common ./src/goldenguide_common
COPY src/backend ./src/backend
COPY src/embedding_service ./src/embedding_service
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --group ${DEPENDENCY_GROUP} --no-editable

FROM python AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /venv /venv
COPY configs ./configs
USER app
