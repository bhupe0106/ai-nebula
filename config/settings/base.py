"""Base settings shared by every environment.

Environment specific modules (development.py, production.py) import * from here
and override the pieces that differ.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, "django-insecure-dev-only-change-me"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DATABASE_URL=(str, f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}"),
    REDIS_URL=(str, ""),
    CELERY_BROKER_URL=(str, ""),
    CELERY_RESULT_BACKEND=(str, ""),
    CELERY_TASK_ALWAYS_EAGER=(bool, True),
    LLM_PROVIDER=(str, "mock"),
    LLM_BASE_URL=(str, "https://api.openai.com/v1"),
    LLM_API_KEY=(str, ""),
    LLM_CHAT_MODEL=(str, "gpt-4o-mini"),
    LLM_EMBEDDING_MODEL=(str, "text-embedding-3-small"),
    LLM_EMBEDDING_BASE_URL=(str, ""),
    LLM_TEMPERATURE=(float, 0.7),
    LLM_MAX_TOKENS=(int, 1024),
    LLM_TIMEOUT=(float, 60.0),
    LLM_EXTRA_HEADERS=(dict, {}),
    LLM_EXTRA_QUERY=(dict, {}),
    MOCK_LLM_DELAY=(float, 0.02),
    RAG_CHUNK_SIZE=(int, 1200),
    RAG_CHUNK_OVERLAP=(int, 200),
    RAG_TOP_K=(int, 5),
    RAG_MIN_SCORE=(float, 0.2),
    RAG_EMBED_BATCH_SIZE=(int, 32),
    RAG_MAX_CANDIDATES=(int, 2000),
    RAG_MAX_UPLOAD_MB=(int, 20),
    DEFAULT_MONTHLY_TOKEN_QUOTA=(int, 200_000),
    CHAT_HISTORY_LIMIT=(int, 24),
    TIME_ZONE=(str, "UTC"),
)

# Load .env if present. Real environment variables always win.
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    environ.Env.read_env(ENV_FILE, overwrite=False)

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

INSTALLED_APPS = [
    # Daphne must be first so `manage.py runserver` speaks ASGI.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    # Local
    "apps.core",
    "apps.accounts",
    "apps.chat",
    "apps.llm",
    "apps.rag",
    "apps.usage",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.chat_sidebar",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"].setdefault("OPTIONS", {})
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"]["OPTIONS"].setdefault("connect_timeout", 5)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "chat:list"
LOGOUT_REDIRECT_URL = "core:home"

SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # chat.js / htmx read the cookie for X-CSRFToken

# ---------------------------------------------------------------------------
# I18N / time
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="chatbot@example.com")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)

# ---------------------------------------------------------------------------
# Channels (WebSockets)
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL") or REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND") or REDIS_URL or "rpc://"
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=not bool(REDIS_URL))
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "user": env("API_USER_THROTTLE", default="120/min"),
        "anon": env("API_ANON_THROTTLE", default="20/min"),
    },
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---------------------------------------------------------------------------
# LLM / RAG / quotas
# ---------------------------------------------------------------------------
LLM_PROVIDER = env("LLM_PROVIDER")
LLM_BASE_URL = env("LLM_BASE_URL").rstrip("/")
LLM_API_KEY = env("LLM_API_KEY")
LLM_CHAT_MODEL = env("LLM_CHAT_MODEL")
LLM_EMBEDDING_MODEL = env("LLM_EMBEDDING_MODEL")
LLM_EMBEDDING_BASE_URL = env("LLM_EMBEDDING_BASE_URL")
LLM_TEMPERATURE = env("LLM_TEMPERATURE")
LLM_MAX_TOKENS = env("LLM_MAX_TOKENS")
LLM_TIMEOUT = env("LLM_TIMEOUT")
LLM_EXTRA_HEADERS = env.json("LLM_EXTRA_HEADERS", default={})
LLM_EXTRA_QUERY = env.json("LLM_EXTRA_QUERY", default={})
LLM_MODEL_CHOICES = list(
    dict.fromkeys(env.list("LLM_MODEL_CHOICES", default=[LLM_CHAT_MODEL]))
)
MOCK_LLM_DELAY = env("MOCK_LLM_DELAY")

RAG_CHUNK_SIZE = env("RAG_CHUNK_SIZE")
RAG_CHUNK_OVERLAP = env("RAG_CHUNK_OVERLAP")
RAG_TOP_K = env("RAG_TOP_K")
RAG_MIN_SCORE = env("RAG_MIN_SCORE")
RAG_EMBED_BATCH_SIZE = env("RAG_EMBED_BATCH_SIZE")
RAG_MAX_CANDIDATES = env("RAG_MAX_CANDIDATES")
RAG_MAX_UPLOAD_MB = env("RAG_MAX_UPLOAD_MB")
RAG_MAX_UPLOAD_BYTES = RAG_MAX_UPLOAD_MB * 1024 * 1024
RAG_ALLOWED_EXTENSIONS = env.list(
    "RAG_ALLOWED_EXTENSIONS", default=[".pdf", ".txt", ".md", ".markdown", ".docx"]
)

DEFAULT_MONTHLY_TOKEN_QUOTA = env("DEFAULT_MONTHLY_TOKEN_QUOTA")
CHAT_HISTORY_LIMIT = env("CHAT_HISTORY_LIMIT")

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = RAG_MAX_UPLOAD_BYTES + (1024 * 1024)

# ---------------------------------------------------------------------------
# Security defaults (overridden in production.py)
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.channels": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": env("APP_LOG_LEVEL", default="INFO"), "propagate": False},
    },
}
