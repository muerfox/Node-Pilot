from .base import *  # noqa: F401,F403

DEBUG = False

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)  # noqa: F405
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000") or 31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

if not env("SECRET_KEY"):  # noqa: F405
    raise RuntimeError("SECRET_KEY must be set in production")
if SECRET_KEY == "insecure-dev-key-change-me":  # noqa: F405
    raise RuntimeError("Refusing to start with the default development SECRET_KEY")
