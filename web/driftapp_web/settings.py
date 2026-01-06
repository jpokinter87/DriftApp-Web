"""
Django settings for DriftApp Web.

Configuration pour l'interface web de contrôle de la coupole.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Ajouter le répertoire parent pour accéder à core/
PROJECT_ROOT = BASE_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-driftapp-dev-key-change-in-production'

# SECURITY WARNING: don't run with debug turned on in production!
# Utiliser DJANGO_DEBUG=0 ou DJANGO_DEBUG=false en production
DEBUG = os.environ.get('DJANGO_DEBUG', 'true').lower() in ('true', '1', 'yes')

# Permettre les connexions depuis le réseau local
ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # REST Framework
    'rest_framework',
    # Apps DriftApp
    'tracking',
    'hardware',
    'health',
    'session',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'driftapp_web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'driftapp_web.wsgi.application'

# Database - SQLite pour simplicité (données de session)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = []

# Internationalization
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

# Chemins IPC pour la communication avec le Motor Service
MOTOR_SERVICE_IPC = {
    'COMMAND_FILE': '/dev/shm/motor_command.json',
    'STATUS_FILE': '/dev/shm/motor_status.json',
    'ENCODER_FILE': '/dev/shm/ems22_position.json',
}

# Configuration DriftApp
DRIFTAPP_CONFIG = PROJECT_ROOT / 'data' / 'config.json'

# Logging - fichier horodaté par session
LOGS_DIR = PROJECT_ROOT / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Nombre max de fichiers de log Django à conserver
MAX_DJANGO_LOG_FILES = 20

# Nettoyage des vieux logs Django au démarrage
def _cleanup_old_django_logs():
    """Supprime les vieux fichiers de log Django, garde les N plus récents."""
    log_files = sorted(
        LOGS_DIR.glob("django_*.log"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    for old_file in log_files[MAX_DJANGO_LOG_FILES:]:
        try:
            old_file.unlink()
        except OSError:
            pass

_cleanup_old_django_logs()

# Fichier de log horodaté pour cette session Django
_django_log_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
DJANGO_LOG_FILE = LOGS_DIR / f"django_{_django_log_timestamp}.log"

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': DJANGO_LOG_FILE,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}
