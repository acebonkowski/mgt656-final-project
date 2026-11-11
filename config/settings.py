"""
Django settings for the MGT656 project.

All configuration comes from environment variables (12-factor). Nothing secret
lives in this file. See `.env.example` for the full list of variables.
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name):
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


# --- Core ---------------------------------------------------------------------

DEBUG = env_bool("DJANGO_DEBUG", default=False)

# "local", "staging" or "production". Shown on the home page so it's obvious
# which environment you're looking at.
APP_ENV = os.environ.get("APP_ENV", "local")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off.")
    SECRET_KEY = "insecure-local-dev-key-do-not-use-in-deployments"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Render sets RENDER_EXTERNAL_HOSTNAME on every web service, so the public
# hostname is allowed without configuring it by hand.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]


# --- A/B test page (course requirement) ---------------------------------------
# The page lives at "/" + first 7 hex chars of sha1(TEAM_NICKNAME). The env var
# holds the nickname, never the hash. Not a secret, so a default is fine.

TEAM_NICKNAME = os.environ.get("TEAM_NICKNAME", "").strip() or "holy-dew"

# Members' course nicknames, shown on the A/B page. Comma-separated in the env.
# TODO: replace the TBD placeholders once the team confirms its nicknames.
TEAM_MEMBER_NICKNAMES = env_list("TEAM_MEMBER_NICKNAMES") or [
    "adventurous-porcupine",
    "TBD-member-2",
    "TBD-member-3",
    "TBD-member-4",
    "TBD-member-5",
]


# --- Applications -------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "abtest",
    "accounts",
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

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"


# --- Database -----------------------------------------------------------------
# Attached via DATABASE_URL. On Render, use Supabase's *Session pooler* string
# (port 5432, user "postgres.<project-ref>"): Render has no outbound IPv6 and
# Supabase's direct host is IPv6-only without the paid IPv4 add-on.
# Session mode keeps one server connection per client, so persistent Django
# connections are fine here. If you switch to the transaction pooler (6543),
# set DATABASE_CONN_MAX_AGE=0 and DATABASE_DISABLE_SERVER_SIDE_CURSORS=true.

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    if not DEBUG:
        raise ImproperlyConfigured("DATABASE_URL must be set when DJANGO_DEBUG is off.")
    # Local development only; never used on staging/production.
    DATABASE_URL = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=int(os.environ.get("DATABASE_CONN_MAX_AGE", "60")),
        conn_health_checks=True,
        ssl_require=env_bool("DATABASE_SSL_REQUIRE", default=not DEBUG),
    )
}
if env_bool("DATABASE_DISABLE_SERVER_SIDE_CURSORS"):
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True


# --- Auth ---------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Login is a one-time code emailed to a Yale address (#6), on top of Django's
# normal auth and sessions. Logged-out users go to the Welcome screen.
LOGIN_URL = "accounts:welcome"
LOGOUT_REDIRECT_URL = "accounts:welcome"
# After login, and after onboarding's "Start discovering" (#7), users land on the map.
LOGIN_REDIRECT_URL = "map"
ONBOARDING_SUCCESS_URL = "map"
# New users (profile not completed) are sent here after login. #7 replaces the
# placeholder page behind this URL name.
ONBOARDING_URL = "accounts:onboarding"

# Grader accounts (per Kyle): created by `manage.py seed`, they log in with a
# fixed code instead of an emailed one and never receive email. The addresses
# are not secret; the code is, so it only comes from the environment. Empty
# means grader login is disabled.
GRADER_ADMIN_EMAIL = "kyle.jensen@yale.edu"
GRADER_MEMBER_EMAIL = "mgt656-demo-member@yale.edu"
GRADER_EMAILS = [GRADER_ADMIN_EMAIL, GRADER_MEMBER_EMAIL]
GRADER_FIXED_OTP = os.environ.get("GRADER_FIXED_OTP", "").strip()


# --- Email (login codes) -------------------------------------------------------
# Sent through Resend's SMTP relay with Django's built-in SMTP backend. Without
# RESEND_API_KEY, local development prints emails to the terminal; deployed
# environments refuse to send (users see an error) rather than log codes.

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
DEFAULT_FROM_EMAIL = os.environ.get("EMAIL_FROM", "").strip() or "Yale Events <login@example.com>"
EMAIL_DELIVERY_ENABLED = bool(RESEND_API_KEY) or DEBUG

if RESEND_API_KEY:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.resend.com"
    # 587 (STARTTLS) by default; Resend also accepts 2587 if a host blocks 587.
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = "resend"
    EMAIL_HOST_PASSWORD = RESEND_API_KEY
    EMAIL_TIMEOUT = 10
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# --- Map (#8) -----------------------------------------------------------------
# Browser map key, read only from the environment and never committed. It is
# visible in the page source by design, so restrict it to our domains in the
# provider's console. Empty means the map screen shows its fallback message.
MAP_API_KEY = os.environ.get("MAP_API_KEY", "")


# --- I18N ---------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True


# --- Static files (served by WhiteNoise, nothing stored at runtime) ----------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Security (deployed environments) -----------------------------------------

if not DEBUG:
    # Render terminates TLS and forwards the original scheme in this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    # /healthz must answer Render's plain-HTTP internal health check.
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]


# --- Logging: everything to stdout --------------------------------------------

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "default",
        },
    },
    "root": {"handlers": ["stdout"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["stdout"], "level": LOG_LEVEL, "propagate": False},
    },
}
