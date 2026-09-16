from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.TextChoices):
    """Tiga role baku - lihat requirements.md lama (DEC-009) dan CLAUDE.md. Jangan tambah role
    baru tanpa keputusan bisnis eksplisit; RBAC F2 ke atas dibangun di atas field ini."""

    ADMIN = "ADMIN", "Admin"
    OPERATOR = "OPERATOR", "Operator"
    VIEWER = "VIEWER", "Viewer"


class GasWayanUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Superuser selalu ADMIN - tidak ada superuser dengan role lain yang masuk akal.
        extra_fields["role"] = Role.ADMIN
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """User internal (bukan pelanggan). Role menentukan akses server-side; lihat
    identity/permissions.py. Tidak ada field pelanggan di sini - itu domain `catalog` di F2."""

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)

    objects = GasWayanUserManager()

    def __str__(self):
        return f"{self.username} ({self.role})"
