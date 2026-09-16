"""Penegakan role server-side. Tidak cukup menyembunyikan tombol di template - setiap view yang
butuh role tertentu HARUS dibungkus salah satu dekorator di sini (FR-01: "API memeriksa role pada
server, bukan hanya menyembunyikan tombol")."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    """403 (server-side) bila role user tidak ada di allowed_roles. Redirect ke login bila belum
    login sama sekali (lewat login_required)."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                raise PermissionDenied("Role Anda tidak memiliki akses ke halaman ini.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
