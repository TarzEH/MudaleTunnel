# MudaleTunnel — single image serving both the web tier and the engine daemon.
#
# The same image runs two different processes (see docker-compose.yml): daphne
# for the API and dashboard, and `manage.py enginectl` for the supervisor. They
# are separate containers because the engine owns long-lived subprocesses and
# must not be recycled when the web tier is redeployed.

# ── Stage 1: build the dashboard ────────────────────────────────────────

FROM node:22-alpine AS frontend

WORKDIR /build

# Copy manifests first so `npm ci` is cached until dependencies actually change.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ── Stage 2: python dependencies ────────────────────────────────────────

FROM python:3.12-slim AS python-deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY backend/pyproject.toml ./
# Resolve into a self-contained venv that the runtime stage copies wholesale,
# so no build tooling ends up in the final image.
RUN uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python -r pyproject.toml


# ── Stage 3: runtime ────────────────────────────────────────────────────

FROM python:3.12-slim AS runtime

# openssh-client  — the ssh adapter's binary
# nmap            — the scan adapter's binary
# proxychains4    — routes a scan through a pivot's SOCKS proxy, so a scan
#                   labelled "through the tunnel" genuinely travels through it
# iproute2        — route management for tunnel interfaces
# tini            — a real PID 1, so SIGTERM reaches the daemon and it can stop
#                   its supervised children cleanly instead of being SIGKILLed
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      openssh-client \
      nmap \
      proxychains4 \
      iproute2 \
      tini \
      curl \
 && rm -rf /var/lib/apt/lists/*

# Runs unprivileged. v2's image ran everything as root, which combined with an
# unauthenticated endpoint and an injectable nmap target meant root-level
# filesystem access from the network.
RUN groupadd --gid 10001 mudale \
 && useradd --uid 10001 --gid mudale --create-home --shell /usr/sbin/nologin mudale

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=mudale.settings.prod \
    MUDALE_FRONTEND_DIST=/app/frontend_dist

WORKDIR /app

COPY --from=python-deps /opt/venv /opt/venv
COPY --chown=mudale:mudale backend/ /app/
COPY --from=frontend --chown=mudale:mudale /build/dist /app/frontend_dist

RUN mkdir -p /app/var/logs /app/staticfiles \
 && chown -R mudale:mudale /app/var /app/staticfiles

USER mudale

# Collect the SPA and Django's own assets into STATIC_ROOT for WhiteNoise.
# Needs a SECRET_KEY to import settings, but nothing here touches the database,
# so a throwaway value is correct — it is not baked into the running app.
RUN MUDALE_SECRET_KEY=build-time-only \
    MUDALE_ALLOWED_HOSTS=localhost \
    MUDALE_DB_PASSWORD=build-time-only \
    python manage.py collectstatic --noinput --clear

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health/ || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "mudale.asgi:application"]
