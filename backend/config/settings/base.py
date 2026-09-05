"""
Base Django settings for NodePilot controller.

Configuration is sourced from environment variables so secrets are never
committed to source control. See .env.example for the full list of
recognized variables.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(REPO_ROOT / ".env", override=False)


def env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = env("SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "channels",
    "drf_spectacular",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.common",
    "apps.users",
    "apps.authentication",
    "apps.permissions",
    "apps.organizations",
    "apps.audit",
    "apps.nodes",
    "apps.jobs",
    "apps.virtual_machines",
    "apps.storage",
    "apps.networks",
    "apps.images",
    "apps.vm_templates",
    "apps.snapshots",
    "apps.backups",
    "apps.metrics",
    "apps.events",
    "apps.webhooks",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "users.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.RequestContextMiddleware",
    "apps.common.middleware.IdempotencyMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "nodepilot"),
        "USER": env("POSTGRES_USER", "nodepilot"),
        "PASSWORD": env("POSTGRES_PASSWORD", "nodepilot"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(env("POSTGRES_CONN_MAX_AGE", "60") or 60),
        "ATOMIC_REQUESTS": False,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Redis / Celery / Channels
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")
REDIS_LOCK_DB_URL = env("REDIS_LOCK_URL", REDIS_URL)

CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = env("TIME_ZONE", "UTC")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    # Node health can never be trusted from stored state alone (section 8);
    # this sweep is what actually flips a stale node to OFFLINE.
    "sweep-offline-nodes": {"task": "nodes.sweep_offline_nodes", "schedule": 15.0},
    "reconcile-nodes": {"task": "nodes.reconcile_nodes", "schedule": 300.0},
    "apply-backup-retention": {"task": "backups.apply_retention", "schedule": 3600.0},
    "refresh-storage-pools": {"task": "storage.refresh_storage_pools", "schedule": 300.0},
}
# Tests / local dev without a worker running can force synchronous execution.
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    }
}

# ---------------------------------------------------------------------------
# REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "apps.authentication.auth.APITokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.common.exceptions.nodepilot_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "apps.common.throttling.AdminExemptRateThrottle",
        "apps.common.throttling.APITokenRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/min",
        "user": "120/min",
        "api_token": "300/min",
        "login": "10/min",
        "token_create": "10/min",
        "vm_create": "30/min",
        "image_upload": "10/min",
        "console_auth": "20/min",
        "webhook": "60/min",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "NodePilot API",
    "DESCRIPTION": "KVM Infrastructure, Simplified.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_LIFETIME_MIN", "15") or 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_LIFETIME_DAYS", "7") or 7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "SIGNING_KEY": env("JWT_SIGNING_KEY", SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "uuid",
    "USER_ID_CLAIM": "user_uuid",
}

# ---------------------------------------------------------------------------
# CORS / CSRF / Security
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
CSRF_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# I18N / static
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = REPO_ROOT / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(REPO_ROOT / "media")))

# ---------------------------------------------------------------------------
# NodePilot domain configuration
# ---------------------------------------------------------------------------
NODEPILOT = {
    # Seconds between expected agent heartbeats.
    "HEARTBEAT_INTERVAL_SECONDS": int(env("HEARTBEAT_INTERVAL_SECONDS", "10") or 10),
    # A node is considered OFFLINE if no heartbeat is received within this window.
    "OFFLINE_THRESHOLD_SECONDS": int(env("OFFLINE_THRESHOLD_SECONDS", "30") or 30),
    # How long the controller waits for a synchronous agent RPC response
    # (e.g. during heartbeat correlation) before treating it as failed.
    "AGENT_RPC_TIMEOUT_SECONDS": int(env("AGENT_RPC_TIMEOUT_SECONDS", "30") or 30),
    "MIN_SUPPORTED_AGENT_VERSION": env("MIN_SUPPORTED_AGENT_VERSION", "1.0.0"),
    "CONTROLLER_VERSION": env("NODEPILOT_CONTROLLER_VERSION", "0.1.0"),
    "IMAGE_UPLOAD_CHUNK_DIR": Path(env("IMAGE_UPLOAD_CHUNK_DIR", str(REPO_ROOT / "media" / "uploads" / "chunks"))),
    "METRICS_RETENTION_SECONDS": int(env("METRICS_RETENTION_SECONDS", "3600") or 3600),
    "METRICS_SAMPLE_MAX_POINTS": int(env("METRICS_SAMPLE_MAX_POINTS", "720") or 720),
    "WEBHOOK_MAX_RETRIES": int(env("WEBHOOK_MAX_RETRIES", "6") or 6),
    "IDEMPOTENCY_KEY_TTL_SECONDS": int(env("IDEMPOTENCY_KEY_TTL_SECONDS", "86400") or 86400),
}

# ---------------------------------------------------------------------------
# Logging (structured; every request should carry request_id/user/org context
# via apps.common.middleware.RequestContextMiddleware + logging filter).
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "apps.common.logging_utils.RequestContextFilter",
        },
    },
    "formatters": {
        "structured": {
            "()": "apps.common.logging_utils.StructuredFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
            "filters": ["request_context"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "WARNING"), "propagate": False},
        "nodepilot": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO"), "propagate": False},
    },
}

LOGIN_URL = "/api/v1/auth/login/"
