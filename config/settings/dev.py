"""Setting development lokal. Dipakai lewat DJANGO_SETTINGS_MODULE=config.settings.dev (lihat
.env.example). Tidak pernah dipakai untuk deployment produksi - lihat prod.py."""

import environ

from .base import *  # noqa: F401,F403 - meneruskan seluruh setting bersama dari base.py
from .base import BASE_DIR, env

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-insecure-key-change-me-before-prod")

DEBUG = True

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://gaswayan:gaswayan_dev_password@localhost:55432/gaswayan_dev",
    )
}
