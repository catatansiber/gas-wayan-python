from django.contrib import admin

from .models import AuditLog, OutboxEvent


class ReadOnlyAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "entity_type", "entity_id", "source")
    list_filter = ("source", "action")
    search_fields = ("entity_id", "action")


@admin.register(OutboxEvent)
class OutboxEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("event_type", "created_at", "processed_at", "attempts")
    list_filter = ("event_type",)
