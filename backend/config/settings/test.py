from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

# The test suite runs against sqlite for speed/portability and never
# touches a real Postgres/Redis instance (Redis is faked in
# tests/conftest.py). Production always uses PostgreSQL -- see
# config/settings/base.py -- this override exists only for `pytest`.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR.parent / "test_db.sqlite3",
    }
}
