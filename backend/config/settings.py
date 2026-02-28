# backend/config/settings.py

from pathlib import Path
from corsheaders.defaults import default_headers
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')

DEBUG = os.getenv('DEBUG', 'False') == 'True'

_render_host     = os.getenv('RENDER_EXTERNAL_HOSTNAME', '')
_extra_hosts_raw = os.getenv('DJANGO_EXTRA_HOSTS', '')
_extra_hosts     = [h.strip() for h in _extra_hosts_raw.split(',') if h.strip()]

ALLOWED_HOSTS = ['localhost', '127.0.0.1'] + (
    [_render_host] if _render_host else []
) + _extra_hosts

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'channels',
    'accounts',
    'reactions',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ASGI_APPLICATION = 'config.asgi.application'

# ── Redis ─────────────────────────────────────────────────────────────────────
# REDIS_URL must be set as an environment variable in production (Render Redis
# addon sets this automatically).  Locally it falls back to localhost.
REDIS_URL = os.getenv('REDIS_URL', '')

# ── Channel Layers ────────────────────────────────────────────────────────────
# Use Redis in production (required for multi-worker deployments).
# Falls back to InMemory for local dev when Redis is not available.
# Install:  pip install channels-redis
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# ── Cache (shared state across workers) ──────────────────────────────────────
# This is what fixes the process-isolation bug.  The stream_state module uses
# this cache as its backing store so that HTTP workers and ASGI WebSocket
# workers all read/write from the same Redis instance.
# Install:  pip install django-redis
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND":  "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                # Keeps pickle-serialised values; needed for None/False/list storage.
                "SERIALIZER": "django_redis.serializers.pickle.PickleSerializer",
            },
            "TIMEOUT":    3600,   # 1 hour TTL — lab sessions are short-lived
            "KEY_PREFIX": "gestured",
        }
    }
else:
    # Local dev without Redis: LocMemCache is per-process but that's fine when
    # running a single dev server.  The WebSocket message layer (Layer 1 fix)
    # ensures the consumer always has the right chemical state regardless.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# ── Database ──────────────────────────────────────────────────────────────────
_db_url = os.getenv('DATABASE_URL')
if _db_url:
    import dj_database_url
    DATABASES = {'default': dj_database_url.config(default=_db_url, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True

STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ── CORS / CSRF ───────────────────────────────────────────────────────────────
_BASE_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://localhost:4173",
    "http://127.0.0.1:5173",
    "https://gestur-ed.vercel.app",
]

_frontend_url  = os.getenv('FRONTEND_URL', '')
_extra_raw     = os.getenv('DJANGO_EXTRA_ORIGINS', '')
_extra_origins = [o.strip() for o in _extra_raw.split(',') if o.strip()]

_all_origins = _BASE_ORIGINS + (
    [_frontend_url] if _frontend_url else []
) + _extra_origins

CORS_ALLOWED_ORIGINS  = _all_origins
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS    = list(default_headers) + ['ngrok-skip-browser-warning']

CSRF_TRUSTED_ORIGINS = _all_origins

SESSION_COOKIE_SAMESITE = 'None'
SESSION_COOKIE_SECURE   = True
CSRF_COOKIE_SAMESITE    = 'None'
CSRF_COOKIE_SECURE      = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
}

# ── Logging ───────────────────────────────────────────────────────────────────
# Exposes DEBUG-level logs from the consumer so you can see the reaction
# check lines in your Render / Railway log viewer.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class":     "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "reactions.consumers": {
            "handlers":  ["console"],
            "level":     "DEBUG",
            "propagate": False,
        },
        "reactions.stream_state": {
            "handlers":  ["console"],
            "level":     "DEBUG",
            "propagate": False,
        },
    },
}