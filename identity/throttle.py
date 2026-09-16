"""Rate limiting login sederhana lewat Django cache framework (LocMemCache default - proses
tunggal, cukup untuk skala F7; Redis/antrean bersama masih MIG-P01 PENDING, menyusul F6/F8 bila
deployment multi-proses). Per (IP, username) supaya satu username yang diserang brute-force
tidak memblokir pengguna lain dari IP yang sama, dan sebaliknya."""

from django.core.cache import cache

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300  # 5 menit


def _key(request, username: str) -> str:
    ip = request.META.get("REMOTE_ADDR", "unknown")
    return f"login_attempts:{ip}:{username.strip().lower()}"


def is_rate_limited(request, username: str) -> bool:
    if not username:
        return False
    return cache.get(_key(request, username), 0) >= MAX_ATTEMPTS


def register_failed_attempt(request, username: str) -> None:
    if not username:
        return
    key = _key(request, username)
    cache.set(key, cache.get(key, 0) + 1, WINDOW_SECONDS)


def reset_attempts(request, username: str) -> None:
    if username:
        cache.delete(_key(request, username))
