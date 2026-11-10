"""
Settings are read once at import time, so each case loads them in a fresh
subprocess with a controlled environment. No network or database is touched:
dj-database-url only parses the URL.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parents[2]

PROBE = """
import json, django
from django.conf import settings
django.setup()
db = settings.DATABASES["default"]
handler = settings.LOGGING["handlers"]["stdout"]
print(json.dumps({
    "engine": db["ENGINE"], "host": db["HOST"], "port": db["PORT"], "user": db["USER"],
    "sslmode": db.get("OPTIONS", {}).get("sslmode"),
    "allowed_hosts": settings.ALLOWED_HOSTS,
    "csrf_origins": settings.CSRF_TRUSTED_ORIGINS,
    "log_stream": handler["stream"],
    "app_env": settings.APP_ENV,
    "map_api_key": settings.MAP_API_KEY,
}))
"""

FAKE_URL = "postgresql://postgres.abc123:pw@aws-0-us-east-1.pooler.supabase.com:5432/postgres"


def load_settings(**env):
    clean = {
        k: v for k, v in os.environ.items()
        if not k.startswith(("DJANGO_", "DATABASE_", "RENDER_", "APP_ENV", "MAP_"))
    }
    clean["DJANGO_SETTINGS_MODULE"] = "config.settings"
    clean.update(env)
    return subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BASE_DIR, env=clean,
        capture_output=True, text=True, timeout=60,
    )


class DeployedSettingsTests(SimpleTestCase):
    def test_reads_database_from_database_url_with_ssl(self):
        result = load_settings(DJANGO_SECRET_KEY="x", DATABASE_URL=FAKE_URL, APP_ENV="staging")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["engine"], "django.db.backends.postgresql")
        self.assertEqual(data["host"], "aws-0-us-east-1.pooler.supabase.com")
        self.assertEqual(data["port"], 5432)
        self.assertEqual(data["user"], "postgres.abc123")
        self.assertEqual(data["sslmode"], "require")
        self.assertEqual(data["app_env"], "staging")

    def test_refuses_to_start_without_database_url(self):
        result = load_settings(DJANGO_SECRET_KEY="x")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL must be set", result.stderr)

    def test_refuses_to_start_without_secret_key(self):
        result = load_settings(DATABASE_URL=FAKE_URL)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY must be set", result.stderr)

    def test_render_hostname_is_allowed_and_trusted(self):
        result = load_settings(
            DJANGO_SECRET_KEY="x", DATABASE_URL=FAKE_URL,
            RENDER_EXTERNAL_HOSTNAME="mgt656-staging.onrender.com",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("mgt656-staging.onrender.com", data["allowed_hosts"])
        self.assertIn("https://mgt656-staging.onrender.com", data["csrf_origins"])

    def test_map_api_key_is_read_from_environment(self):
        result = load_settings(
            DJANGO_SECRET_KEY="x", DATABASE_URL=FAKE_URL, MAP_API_KEY="fake-map-key"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["map_api_key"], "fake-map-key")

    def test_map_api_key_defaults_to_empty(self):
        result = load_settings(DJANGO_SECRET_KEY="x", DATABASE_URL=FAKE_URL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["map_api_key"], "")

    def test_logs_go_to_stdout(self):
        result = load_settings(DJANGO_SECRET_KEY="x", DATABASE_URL=FAKE_URL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["log_stream"], "ext://sys.stdout")
