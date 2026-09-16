"""Exception domain - dipakai layanan operations.services. Sengaja bukan turunan
django.core.exceptions.PermissionDenied/Http404 supaya layer ini tetap independen dari HTTP
(Telegram memanggil service yang sama tanpa request/response Django)."""


class DomainError(Exception):
    """Basis seluruh error domain operations."""


class CylinderNotFound(DomainError):
    pass


class CylinderNotAvailable(DomainError):
    pass


class NoActiveCycle(DomainError):
    pass


class InvalidTransition(DomainError):
    pass


class RoleNotAllowed(DomainError):
    pass


class IdempotencyConflict(DomainError):
    """Key sama, payload berbeda - request ditolak, bukan diam-diam dieksekusi ulang."""
