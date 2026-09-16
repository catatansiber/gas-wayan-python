import uuid

from django.conf import settings
from django.db import models

from catalog.models import Customer, Cylinder, GasType


class Cycle(models.Model):
    """Satu siklus tabung di satu pelanggan: dibuka oleh dispatch/exchange-in, ditutup oleh
    return/exchange-out/lost/reversal. Constraint DB (bukan cuma validasi Python) memastikan
    hanya satu Cycle berstatus OPEN per cylinder - lihat Meta.constraints dan migrasi 0002 (CHECK
    tambahan lewat SQL manual, ADR-P004)."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    class CloseReason(models.TextChoices):
        RETURNED = "RETURNED", "Returned"
        EXCHANGED = "EXCHANGED", "Exchanged"
        LOST = "LOST", "Lost"
        REVERSED = "REVERSED", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cylinder = models.ForeignKey(Cylinder, related_name="cycles", on_delete=models.PROTECT)
    customer = models.ForeignKey(Customer, related_name="cycles", on_delete=models.PROTECT)
    gas_type_at_dispatch = models.ForeignKey(
        GasType, null=True, blank=True, on_delete=models.PROTECT
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    sent_at = models.DateField()
    returned_at = models.DateField(null=True, blank=True)
    close_reason = models.CharField(
        max_length=20, choices=CloseReason.choices, blank=True, default=""
    )
    date_unknown = models.BooleanField(
        default=False,
        help_text="True bila tanggal kembali/tutup siklus tidak diketahui pasti.",
    )
    data_quality_flag = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Mis. NEEDS_REVIEW bila gas tidak dikenal saat dispatch.",
    )
    replaced_by = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        related_name="replaces",
        on_delete=models.SET_NULL,
        help_text="Diisi saat siklus ditutup lewat pertukaran (EXCHANGED).",
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cylinder"],
                condition=models.Q(status="OPEN"),
                name="uniq_open_cycle_per_cylinder",
            ),
        ]
        indexes = [models.Index(fields=["customer", "status"])]

    def __str__(self):
        return f"{self.cylinder.serial_number} -> {self.customer} ({self.status})"


class LifecycleEvent(models.Model):
    """Histori append-only. TIDAK PERNAH diupdate/dihapus oleh kode aplikasi - koreksi memakai
    event REVERSED baru yang menunjuk event yang dikoreksi (`reversed_event`), bukan mengubah
    baris lama (DEC-010, ADR-P008)."""

    class EventType(models.TextChoices):
        DISPATCHED = "DISPATCHED", "Dispatched"
        RETURNED = "RETURNED", "Returned"
        EXCHANGED_OUT = "EXCHANGED_OUT", "Exchanged out"
        EXCHANGED_IN = "EXCHANGED_IN", "Exchanged in"
        LOST = "LOST", "Lost"
        MAINTENANCE_STARTED = "MAINTENANCE_STARTED", "Maintenance started"
        MAINTENANCE_COMPLETED = "MAINTENANCE_COMPLETED", "Maintenance completed"
        RETIRED = "RETIRED", "Retired"
        REVERSED = "REVERSED", "Reversed"
        CORRECTED = "CORRECTED", "Corrected"

    class Source(models.TextChoices):
        WEB = "WEB", "Web"
        TELEGRAM = "TELEGRAM", "Telegram"
        IMPORT = "IMPORT", "Import"
        SYSTEM = "SYSTEM", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cylinder = models.ForeignKey(
        Cylinder, related_name="lifecycle_events", on_delete=models.PROTECT
    )
    cycle = models.ForeignKey(
        Cycle, null=True, blank=True, related_name="events", on_delete=models.PROTECT
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    occurred_at = models.DateField(null=True, blank=True)
    date_unknown = models.BooleanField(default=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.WEB)
    reason = models.TextField(blank=True, default="")
    reversed_event = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="reversal_of_set",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["cylinder", "created_at"])]

    def __str__(self):
        return f"{self.event_type} {self.cylinder.serial_number} @ {self.created_at:%Y-%m-%d %H:%M}"


class IdempotencyRecord(models.Model):
    """Idempotency payload-aware: key sama + payload sama -> hasil lama dikembalikan; key sama +
    payload beda -> ditolak (IdempotencyConflict). Scope dalam konteks aktor+command (requirements
    "idempotency key unik dalam scope aktor/command")."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=32, help_text="Nama command, mis. 'dispatch', 'return'.")
    key = models.CharField(max_length=255)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    payload_hash = models.CharField(max_length=64)
    result_cycle = models.ForeignKey(Cycle, null=True, blank=True, on_delete=models.SET_NULL)
    result_cylinder = models.ForeignKey(Cylinder, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "actor", "key"], name="uniq_idempotency_scope_actor_key"
            )
        ]

    def __str__(self):
        return f"{self.scope}:{self.key}"
