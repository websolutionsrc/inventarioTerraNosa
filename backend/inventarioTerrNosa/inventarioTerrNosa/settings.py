"""
Configuración de Django para el inventario de TerraNosa.

Todo lo que cambia entre este PC y el hosting se lee de variables de entorno o de un
archivo `.env` junto a manage.py (ver `.env.ejemplo`). Sin `.env` arranca en modo local:
SQLite, DEBUG activado y una clave de desarrollo.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(ruta):
    """Lee un archivo .env sencillo (CLAVE=valor). No pisa variables ya definidas."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding='utf-8').splitlines():
        linea = linea.strip()
        if not linea or linea.startswith('#') or '=' not in linea:
            continue
        clave, valor = linea.split('=', 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(BASE_DIR / '.env')


def _env(clave, defecto=None):
    return os.environ.get(clave, defecto)


def _env_bool(clave, defecto=False):
    return _env(clave, str(defecto)).lower() in ('1', 'true', 'si', 'sí', 'yes')


def _env_lista(clave, defecto=''):
    return [v.strip() for v in _env(clave, defecto).split(',') if v.strip()]


DEBUG = _env_bool('DJANGO_DEBUG', True)

SECRET_KEY = _env('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('Falta DJANGO_SECRET_KEY (obligatoria con DEBUG desactivado).')
    SECRET_KEY = 'solo-para-desarrollo-local-no-usar-en-el-hosting'

ALLOWED_HOSTS = _env_lista('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = _env_lista('DJANGO_CSRF_TRUSTED_ORIGINS')


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    # Aplicaciones propias
    'inventario',
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

ROOT_URLCONF = 'inventarioTerrNosa.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'inventarioTerrNosa.wsgi.application'


# Base de datos: SQLite en local, MySQL en el hosting (DB_ENGINE=mysql)
if _env('DB_ENGINE', 'sqlite') == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': _env('DB_NAME', 'inventario_db'),
            'USER': _env('DB_USER', ''),
            'PASSWORD': _env('DB_PASSWORD', ''),
            'HOST': _env('DB_HOST', 'localhost'),
            'PORT': _env('DB_PORT', '3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                'charset': 'utf8mb4',
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': Path(_env('DB_SQLITE_PATH', BASE_DIR / 'db.sqlite3')),
        }
    }

AUTH_USER_MODEL = 'inventario.Usuario'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Idioma y hora de la tienda. Las "ventas del día" se cortan a medianoche de Venezuela.
LANGUAGE_CODE = 'es-ve'
TIME_ZONE = 'America/Caracas'
USE_I18N = True
USE_TZ = True


STATIC_URL = '/static/'
STATIC_ROOT = Path(_env('DJANGO_STATIC_ROOT', BASE_DIR / 'staticfiles'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',  # para la API navegable
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'login': '10/min',
        'pin': '6/min',
    },
    'COERCE_DECIMAL_TO_STRING': True,
}

# Cobros con Binance Pay verificados automáticamente (ver inventario/binance.py).
# La clave de API debe ser de SOLO LECTURA y, si se puede, limitada a la IP del servidor.
BINANCE_API_KEY = _env('BINANCE_API_KEY', '')
BINANCE_API_SECRET = _env('BINANCE_API_SECRET', '')
BINANCE_PAY_ID = _env('BINANCE_PAY_ID', '')            # se muestra al cajero para que se lo dé al cliente
BINANCE_SIMULADO = _env_bool('BINANCE_SIMULADO', False)  # pagos falsos para probar (solo con DEBUG)
BINANCE_MINUTOS_COBRO = int(_env('BINANCE_MINUTOS_COBRO', '15'))
BINANCE_TOLERANCIA_USDT = _env('BINANCE_TOLERANCIA_USDT', '0.10')  # se acepta hasta esto de menos…
BINANCE_TOLERANCIA_PCT = _env('BINANCE_TOLERANCIA_PCT', '1')       # …o este % de menos (lo mayor)
BINANCE_EXCESO_PCT = _env('BINANCE_EXCESO_PCT', '10')              # y hasta este % de más

# En el hosting (DEBUG desactivado) todo va por HTTPS
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = _env_bool('DJANGO_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
