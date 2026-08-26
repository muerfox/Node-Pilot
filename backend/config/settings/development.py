from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE  # noqa: F405
INTERNAL_IPS = ["127.0.0.1"]

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
