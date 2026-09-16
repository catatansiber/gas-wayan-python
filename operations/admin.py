from django.contrib import admin

from .models import Cycle, IdempotencyRecord, LifecycleEvent


class ReadOnlyAdminMixin:
    """Tabel append-only/hasil sistem - Admin boleh MELIHAT lewat Django Admin untuk keperluan
    dukungan, tapi tidak boleh menambah/mengubah/menghapus baris di sini. Semua mutasi HARUS
    lewat operations.services supaya audit/idempotency/constraint tetap konsisten (lihat
    phase-plan.md F2: "Admin tidak boleh mengubah tabel event secara bebas melalui Django
    Admin")."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Cycle)
class CycleAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("cylinder", "customer", "status", "sent_at", "returned_at", "close_reason")
    list_filter = ("status", "close_reason", "data_quality_flag")
    search_fields = ("cylinder__serial_number", "customer__display_name")


@admin.register(LifecycleEvent)
class LifecycleEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("cylinder", "event_type", "occurred_at", "actor", "source", "created_at")
    list_filter = ("event_type", "source")
    search_fields = ("cylinder__serial_number",)


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("scope", "key", "actor", "created_at")
    list_filter = ("scope",)
    search_fields = ("key",)
