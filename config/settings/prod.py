"""Setting produksi. DEBUG SELALU False di sini (tidak dibaca dari env) supaya tidak mungkin
tertukar jadi True karena kesalahan konfigurasi .env. SECRET_KEY dan ALLOWED_HOSTS WAJIB
disediakan lewat environment produksi - tidak ada default, proses gagal start bila hilang
(ImproperlyConfigured), bukan diam-diam memakai nilai development."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

SECRET_KEY = env("DJANGO_SECRET_KEY")  # wajib ada di environment produksi, tidak ada default
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")  # wajib ada, tidak ada default

DATABASES = {"default": env.db("DATABASE_URL")}  # wajib ada, tidak ada default

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HSTS (F7 - ditemukan lewat `manage.py check --deploy`, security.W004). Default 1 tahun tanpa
# preload (preload butuh commit jangka panjang ke browser vendor - tidak diaktifkan tanpa
# keputusan eksplisit pemilik proyek, lihat dokumentasi Django sebelum mengaktifkan).
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)
