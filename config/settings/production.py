"""Production settings.

Everything security sensitive is opt-in through environment variables so the
container can run behind a TLS-terminating proxy without surprises.
"""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Fail fast when the placeholder secret is left in place.
if SECRET_KEY == "django-insecure-dev-only-change-me":  # noqa: F405
    raise RuntimeError("Set SECRET_KEY to a long random value in production.")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Trust X-Forwarded-Proto from the reverse proxy (nginx, Caddy, Fly, Render...).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Hashed, compressed static files.
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
}

# JSON only; no browsable API in production.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
)

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")

# Cross-process WebSockets are required when running more than one Daphne worker.
if not REDIS_URL:  # noqa: F405
    import warnings

    warnings.warn(
        "REDIS_URL is not set: WebSocket messages will not cross processes. "
        "Set REDIS_URL before scaling horizontally.",
        RuntimeWarning,
        stacklevel=2,
    )
