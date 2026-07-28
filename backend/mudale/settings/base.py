"""Base Django settings for MudaleTunnel.

Environment-specific modules (dev/prod/test) import * from here and override.
Nothing secret lives in this file — everything sensitive comes from the environment.
"""

import os
from pathlib import Path

from mudale.settings.env import env_bool, env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── Core ────────────────────────────────────────────────────────────────

SECRET_KEY = env_str("MUDALE_SECRET_KEY", required=True)
DEBUG = False
ALLOWED_HOSTS = env_list("MUDALE_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

ROOT_URLCONF = "mudale.urls"
ASGI_APPLICATION = "mudale.asgi.application"
WSGI_APPLICATION = "mudale.wsgi.application"

AUTH_USER_MODEL = "accounts.Operator"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Applications ────────────────────────────────────────────────────────

DJANGO_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "channels",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.engagements",
    "apps.agents",
    "apps.tunnels",
    "apps.scans",
    "apps.audit",
    "apps.engine",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Directly after SecurityMiddleware, as WhiteNoise requires. Serves
    # everything under STATIC_URL from STATIC_ROOT, including the compiled SPA.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.AuditContextMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ── Database ────────────────────────────────────────────────────────────

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("MUDALE_DB_NAME", default="mudale"),
        "USER": env_str("MUDALE_DB_USER", default="mudale"),
        "PASSWORD": env_str("MUDALE_DB_PASSWORD", default=""),
        "HOST": env_str("MUDALE_DB_HOST", default="127.0.0.1"),
        "PORT": env_str("MUDALE_DB_PORT", default="5432"),
        "CONN_MAX_AGE": env_int("MUDALE_DB_CONN_MAX_AGE", default=60),
        "OPTIONS": {"connect_timeout": 5},
    }
}

# ── Channels / Redis ────────────────────────────────────────────────────

REDIS_URL = env_str("MUDALE_REDIS_URL", default="redis://127.0.0.1:6379/0")

# RedisPubSubChannelLayer, not the default RedisChannelLayer.
#
# What this layer carries is pure fan-out: "tunnel 3 changed, tell every
# dashboard watching this engagement". The default layer models each consumer as
# a durable queue and holds a blocking read open against Redis for it, which
# raises TimeoutError on an idle socket and drops the connection — observed as
# a "Live" indicator that never delivers an update. Pub/sub has no queue to time
# out, and losing a message while disconnected is fine here: the dashboard
# refetches on reconnect.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.pubsub.RedisPubSubChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

# ── Auth / passwords ────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── REST framework ──────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "apps.accounts.authentication.ApiKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.api.exceptions.api_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# ── i18n / tz ───────────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = env_str("MUDALE_TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# ── Static / frontend ───────────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Built React SPA (vite build output) is collected from here.
_DEFAULT_FRONTEND_DIST = str(BASE_DIR.parent / "frontend" / "dist")
FRONTEND_DIST = Path(env_str("MUDALE_FRONTEND_DIST", default=_DEFAULT_FRONTEND_DIST))
STATICFILES_DIRS = [FRONTEND_DIST] if FRONTEND_DIST.is_dir() else []

# Vite already fingerprints its output, so re-hashing gains nothing; compression
# is the part worth having.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_MAX_AGE = 31536000

# ── Security (hardened by default; dev.py relaxes what it must) ─────────

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env_list("MUDALE_CSRF_TRUSTED_ORIGINS", default=[])
SECURE_HSTS_SECONDS = env_int("MUDALE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = env_bool("MUDALE_SSL_REDIRECT", default=True)

# WebSocket origins allowed to connect. Empty means "same origin only",
# which channels enforces via AllowedHostsOriginValidator.
WEBSOCKET_ALLOWED_ORIGINS = env_list("MUDALE_WEBSOCKET_ALLOWED_ORIGINS", default=[])

# ── Engine (the subprocess-owning daemon) ───────────────────────────────

ENGINE = {
    # Absolute paths to the binaries the engine drives. Resolved at startup;
    # a missing binary disables that adapter rather than crashing the daemon.
    "SSH_BIN": env_str("MUDALE_SSH_BIN", default="ssh"),
    "NMAP_BIN": env_str("MUDALE_NMAP_BIN", default="nmap"),
    "LIGOLO_PROXY_BIN": env_str("MUDALE_LIGOLO_PROXY_BIN", default=""),
    "LIGOLO_AGENT_DIR": env_str("MUDALE_LIGOLO_AGENT_DIR", default=""),
    # How often the supervisor reconciles desired state against reality.
    "RECONCILE_INTERVAL_SECONDS": env_int("MUDALE_ENGINE_RECONCILE_INTERVAL", default=5),
    # How long to wait for a process to die on SIGTERM before SIGKILL.
    "STOP_GRACE_SECONDS": env_int("MUDALE_ENGINE_STOP_GRACE", default=10),
    # Hard ceiling on concurrently running tunnels, enforced in the engine.
    "MAX_CONCURRENT_TUNNELS": env_int("MUDALE_MAX_CONCURRENT_TUNNELS", default=64),
    # Wall-clock cap on a single nmap run.
    "SCAN_TIMEOUT_SECONDS": env_int("MUDALE_SCAN_TIMEOUT", default=3600),
    # Where the engine writes per-process log files.
    "LOG_DIR": env_str("MUDALE_ENGINE_LOG_DIR", default=str(BASE_DIR / "var" / "logs")),
}

# ── Logging ─────────────────────────────────────────────────────────────

LOG_LEVEL = env_str("MUDALE_LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname:<8} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "mudale": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

os.makedirs(ENGINE["LOG_DIR"], exist_ok=True)
