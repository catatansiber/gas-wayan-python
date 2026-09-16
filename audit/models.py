import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Jejak seluruh mutasi penting (FR-11). Append-only - tidak ada UI/admin untuk mengubah
    atau menghapus baris ini (lihat audit/admin.py). `entity_type`/`entity_id` generik (bukan FK)
    supaya audit log tidak terikat siklus hidup baris yang diaudit."""

    class Source(models.TextChoices):
        WEB = "WEB", "Web"
        TELEGRAM = "TELEGRAM", "Telegram"
        IMPORT = "IMPORT", "Import"
        SYSTEM = "SYSTEM", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    role_at_time = models.CharField(max_length=20, blank=True, default="")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.WEB)
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    correlation_id = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.entity_type}:{self.entity_id}"


class OutboxEvent(models.Model):
    """Pola outbox: efek samping (notifikasi, dsb.) dicatat di tabel ini DALAM transaksi yang
    sama dengan mutasi domain, lalu diproses worker terpisah (F6). Belum ada worker di F2 - tabel
    ini hanya diisi, belum dikonsumsi."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.event_type} ({'processed' if self.processed_at else 'pending'})"
