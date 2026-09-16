"""Setting untuk `manage.py test` dan CI. PostgreSQL nyata (ADR-P003/ADR-P006), bukan SQLite -
Django otomatis membuat database `test_<nama>` terpisah dari database dev."""

import environ

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = "test-only-secret-key-not-for-production"

DEBUG = False

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://gaswayan:gaswayan_dev_password@localhost:55432/gaswayan_dev",
    )
}

# Hash password cepat mempercepat suite tes; tidak pernah dipakai di dev/prod.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
